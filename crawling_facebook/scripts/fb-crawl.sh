#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "Chưa có venv. Chạy: ./scripts/setup.sh" >&2
  exit 1
fi

# Đảm bảo package luôn import được (tránh lỗi ModuleNotFoundError)
.venv/bin/pip install -q -e .
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"

exec .venv/bin/python -m fb_crawl.cli "$@"
