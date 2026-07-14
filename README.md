# Clawler Platform

Nền tảng social listening đa nền tảng (multi-tenant B2B) cho MobiFone —
crawl Facebook Group/Page, diễn đàn, báo điện tử; lọc từ khoá, phân loại
sắc thái bằng LLM, gắn thực thể/chủ đề; xuất báo cáo Word/Excel; theo dõi
qua giao diện khách hàng (React) và dashboard vận hành nội bộ (Jinja2).

## Kiến trúc tổng quan

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| API | FastAPI + psycopg3 | REST API cho frontend khách hàng |
| Frontend | React 19 + Vite | Giao diện khách hàng (báo cáo, giám sát, cấu hình) |
| Dashboard nội bộ | FastAPI + Jinja2 | Công cụ vận hành: xem document, trigger DAG, giám sát crawl FB |
| Orchestration | Apache Airflow (CeleryExecutor) | Lên lịch crawl Forum/News (HTTP) + dispatch batch crawl FB |
| FB crawl | Playwright + Celery riêng (RabbitMQ) | Crawl Facebook Group/Page qua account pool xoay vòng |
| Database | PostgreSQL | Dữ liệu ứng dụng (`crawl_platform`) + metadata Airflow (`airflow`) |
| Queue/cache | Redis, RabbitMQ | Airflow Celery broker, FB crawl queue, inflight lock |

Chi tiết luồng DAG/pipeline: xem [`docs/dag-flow.md`](docs/dag-flow.md) và
[`docs/classification-pipeline.md`](docs/classification-pipeline.md).

## Bắt đầu nhanh (máy local mới)

Yêu cầu: Docker + Docker Compose v2, ~4GB RAM rảnh. Node.js 20+ và Python
3.11+ chỉ cần nếu muốn chạy frontend dev server / test ngoài Docker.

```bash
git clone <repo-url> clawler_platform
cd clawler_platform
cp .env.example .env
```

Mở `.env`, điền tối thiểu 2 biến bắt buộc (phần còn lại có default an toàn
cho local — đọc chú thích trong `.env.example`):

```
OPENAI_API_KEY=sk-...
JWT_SECRET=<chuỗi ngẫu nhiên, vd: openssl rand -hex 32>
```

Khởi động toàn bộ stack (lần đầu mất vài phút — build image, tải Chromium
cho FB worker, tự chạy migration DB):

```bash
docker compose up -d --build
docker compose ps   # chờ tất cả "Up"
```

| Service | URL |
|---|---|
| Frontend (React) | http://localhost:5173 |
| API (FastAPI, docs ở `/docs`) | http://localhost:8083 |
| Airflow webserver | http://localhost:8081 (login `admin`/`admin`) |
| Dashboard nội bộ | http://localhost:8082 |
| Postgres | `localhost:5432` (user `crawler`, db `crawl_platform`) |

Tạo tài khoản đầu tiên để đăng nhập frontend:

```bash
curl -X POST http://localhost:8083/auth/register \
  -H "Content-Type: application/json" \
  -d '{"organization_name": "Test Org", "email": "you@example.com", "password": "matkhau123"}'
```

**Hướng dẫn đầy đủ** (dev server frontend, chạy test/lint ngoài Docker,
rebuild sau khi sửa code, crawl FB cần session thật, đồng bộ dữ liệu từ VPS,
xử lý sự cố thường gặp): xem
[`docs/local-dev-setup.md`](docs/local-dev-setup.md).

## Tài liệu khác

- [`docs/dag-flow.md`](docs/dag-flow.md) — sơ đồ flow các DAG Airflow
- [`docs/classification-pipeline.md`](docs/classification-pipeline.md) — pipeline lọc từ khoá/phân loại sắc thái/gắn thực thể
- [`docs/fb-session-pool.md`](docs/fb-session-pool.md) — tạo session đăng nhập Facebook cho crawl
- [`docs/vps-deploy.md`](docs/vps-deploy.md) — runbook deploy code/đồng bộ dữ liệu lên VPS

## Cấu trúc thư mục

```
platform_app/    Backend: api/ (routes), crawlers/ (FB+targets), pipeline/
                  (LLM classify/report), reporting/ (Word/Excel builders),
                  dashboard/ (Jinja2 nội bộ), db/ (migrations)
frontend/         React customer app (Vite)
airflow/dags/     Định nghĩa DAG (mount sống vào container Airflow)
crawling_facebook/ Package Playwright crawler cho FB, cài -e riêng
scripts/          Script vận hành/import dữ liệu một lần (không phải service)
tests/            pytest
docs/             Tài liệu vận hành/kiến trúc chi tiết
```

## Chạy test

```bash
docker compose exec -T api python -m pytest tests/ -q
```

(hoặc dùng venv host — xem mục 7 trong
[`docs/local-dev-setup.md`](docs/local-dev-setup.md))
