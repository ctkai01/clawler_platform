#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
playwright install chromium
chmod +x scripts/fb-crawl.sh
echo "Cài đặt xong."
echo ""
echo "Chạy crawl (khuyến nghị):"
echo "  ./scripts/fb-crawl.sh crawl-group 'https://www.facebook.com/groups/GROUP_ID' -o output/group_result.json"
echo ""
echo "Hoặc sau khi: source .venv/bin/activate && pip install -e ."
echo "  fb-crawl crawl-group 'https://www.facebook.com/groups/GROUP_ID'"
