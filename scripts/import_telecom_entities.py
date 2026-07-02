from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

from platform_app.db.pool import get_pool

logger = logging.getLogger(__name__)

# Maps the source CSV's canonical_display_name -> our own concept_id, so all
# surface-form variants for the same real company collapse under one concept
# (matching the manually-seeded rows already in entity_gazetteer).
CONCEPT_ID_BY_COMPANY = {
    "MobiFone": "mobifone",
    "Viettel": "viettel",
    "VinaPhone": "vinaphone",
    "Vietnamobile": "vietnamobile",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Import telecom entity surface forms từ CSV opencrawler")
    parser.add_argument("csv_path")
    parser.add_argument("--industry-code", default="TELECOM")
    args = parser.parse_args()

    rows_to_insert = []
    with Path(args.csv_path).open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("industry_code") != args.industry_code:
                continue
            if row.get("is_active", "TRUE").strip().upper() != "TRUE":
                continue
            company = row.get("canonical_display_name", "").strip()
            surface_form = row.get("surface_form", "").strip()
            concept_id = CONCEPT_ID_BY_COMPANY.get(company)
            if not concept_id or not surface_form:
                continue
            rows_to_insert.append((concept_id, company, surface_form))

    inserted = 0
    with get_pool().connection() as conn:
        for concept_id, canonical_name, surface_form in rows_to_insert:
            result = conn.execute(
                """
                INSERT INTO entity_gazetteer (concept_id, canonical_name, surface_form, entity_type)
                VALUES (%s, %s, %s, 'company')
                ON CONFLICT (concept_id, surface_form) DO NOTHING
                RETURNING id
                """,
                (concept_id, canonical_name, surface_form),
            ).fetchone()
            if result is not None:
                inserted += 1

    logging.basicConfig(level=logging.INFO)
    logger.info("Đọc %d dòng khớp industry_code=%s, chèn mới %d surface form", len(rows_to_insert), args.industry_code, inserted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
