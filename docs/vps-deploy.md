# Đưa thay đổi lên VPS

Runbook cho việc deploy code mới (đã test xong ở local) lên VPS. Có 2 tình
huống khác nhau — đọc đúng phần áp dụng cho lần deploy này, đừng làm cả 2.

- **Deploy code thường** (đa số các lần sau này): chỉ đẩy code + chạy
  migration mới, **không đụng vào dữ liệu đã có trên VPS**. Dùng phần A.
- **Đồng bộ lại toàn bộ DB từ local sang VPS** (chỉ khi cố ý muốn ghi đè dữ
  liệu VPS bằng dữ liệu local — ví dụ giai đoạn còn test): dùng phần B. Việc
  này **xoá sạch dữ liệu hiện có trên VPS**, chỉ làm khi chắc chắn.

Đợt thay đổi hiện tại (2026-07-08) chỉ gồm code + 1 migration cộng cột mới
(không đổi/xoá dữ liệu cũ) → dùng **phần A**.

---

## A. Deploy code thường (khuyến nghị)

### 0. Điều kiện trước khi bắt đầu

Local phải build/test sạch và đã **commit + push lên `origin/main`** — VPS
kéo code qua `git pull`, không qua rsync/scp.

```bash
# Ở máy local, trong thư mục clawler_platform
git status                      # kiểm tra không còn gì cần commit
git add -A
git commit -m "mô tả thay đổi"  # bạn tự viết nội dung commit
git push origin main
```

### 1. SSH vào VPS và kéo code mới

```bash
ssh root@<VPS_IP>
cd /path/to/clawler_platform      # đường dẫn thực tế trên VPS
git pull origin main
```

### 2. Rebuild các service bị ảnh hưởng

Chỉ service nào COPY code Python/Frontend vào image lúc build mới cần rebuild
(khác với `airflow/dags` — thư mục DAG được mount sống, không cần rebuild).
An toàn nhất là rebuild đủ bộ dưới đây mỗi lần có đổi backend + frontend:

```bash
docker compose build api airflow-worker-http airflow-worker-fb \
  airflow-scheduler airflow-webserver frontend
```

Nếu chỉ đổi frontend (React/TSX) thì chỉ cần `docker compose build frontend`.
Nếu chỉ đổi backend (`platform_app/`, migration mới) thì bỏ `frontend` ra
khỏi lệnh trên.

### 3. Khởi động lại

```bash
docker compose up -d api airflow-worker-http airflow-worker-fb \
  airflow-scheduler airflow-webserver frontend
```

Migration SQL mới trong `platform_app/db/migrations/` được áp dụng **tự
động** — `airflow-init` chạy `python -m platform_app.db.migrate` mỗi khi
`docker compose up`, và migration cũ đã áp dụng thì bị bỏ qua (tracked trong
bảng `schema_migrations`). Không cần chạy migrate tay.

`postgres`/`redis` không nằm trong danh sách trên — **không restart** để
không làm gián đoạn dữ liệu đang chạy.

### 4. Kiểm tra sau deploy

```bash
# Container nào cũng phải "Up" / "healthy"
docker compose ps

# Migration mới đã chạy chưa
docker compose exec -T postgres psql -U crawler -d crawl_platform -c \
  "SELECT filename FROM schema_migrations ORDER BY filename DESC LIMIT 5;"

# API còn sống
curl -s http://localhost:8083/health || curl -s http://localhost:8083/

# Log không có traceback lặp lại
docker compose logs --tail=50 api
docker compose logs --tail=50 airflow-scheduler
```

Sau đó mở frontend trên trình duyệt (`http://<VPS_IP>:5173`), thử mở 1 bài
viết có ảnh ở trang "Bài viết đã crawl" — nếu org đang bật `llm_image`, panel
chi tiết phải hiện khối "Tóm tắt nội dung" / "Tóm tắt ảnh".

---

## B. Đồng bộ lại toàn bộ DB từ local sang VPS (chỉ khi cố ý)

⚠️ Bước này **ghi đè/xoá sạch** dữ liệu hiện có trong `crawl_platform` trên
VPS bằng dữ liệu local. Chỉ dùng khi VPS chưa có dữ liệu thật cần giữ (ví dụ
đang test), không dùng khi VPS đã chạy crawl thật.

### 1. Dump DB ở local

```bash
docker compose exec -T postgres pg_dump -U crawler -d crawl_platform \
  --no-owner --no-privileges -F c -f /tmp/crawl_platform.dump
docker compose cp postgres:/tmp/crawl_platform.dump ./crawl_platform.dump

# Kiểm tra dump hợp lệ trước khi gửi đi
docker run --rm -v "$(pwd)/crawl_platform.dump:/dump.dump:ro" postgres:16-alpine \
  pg_restore --list /dump.dump | head -20
```

### 2. Gửi dump sang VPS

```bash
scp ./crawl_platform.dump root@<VPS_IP>:/path/to/clawler_platform/
```

### 3. Trên VPS: pull code, build, dừng service ứng dụng (giữ postgres/redis)

```bash
cd /path/to/clawler_platform
git pull origin main
docker compose build api airflow-worker-http airflow-worker-fb \
  airflow-scheduler airflow-webserver frontend
docker compose stop api airflow-worker-http airflow-worker-fb \
  airflow-scheduler airflow-webserver airflow-init frontend
```

### 4. Restore đè lên DB trên VPS

```bash
docker compose exec -T postgres pg_restore -U crawler -d crawl_platform \
  --clean --if-exists --no-owner --no-privileges < ./crawl_platform.dump
```

### 5. Khởi động lại toàn bộ

```bash
docker compose up -d
docker compose ps
```

---

## Ghi chú

- `postgres`/`redis` chỉ nên restart khi thật sự cần (đổi env liên quan tới
  chúng) — restart không cần thiết có thể gây gián đoạn crawl/pipeline đang
  chạy dở.
- Đợt thay đổi 2026-07-08 gồm: fix tải ảnh Facebook CDN cho `llm_image`
  (base64 thay vì gửi URL trần), thêm tóm tắt nội dung/ảnh do LLM sinh
  (`classification_text_summary`, `classification_image_summary`), tách
  luồng mô tả ảnh 2 bước (mô tả từng ảnh → fold vào text classify) theo
  đúng prompt của `opencrawler/classify/llm_classifier.py`, migration
  `0020_document_classification_summary.sql`.
- Việc bật mode `llm_image` cho từng org là cấu hình runtime
  (`pipeline_settings.classify_mode`, đổi qua trang Cài đặt hoặc
  `set_classify_mode()`) — không nằm trong code deploy, không tự đổi khi
  deploy lên VPS. Org nào đang ở mode nào trên VPS thì giữ nguyên mode đó
  sau khi deploy.
