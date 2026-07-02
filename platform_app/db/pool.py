from __future__ import annotations

import os
from functools import lru_cache

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def _dsn() -> str:
    return os.environ.get(
        "CRAWL_PLATFORM_DSN",
        "postgresql://crawler:crawler@localhost:5432/crawl_platform",
    )


@lru_cache(maxsize=1)
def get_pool() -> ConnectionPool:
    pool = ConnectionPool(
        _dsn(),
        min_size=1,
        max_size=10,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    pool.wait()
    return pool
