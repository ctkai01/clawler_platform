from __future__ import annotations

import argparse
import logging
import os

from pymongo import MongoClient

from platform_app.db.pool import get_pool

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import password + two_fa_secret từ MongoDB account_pool (fb-distributed-scraper) "
        "vào fb_accounts, để bật tự động refresh session. Chỉ cập nhật account đã tồn tại trong "
        "fb_accounts (id khớp _id bên Mongo) — không tự tạo account mới. Không bao giờ in giá trị "
        "password/2FA thật ra stdout/log."
    )
    parser.add_argument("key", nargs="?", help="Chỉ import 1 account — bỏ trống để import tất cả account khớp _id")
    parser.add_argument("--mongo-uri", default=os.environ.get("MONGO_URI", "mongodb://localhost:27017"))
    parser.add_argument("--mongo-db", default=os.environ.get("MONGO_DB", "fb_crawl"))
    args = parser.parse_args(argv)

    client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=5000)
    collection = client[args.mongo_db]["account_pool"]

    query = {"_id": args.key} if args.key else {}
    docs = list(collection.find(query, {"_id": 1, "password": 1, "two_fa_secret": 1}))
    if not docs:
        logger.warning("Không tìm thấy account nào trong Mongo khớp điều kiện.")
        return 0

    updated = skipped_no_creds = skipped_not_in_pg = 0
    with get_pool().connection() as conn:
        for doc in docs:
            uid = doc["_id"]
            password = doc.get("password")
            two_fa_secret = doc.get("two_fa_secret")
            if not password:
                logger.warning("Account %s không có password trong Mongo — bỏ qua.", uid)
                skipped_no_creds += 1
                continue
            result = conn.execute(
                "UPDATE fb_accounts SET password = %s, two_fa_secret = %s, updated_at = now() WHERE id = %s",
                (password, two_fa_secret, uid),
            )
            if result.rowcount == 0:
                logger.warning("Account %s có trong Mongo nhưng chưa có trong fb_accounts — bỏ qua.", uid)
                skipped_not_in_pg += 1
            else:
                logger.info("Đã import credentials cho account %s", uid)
                updated += 1

    logger.info("Xong — %d account cập nhật, %d bỏ qua (thiếu credentials), %d bỏ qua (chưa có trong fb_accounts).", updated, skipped_no_creds, skipped_not_in_pg)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
