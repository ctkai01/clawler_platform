# Chạy dự án ở máy local

Hướng dẫn setup toàn bộ hệ thống (backend + Airflow + frontend) trên 1 máy
local mới, từ đầu.

## 1. Yêu cầu

- **Docker** + **Docker Compose** (v2, lệnh `docker compose`, không phải
  `docker-compose` rời) — bắt buộc, toàn bộ backend/Airflow/DB chạy qua đây.
- **Node.js 20+** — chỉ cần nếu muốn chạy frontend dev server (`npm run dev`)
  thay vì build qua Docker mỗi lần sửa code.
- **Python 3.11+** — chỉ cần nếu muốn chạy `pytest`/lint ở máy host thay vì
  `docker compose exec`.
- Ít nhất ~4GB RAM rảnh (Postgres + Redis + Airflow scheduler/webserver + 2
  Celery worker + Chromium cho FB worker cùng chạy).

## 2. Clone + cấu hình `.env`

```bash
git clone <repo-url> clawler_platform
cd clawler_platform
cp .env.example .env
```

Mở `.env`, điền tối thiểu 2 biến bắt buộc (còn lại có default an toàn cho
local, đọc chú thích trong `.env.example`):

```
OPENAI_API_KEY=sk-...
JWT_SECRET=<chuỗi ngẫu nhiên bất kỳ, vd: openssl rand -hex 32>
```

Không cần set `POSTGRES_PASSWORD`/`APP_DB_PASSWORD`/`AIRFLOW_ADMIN_PASSWORD`
cho local — mặc định `airflow`/`crawler`/`admin` là đủ dùng khi không public
ra internet.

## 3. Khởi động toàn bộ stack

```bash
docker compose up -d --build
```

Lần đầu sẽ mất vài phút (tải Postgres/Redis image, build image Python, tải
Chromium cho FB worker). `airflow-init` tự chạy migration DB (cả
`platform_app/db/migrations/*.sql` lẫn Airflow's own metadata) — không cần
chạy migrate tay.

Kiểm tra tất cả container đã "Up":
```bash
docker compose ps
```

## 4. Các cổng dịch vụ

| Service | URL | Ghi chú |
|---|---|---|
| Frontend (React) | http://localhost:5173 | UI chính |
| API (FastAPI) | http://localhost:8083 | REST API, docs ở `/docs` |
| Airflow webserver | http://localhost:8081 | login `admin`/`admin` (mặc định) |
| Dashboard nội bộ | http://localhost:8082 | công cụ debug/trigger DAG thủ công |
| Postgres | localhost:5432 | user `crawler` / db `crawl_platform` |

## 5. Tạo tài khoản đầu tiên

Ứng dụng là multi-tenant — cần 1 tài khoản `org_main` để đăng nhập vào UI
chính (http://localhost:5173):

```bash
curl -X POST http://localhost:8083/auth/register \
  -H "Content-Type: application/json" \
  -d '{"organization_name": "Test Org", "email": "you@example.com", "password": "matkhau123"}'
```

Đăng nhập bằng email/password đó ở trang `/login`.

Nếu cần tài khoản `system_admin` (quản trị catalog Entity/Keyword/Chủ đề
toàn hệ thống, ở `/admin/*`):
```bash
docker compose exec -T api python scripts/seed_admin.py admin@example.com
```
(script hỏi password qua stdin, chạy trong container vì cần kết nối DB nội bộ)

## 6. Frontend — chạy dev server riêng (khuyến nghị khi đang code)

Container `frontend` trong Docker Compose build lại **toàn bộ** mỗi lần đổi
code (chậm, không hot-reload). Khi đang phát triển, tắt container đó và chạy
dev server thật thay thế:

```bash
docker compose stop frontend   # tránh xung đột cổng 5173
cd frontend
npm install
npm run dev
```

Vite dev server có hot-reload, đọc thẳng `frontend/src/`, chạy ở cùng cổng
5173. **Không chạy đồng thời cả 2** (container `frontend` + `npm run dev`) —
cả hai cùng cố bind cổng 5173, cái chạy sau sẽ báo lỗi
`address already in use`.

`frontend/.env` không cần tạo riêng — Vite dev server mặc định trỏ API tới
`http://localhost:8083` (khớp cổng container `api` ở bước 3).

## 7. Backend — chạy test/lint không qua Docker (tuỳ chọn)

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,airflow]"
.venv/bin/pip install -e ./crawling_facebook
PYTHONPATH=. .venv/bin/python -m pytest tests/ -q
```

Venv này dùng chung Postgres của Docker (`localhost:5432`, đã expose ra host)
nên không cần cài Postgres riêng — `CRAWL_PLATFORM_DSN` mặc định trong code
đã trỏ đúng.

## 8. Sau khi sửa code backend — rebuild container

`platform_app/` được COPY vào image lúc build (không mount sống), nên **mọi
thay đổi Python đều cần rebuild + restart** container liên quan:

```bash
docker compose build api airflow-worker-http airflow-worker-fb \
  airflow-scheduler airflow-webserver
docker compose up -d api airflow-worker-http airflow-worker-fb \
  airflow-scheduler airflow-webserver
```

Riêng `airflow/dags/*.py` **mount sống** (`./airflow/dags:/opt/airflow/dags`)
— sửa DAG không cần build, chỉ cần restart để scheduler nhận file mới ngay:
```bash
docker compose restart airflow-scheduler airflow-webserver
```

## 9. Crawl Facebook ở local (tuỳ chọn)

Crawl FB Group/Page cần session đăng nhập thật — xem
[`docs/fb-session-pool.md`](fb-session-pool.md) để biết cách tạo
`secrets/fb_session.json` (chạy `fb-crawl login`, cần máy có màn hình/trình
duyệt, không chạy được trong container headless).

Forum/News crawl không cần login, hoạt động ngay sau bước 3.

## 10. Lấy dữ liệu thật từ VPS về máy local (tuỳ chọn)

Setup xong bằng bước 2-3 chỉ có DB rỗng. Muốn có dữ liệu thật (document đã
crawl, entity, tổ chức...) để test, đồng bộ ngược từ VPS về — làm trên **2
máy**: chạy dump ở VPS, restore ở máy local.

⚠️ Bước restore **ghi đè/xoá sạch** dữ liệu hiện có trong `crawl_platform` ở
máy local. Nếu local đang có dữ liệu cần giữ, bỏ qua bước này hoặc tự backup
trước.

**1. Trên VPS — dump DB:**

```bash
docker compose exec -T postgres pg_dump -U crawler -d crawl_platform \
  --no-owner --no-privileges -F c -f /tmp/crawl_platform.dump
docker compose cp postgres:/tmp/crawl_platform.dump ./crawl_platform.dump
```

**2. Tải file dump về máy local** (chạy lệnh này ở máy local, không phải VPS):

```bash
scp root@<VPS_IP>:/root/clawler_platform/crawl_platform.dump ./crawl_platform.dump
```

**3. Trên máy local — kiểm tra dump hợp lệ trước khi restore:**

```bash
docker run --rm -v "$(pwd)/crawl_platform.dump:/dump.dump:ro" postgres:16-alpine \
  pg_restore --list /dump.dump | head -20
```

**4. Dừng service ứng dụng** (giữ nguyên `postgres`/`redis` đang chạy):

```bash
docker compose stop api airflow-worker-http airflow-worker-fb \
  airflow-scheduler airflow-webserver airflow-init frontend
```

**5. Restore đè lên DB local:**

```bash
docker compose exec -T postgres pg_restore -U crawler -d crawl_platform \
  --clean --if-exists --no-owner --no-privileges < ./crawl_platform.dump
```

**6. Khởi động lại toàn bộ:**

```bash
docker compose up -d
```

Tài khoản đăng nhập giờ là tài khoản thật đã có trên VPS (không phải tài
khoản tạo ở bước 5 nữa) — dùng email/password đã biết từ VPS để đăng nhập ở
`/login` local.

## 11. Dừng / dọn dẹp

```bash
docker compose down          # dừng, giữ lại data (volume postgres-data)
docker compose down -v       # dừng + XOÁ SẠCH data — chỉ dùng khi muốn làm lại từ đầu
```

## Xử lý sự cố thường gặp

- **`address already in use` ở cổng 5173`**: đang chạy cả container
  `frontend` lẫn `npm run dev` cùng lúc — chỉ giữ 1 trong 2 (xem mục 6).
- **API trả lỗi `relation "..." does not exist`**: migration chưa chạy — kiểm
  tra `docker compose logs airflow-init`, hoặc chạy tay:
  `docker compose exec -T api python -m platform_app.db.migrate`.
- **Đổi code Python nhưng không thấy hiệu lực**: quên rebuild — xem mục 8.
- **FB crawl fail `session_expired` ngay từ đầu**: chưa tạo
  `secrets/fb_session.json` — xem mục 9.
