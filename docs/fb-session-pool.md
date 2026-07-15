# Xoay vòng nhiều tài khoản Facebook cho crawl

Mặc định hệ thống crawl FB Group/Page bằng **đúng 1 tài khoản** (file
`secrets/fb_session.json`) — không cần làm gì thêm, mọi thứ hoạt động y hệt
trước khi có tài liệu này. Phần dưới đây chỉ áp dụng khi bạn muốn **thêm tài
khoản thứ 2 trở lên** để giảm rủi ro 1 tài khoản bị Facebook giới hạn/chặn khi
số lượng nguồn crawl tăng.

## Cơ chế

- Session sống trong thư mục `secrets/fb_sessions/*.json` (mỗi file = 1 tài
  khoản, tên file không đuôi `.json` = "session key", vd `acc1.json` →
  key `acc1`).
- **FB Page** (nội dung công khai): nếu không gán `fb_session_key` cho target,
  hệ thống **tự động round-robin** giữa các session đang có (`target_id %
  số_session`) — không cần thao tác gì thêm khi thêm Page mới.
- **FB Group** (đặc biệt group kín): tài khoản crawl phải **là thành viên**
  group thì mới thấy nội dung → **bắt buộc gán thủ công** `fb_session_key`
  cho từng group khi có từ 2 session trở lên (không tự đoán được tài khoản
  nào đã join group nào).
- Chỉ khi thư mục `fb_sessions/` **không tồn tại** (setup mặc định hiện tại),
  hệ thống fallback về file `fb_session.json` cũ — đúng hành vi trước đây.

## Thêm 1 tài khoản mới

**1. Đăng nhập, lưu session** — chạy ở máy có màn hình/trình duyệt (không
chạy được trên VPS headless), trong thư mục `crawling_facebook`:
```bash
python -m fb_crawl.cli login --session ./fb_sessions/accN.json
```
Trình duyệt hiện ra → đăng nhập bằng tài khoản Facebook mới → chờ lưu xong.

**2. Import vào DB** — session sống trong `fb_accounts.session_data`
(Postgres), không phải file, nên chạy script này (trong container `api`,
cần kết nối DB):

```bash
docker compose exec -T api python scripts/import_fb_sessions_to_db.py accN
```

(Không tham số = import toàn bộ `secrets/fb_sessions/*.json` cùng lúc, hữu
ích lần đầu migrate cả pool.)

**3. Không cần restart gì** — `AccountPool` đọc `fb_accounts` trực tiếp mỗi
lần acquire một batch mới, không cache, nên session mới có hiệu lực ngay từ
batch tiếp theo.

**4. Với Page mới**: không cần làm gì thêm — tự động vào vòng xoay.

**5. Với Group mới (hoặc muốn ghim 1 group cho accN cụ thể)**: dùng tài khoản
accN **join group đó thủ công trước** (qua trình duyệt), rồi gán trong DB:
```bash
docker compose exec -T postgres psql -U crawler -d crawl_platform -c \
  "UPDATE crawl_targets SET fb_session_key = 'accN' WHERE id = <target_id>;"
```

## Kiểm tra đã hoạt động

Xem log lần crawl gần nhất của 1 target, tìm dòng `Crawled target ...` —
không có cách trực tiếp in ra session key trong log hiện tại, nhưng có thể xác
nhận gián tiếp: nếu 1 tài khoản bị Facebook chặn, chỉ các target gán/rơi vào
đúng session đó sẽ đồng loạt lỗi `session_expired` — xem trang **Giám sát**
(`/tracking/monitoring`) → bảng "Danh sách lỗi cần xử lý" → cột "Tài khoản FB"
để biết chính xác tài khoản nào cần đăng nhập lại (chỉ hiện được với target đã
gán `fb_session_key` thủ công; Page tự động round-robin không lưu lại đã dùng
key nào ở lần crawl gần nhất).

## Lưu ý

- Tài khoản mới nên "làm nóng" dần — không gán ngay hàng chục Page/Group từ
  ngày đầu, dễ bị Facebook đánh dấu bất thường.
- Không tăng `fb_playwright_pool`/`airflow-worker-fb --concurrency` (đang =3)
  song song với việc thêm tài khoản — đó là giới hạn tài nguyên VPS (CPU/RAM),
  không liên quan tới số tài khoản.
