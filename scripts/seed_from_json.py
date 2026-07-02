from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from platform_app.targets.repository import seed_target

logger = logging.getLogger(__name__)


def _normalize_url(url: str) -> str:
    # Prevents "facebook.com/x" and "facebook.com/x/" from seeding two rows
    # for what's the same real target (crawl_targets dedupes on exact url).
    return url.strip().rstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed crawl_targets từ file JSON groups/pages")
    parser.add_argument("json_path")
    parser.add_argument("--interval", type=int, default=3600)
    args = parser.parse_args()

    data = json.loads(Path(args.json_path).read_text(encoding="utf-8"))

    counts = {"facebook_group": 0, "facebook_page": 0}
    for item in data.get("groups", []):
        seed_target(
            "facebook_group",
            _normalize_url(item["share_url"]),
            display_name=item.get("source_name"),
            crawl_interval_sec=args.interval,
            enabled=bool(item.get("enabled", True)),
        )
        counts["facebook_group"] += 1

    for item in data.get("pages", []):
        seed_target(
            "facebook_page",
            _normalize_url(item["share_url"]),
            display_name=item.get("source_name"),
            crawl_interval_sec=args.interval,
            enabled=bool(item.get("enabled", True)),
        )
        counts["facebook_page"] += 1

    logging.basicConfig(level=logging.INFO)
    logger.info("Seeded %d facebook_group, %d facebook_page targets", counts["facebook_group"], counts["facebook_page"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
