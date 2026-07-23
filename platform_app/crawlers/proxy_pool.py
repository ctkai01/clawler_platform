from __future__ import annotations

import base64
import itertools
import logging
import os
import socket
import threading
import time
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# How long a proxy that just failed a health check (startup probe or a
# confirmed net::ERR_* during a real crawl) sits out of acquire()'s
# rotation. Long enough that concurrent batches dispatched in the same
# burst don't all pile onto the same known-bad proxy; short enough that a
# proxy which comes back (provider fixes it, IP reset finishes propagating)
# gets tried again without a worker restart.
_UNHEALTHY_COOLDOWN_SECONDS = 300.0
# Startup probe target/timeout — CONNECT through the proxy to the actual
# site we crawl, not some generic reachability check, since a proxy can
# accept TCP connections but still fail to tunnel to facebook.com
# specifically (auth issue, IP banned by FB, etc).
_PROBE_TARGET = "www.facebook.com:443"
_PROBE_TIMEOUT_SECONDS = 5.0


@dataclass
class Proxy:
    server: str | None  # e.g. "http://host:port"; None = direct connection
    username: str | None = None
    password: str | None = None
    reset_url: str | None = None  # GET endpoint that rotates the IP behind this port


def _numbered_proxies() -> list[Proxy]:
    """FB_PROXY_SERVER_1/_2/... (+ _USER_N/_PASS_N/_RESET_URL_N) — several
    authenticated proxies, each with its own IP-rotation API. Scans from 1
    until a gap. This is the only format that supports per-proxy auth +
    reset — FB_PROXY_SERVERS (plural, no suffix) is auth-less by design."""
    proxies = []
    i = 1
    while True:
        server = os.environ.get(f"FB_PROXY_SERVER_{i}", "").strip()
        if not server:
            break
        proxies.append(
            Proxy(
                server=server if "://" in server else f"http://{server}",
                username=os.environ.get(f"FB_PROXY_USER_{i}") or None,
                password=os.environ.get(f"FB_PROXY_PASS_{i}") or None,
                reset_url=os.environ.get(f"FB_PROXY_RESET_URL_{i}") or None,
            )
        )
        i += 1
    return proxies


class ProxyPool:
    """Round-robin pool of proxy endpoints for FB crawl tasks.

    Three ways to configure, checked in this order:
    - FB_PROXY_SERVER_1/_2/... (+ _USER_N/_PASS_N/_RESET_URL_N): several
      authenticated proxies, each with its own IP-rotation API — use this
      when running with FB_CELERY_CONCURRENCY > 1, so concurrent batches
      round-robin onto DIFFERENT physical proxies instead of one batch's
      reset() clobbering another's still-in-flight session on the same port
      (see docs/fb-worker-remote.md's proxy-collision note — same root
      issue, just between concurrent batches on one worker instead of
      across two workers).
    - FB_PROXY_SERVER (+ FB_PROXY_USER/FB_PROXY_PASS/FB_PROXY_RESET_URL):
      a single authenticated proxy — only safe with concurrency=1.
    - FB_PROXY_SERVERS: comma-separated server URLs, no auth/reset (simple
      round robin over several proxies).

    With none set, acquire() returns a no-proxy Proxy so crawling behaves
    exactly as it does today — safe to leave wired in permanently.
    """

    def __init__(self) -> None:
        numbered = _numbered_proxies()
        if numbered:
            self._proxies = numbered
        else:
            single_server = os.environ.get("FB_PROXY_SERVER", "").strip()
            if single_server:
                server = single_server if "://" in single_server else f"http://{single_server}"
                self._proxies = [
                    Proxy(
                        server=server,
                        username=os.environ.get("FB_PROXY_USER") or None,
                        password=os.environ.get("FB_PROXY_PASS") or None,
                        reset_url=os.environ.get("FB_PROXY_RESET_URL") or None,
                    )
                ]
            else:
                raw = os.environ.get("FB_PROXY_SERVERS", "").strip()
                servers = [s.strip() for s in raw.split(",") if s.strip()]
                self._proxies = [Proxy(server=s) for s in servers] or [Proxy(server=None)]
        self._cycle = itertools.cycle(self._proxies)
        self._lock = threading.Lock()
        # server -> monotonic timestamp the proxy is skipped in acquire()
        # until. Populated by the startup probe below and by mark_unhealthy()
        # on a confirmed failure during a real crawl (see reset()).
        self._cooldown_until: dict[str, float] = {}
        self._health_check_all()

    def _probe(self, proxy: Proxy) -> bool:
        """CONNECT through this proxy to the actual site we crawl — a proxy
        can accept TCP connections but still fail to tunnel to
        facebook.com specifically (bad auth, IP banned by FB...), so a bare
        reachability check wouldn't catch what actually matters."""
        if proxy.server is None:
            return True
        host_port = proxy.server.split("://", 1)[-1]
        host, _, port_str = host_port.partition(":")
        try:
            port = int(port_str)
        except ValueError:
            return True  # unparseable — don't block startup over this
        try:
            with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT_SECONDS) as sock:
                sock.settimeout(_PROBE_TIMEOUT_SECONDS)
                request = f"CONNECT {_PROBE_TARGET} HTTP/1.1\r\nHost: {_PROBE_TARGET}\r\n"
                if proxy.username:
                    cred = base64.b64encode(f"{proxy.username}:{proxy.password}".encode()).decode()
                    request += f"Proxy-Authorization: Basic {cred}\r\n"
                request += "\r\n"
                sock.sendall(request.encode())
                status_line = sock.recv(64)
            return b" 200 " in status_line
        except Exception:
            return False

    def _health_check_all(self) -> None:
        """One-time probe of every configured proxy at worker startup —
        catches a proxy that's already dead (provider outage, banned IP...)
        before any crawl batch wastes a full retry cycle finding out the
        hard way. Runs sequentially at construction time (worker boot),
        never in the per-task hot path."""
        for proxy in self._proxies:
            if proxy.server is None or self._probe(proxy):
                continue
            self.mark_unhealthy(proxy)
            logger.warning(
                "Proxy %s không kết nối được lúc khởi động, tạm nghỉ %.0fs.",
                proxy.server, _UNHEALTHY_COOLDOWN_SECONDS,
            )

    def _is_cooling_down(self, proxy: Proxy) -> bool:
        if proxy.server is None:
            return False
        until = self._cooldown_until.get(proxy.server)
        return until is not None and time.monotonic() < until

    def mark_unhealthy(self, proxy: Proxy, cooldown_seconds: float = _UNHEALTHY_COOLDOWN_SECONDS) -> None:
        if proxy.server is None:
            return
        self._cooldown_until[proxy.server] = time.monotonic() + cooldown_seconds

    def acquire(self) -> Proxy:
        """Returns the next healthy proxy in the round-robin cycle WITHOUT
        touching its IP. A real account, viewed from a stable IP over time,
        reads as normal usage to Facebook; an account whose exit IP changes
        on every single batch (every acquire() used to force a reset here,
        unconditionally) reads as classic bot/account-takeover behavior —
        real incident: once profile crawling scaled up batch/acquire
        frequency, this started timing out group/page crawls too, sharing
        the same 6 proxies. Only reset a specific proxy's IP on confirmed
        failure — see reset().

        Proxies currently in cooldown (failed the startup probe, or failed
        during a real crawl recently) are skipped in favor of a healthy one
        — but this fails open: if every proxy is in cooldown, still returns
        one rather than blocking dispatch entirely."""
        with self._lock:
            for _ in range(len(self._proxies)):
                proxy = next(self._cycle)
                if not self._is_cooling_down(proxy):
                    return proxy
            return next(self._cycle)

    def reset(self, proxy: Proxy) -> None:
        """Explicitly rotate this one proxy's IP — call only when it's been
        confirmed bad (e.g. connection refused, repeated failures), not
        preemptively on every use. Also puts it in cooldown so other
        concurrent/subsequent batches don't immediately pile onto the same
        proxy while the new IP is still propagating."""
        self.mark_unhealthy(proxy)
        if not proxy.reset_url:
            return
        try:
            urllib.request.urlopen(proxy.reset_url, timeout=10).read()
            logger.info("Đã đổi IP proxy qua %s", proxy.reset_url)
        except Exception:
            logger.warning("Không đổi được IP proxy qua %s", proxy.reset_url, exc_info=True)
