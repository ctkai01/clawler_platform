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


class ProxyPool:
    """Round-robin pool of proxy endpoints for FB crawl tasks.

    Two ways to configure:
    - FB_PROXY_SERVER (+ FB_PROXY_USER/FB_PROXY_PASS/FB_PROXY_RESET_URL):
      a single authenticated proxy (e.g. a mobile 4G port), IP reset via
      its change-IP API before each acquire().
    - FB_PROXY_SERVERS: comma-separated server URLs, no auth/reset (simple
      round robin over several proxies).

    With neither set, acquire() returns a no-proxy Proxy so crawling
    behaves exactly as it does today — safe to leave wired in permanently.
    """

    def __init__(self) -> None:
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
