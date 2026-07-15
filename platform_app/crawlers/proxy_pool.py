from __future__ import annotations

import itertools
import logging
import os
import threading
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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

    def acquire(self) -> Proxy:
        with self._lock:
            proxy = next(self._cycle)
        if proxy.reset_url:
            try:
                urllib.request.urlopen(proxy.reset_url, timeout=10).read()
                logger.info("Đã đổi IP proxy qua %s", proxy.reset_url)
            except Exception:
                logger.warning("Không đổi được IP proxy qua %s", proxy.reset_url, exc_info=True)
        return proxy
