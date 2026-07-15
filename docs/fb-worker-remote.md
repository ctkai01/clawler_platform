# Thêm fb-celery-worker chạy trên máy thứ 2

Runbook thêm 1 `fb-celery-worker` chạy trên 1 máy vật lý khác, dùng chung
Postgres/Redis/RabbitMQ với máy đang giữ 3 service này ("hub") thay vì dựng
lại toàn bộ stack. Worker mới tự cạnh tranh nhận batch cùng queue `fb_crawl`
với worker hiện có — không cần đổi code, `AccountPool` (khoá theo dòng
Postgres) và RabbitMQ (competing-consumer mặc định của Celery) đã an toàn
cho nhiều worker từ trước.

Đường truyền dùng **Tailscale** (mesh riêng, mã hoá) — không mở port ra
Internet công khai.

## 0. Điều kiện

- Máy 2 đã/sẽ join cùng tailnet với hub.
- Biết Tailscale IP của hub (`tailscale status` trên hub, dạng `100.x.x.x`).
- `APP_DB_PASSWORD` của hub (trong `.env` hub) — worker cần đúng giá trị này
  để kết nối Postgres.

## 1. Trên hub — mở port cho tailnet

Trong `.env` của hub, set:

```
LAN_BIND_IP=<Tailscale IP của hub, vd 100.91.111.85>
```

Áp dụng (chỉ cần recreate 3 service này, không cần đụng service khác):

```bash
docker compose up -d postgres redis rabbitmq
```

Kiểm tra đã bind đúng IP (không phải `0.0.0.0`):

```bash
ss -tlnp | grep -E '5432|16379|5672'
```

⚠️ **Không bao giờ** set `LAN_BIND_IP=0.0.0.0` hay 1 IP public thật — kể cả
khi hub sau này là VPS (xem mục 5).

## 2. Trên máy 2 — cài đặt cơ bản

```bash
# Docker + Docker Compose v2 nếu chưa có
curl -fsSL https://get.docker.com | sh

# Tailscale nếu chưa có (tommy-dell-u22 thì bỏ qua, chỉ cần bật lại)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Xác nhận thấy hub
tailscale ping <Tailscale IP của hub>
```

## 3. Clone repo

```bash
git clone <repo-url> clawler_platform
cd clawler_platform
```

Không cần đồng bộ session Facebook riêng — session giờ nằm trong
`fb_accounts.session_data` (Postgres), máy 2 tự có ngay khi kết nối được
DB chung với hub qua `HUB_HOST` (mục 4).

## 4. Cấu hình `.env` trên máy 2

```bash
cp .env.worker.example .env
```

Điền `HUB_HOST` (Tailscale IP của hub) và `APP_DB_PASSWORD` (khớp hub).
**Không** set bất kỳ biến `FB_PROXY_*` nào — xem giải thích trong
`docker-compose.worker.yml`: nếu dùng chung cấu hình proxy 1-cổng của hub,
2 worker sẽ đổi IP đè lên nhau giữa lúc worker kia đang crawl dở. Để trống,
worker này tự crawl trực tiếp bằng IP thật của máy 2 — vừa tránh đụng độ vừa
có thêm 1 nguồn IP khác biệt.

## 5. Khởi động worker

```bash
docker compose -f docker-compose.worker.yml up -d --build
```

Lần đầu build tải Chromium (~180MB), mất vài phút.

## 6. Kiểm tra

```bash
# Trên máy 2 — xem log kết nối thành công, không lỗi connection refused
docker compose -f docker-compose.worker.yml logs -f fb-celery-worker

# Từ hub (hoặc máy 2) — cả 2 worker cùng trả lời pong
docker compose exec -T fb-celery-worker celery -A platform_app.crawlers.celery_app \
  inspect ping --timeout 5
```

Trigger 1 đợt dispatch thật (trang `/fb-crawl` → "Trigger ngay", hoặc đợi
tick kế tiếp — mỗi 10 phút) rồi theo dõi log cả 2 worker cùng lúc, xác nhận
batch được chia cho cả 2 máy chứ không dồn hết vào 1 bên.

## Khi hub là VPS (không phải máy dev local)

Khác biệt duy nhất: VPS chưa chắc có Tailscale sẵn — cài như máy 2 ở mục 2
(`curl -fsSL https://tailscale.com/install.sh | sh && tailscale up`), rồi
dùng IP tailnet của VPS (không phải IP public thật) cho `LAN_BIND_IP` (hub)
và `HUB_HOST` (worker). Luồng deploy code cho hub vẫn theo
[`vps-deploy.md`](vps-deploy.md) như bình thường; máy worker là 1 checkout
git riêng, cập nhật độc lập:

```bash
git pull
docker compose -f docker-compose.worker.yml build fb-celery-worker
docker compose -f docker-compose.worker.yml up -d
```

## Cập nhật code sau này

Máy worker không tự nhận code mới — mỗi lần `platform_app/`/`crawling_facebook/`
đổi, chạy lại trên máy 2:

```bash
git pull
docker compose -f docker-compose.worker.yml up -d --build
```
