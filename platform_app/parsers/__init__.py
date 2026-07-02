from __future__ import annotations

import importlib
import pkgutil

from platform_app.parsers import generic_css  # noqa: F401 - registers "generic_css"
from platform_app.parsers import sites


def _load_site_plugins() -> None:
    for info in pkgutil.iter_modules(sites.__path__):
        importlib.import_module(f"{sites.__name__}.{info.name}")


_load_site_plugins()
