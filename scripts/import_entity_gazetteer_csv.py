from __future__ import annotations

import argparse
import csv
import logging
import unicodedata
from pathlib import Path

from psycopg.types.json import Jsonb  # noqa: F401  (kept for parity with other scripts' imports)

from platform_app.db.pool import get_pool

logger = logging.getLogger(__name__)


def _fold(text: str) -> str:
    return unicodedata.normalize("NFC", text or "").lower()


def _import_one(csv_path: Path, conn) -> tuple[int, int]:
    inserted = skipped = 0
    # utf-8-sig: several of the opencrawler CSVs start with a UTF-8 BOM.
    with csv_path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            concept_id = (row.get("concept_id") or "").strip()
            surface_form = (row.get("surface_form") or "").strip()
            canonical_display_name = (row.get("canonical_display_name") or "").strip()
            canonical_name = (row.get("canonical_name") or "").strip() or canonical_display_name
            if not concept_id or not surface_form or not canonical_display_name:
                skipped += 1
                continue

            is_active = (row.get("is_active") or "TRUE").strip().upper() == "TRUE"
            result = conn.execute(
                """
                INSERT INTO entity_gazetteer (
                    concept_id, canonical_name, canonical_display_name, surface_form, surface_form_folded,
                    match_kind, entity_type, stakeholder_role, parent_display_name, org_level,
                    industry_code, match_mode, is_active, source_file
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (concept_id, surface_form) DO UPDATE SET
                    canonical_name = EXCLUDED.canonical_name,
                    canonical_display_name = EXCLUDED.canonical_display_name,
                    surface_form_folded = EXCLUDED.surface_form_folded,
                    match_kind = EXCLUDED.match_kind,
                    entity_type = EXCLUDED.entity_type,
                    stakeholder_role = EXCLUDED.stakeholder_role,
                    parent_display_name = EXCLUDED.parent_display_name,
                    org_level = EXCLUDED.org_level,
                    industry_code = EXCLUDED.industry_code,
                    match_mode = EXCLUDED.match_mode,
                    is_active = EXCLUDED.is_active,
                    source_file = EXCLUDED.source_file
                RETURNING id
                """,
                (
                    concept_id,
                    canonical_name,
                    canonical_display_name,
                    surface_form,
                    _fold(surface_form),
                    (row.get("match_kind") or "").strip() or None,
                    (row.get("entity_type") or "").strip() or "company",
                    (row.get("stakeholder_role") or "").strip() or None,
                    (row.get("parent_display_name") or "").strip() or None,
                    (row.get("org_level") or "").strip() or None,
                    (row.get("industry_code") or "").strip() or None,
                    (row.get("match_mode") or "").strip() or "contains",
                    is_active,
                    csv_path.name,
                ),
            ).fetchone()
            if result is not None:
                inserted += 1
    return inserted, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import entity_gazetteer rows từ 1 hoặc nhiều CSV opencrawler (đầy đủ cột, ghi đè nếu đã tồn tại)"
    )
    parser.add_argument("csv_paths", nargs="+")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    total_inserted = total_skipped = 0
    with get_pool().connection() as conn:
        for path_str in args.csv_paths:
            path = Path(path_str)
            inserted, skipped = _import_one(path, conn)
            logger.info("%s: chèn/cập nhật %d dòng, bỏ qua %d dòng", path.name, inserted, skipped)
            total_inserted += inserted
            total_skipped += skipped

    logger.info("Tổng cộng: chèn/cập nhật %d dòng, bỏ qua %d dòng", total_inserted, total_skipped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
