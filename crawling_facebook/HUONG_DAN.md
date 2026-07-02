# Hướng dẫn cài đặt và chạy crawling-facebook

Công cụ crawl bài viết Facebook **Group** và **Page** bằng Playwright (Chromium headless). Kết quả được lọc theo bài mới (**48 giờ**) hoặc comment mới (**60 phút**), lưu JSON và SQLite.

---

## Mục lục

1. [Yêu cầu hệ thống](#1-yêu-cầu-hệ-thống)
2. [Cài đặt trên máy mới](#2-cài-đặt-trên-máy-mới)
3. [Quy trình chạy lần đầu](#3-quy-trình-chạy-lần-đầu)
4. [Đăng nhập Facebook](#4-đăng-nhập-facebook)
5. [Tham số chung (global)](#5-tham-số-chung-global)
6. [Crawl Facebook Group](#6-crawl-facebook-group)
7. [Crawl Facebook Page](#7-crawl-facebook-page)
8. [Logic lọc và parse thời gian](#8-logic-lọc-và-parse-thời-gian)
9. [Gợi ý chọn tham số](#9-gợi-ý-chọn-tham-số)
10. [File và thư mục quan trọng](#10-file-và-thư-mục-quan-trọng)
11. [Xử lý lỗi thường gặp](#11-xử-lý-lỗi-thường-gặp)
12. [Tóm tắt lệnh nhanh](#12-tóm-tắt-lệnh-nhanh)

---

## 1. Yêu cầu hệ thống

| Thành phần | Yêu cầu |
|------------|---------|
| Python | **3.11+** (khuyến nghị 3.12) |
| Hệ điều hành | Windows 10/11, macOS, Linux |
| Mạng | Truy cập được `facebook.com` |
| Tài khoản | Facebook (đăng nhập thủ công một lần, lưu session) |
| Dung lượng | ~500 MB cho Chromium (Playwright) |

---

## 2. Cài đặt trên máy mới

### 2.1. Windows — Anaconda (khuyến nghị)

```powershell
# 1. Vào thư mục project
cd C:\Users\<TEN_USER>\Desktop\crawling_facebook

# 2. Tạo và kích hoạt môi trường
conda create -n fb_crawl python=3.12 -y
conda activate fb_crawl

# 3. Cài package và Chromium
pip install -U pip
pip install -e .
playwright install chromium

# 4. Kiểm tra
python -m fb_crawl.cli --help
```

> **Lưu ý Windows:** dùng `conda activate fb_crawl` rồi chạy lệnh trực tiếp. Tránh `conda run` nếu gặp lỗi encoding.
>
> Nếu `fb-crawl` không nhận lệnh → dùng `python -m fb_crawl.cli` thay thế.

---

### 2.2. Windows — venv (không dùng Anaconda)

```powershell
cd C:\path\to\crawling_facebook
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U pip
pip install -e .
playwright install chromium
```

---

### 2.3. macOS / Linux

```bash
cd /path/to/crawling_facebook
./scripts/setup.sh
```

Hoặc thủ công:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
playwright install chromium
```

**macOS (Apple Silicon)** — nếu thiếu browser:

```bash
export PLAYWRIGHT_BROWSERS_PATH="$HOME/Library/Caches/ms-playwright"
playwright install chromium
```

---

### 2.4. Cập nhật sau khi pull code mới

```powershell
conda activate fb_crawl
cd C:\path\to\crawling_facebook
pip install -e .
```

---

## 3. Quy trình chạy lần đầu

```
Cài đặt → Login Facebook → Crawl Group hoặc Page → Đọc file JSON output
```

| Bước | Lệnh | Tần suất |
|------|------|----------|
| 1. Login | `python -m fb_crawl.cli login` | Một lần (hoặc khi session hết hạn) |
| 2. Crawl Group | `python -m fb_crawl.cli crawl-group "URL" -o output\group_result.json` | Theo lịch |
| 3. Crawl Page | `python -m fb_crawl.cli crawl-page "URL" -o output\page_result.json` | Theo lịch |

---

## 4. Đăng nhập Facebook

Mở trình duyệt → đăng nhập thủ công → session lưu tại `~/.fb_crawl/fb_session.json`.

### Lệnh cơ bản

```powershell
conda activate fb_crawl
cd C:\path\to\crawling_facebook
python -m fb_crawl.cli login
```

### Lệnh đầy đủ tham số

```powershell
python -m fb_crawl.cli ^
  --db "%USERPROFILE%\.fb_crawl\facebook.db" ^
  --session "%USERPROFILE%\.fb_crawl\fb_session.json" ^
  -v ^
  login ^
  --timeout 600
```

| Tham số | Mặc định | Mô tả |
|---------|----------|-------|
| `--db` | `~/.fb_crawl/facebook.db` | Đường dẫn SQLite DB |
| `--session` | `~/.fb_crawl/fb_session.json` | File cookie/session Playwright |
| `-v`, `--verbose` | tắt | Log chi tiết (DEBUG) |
| `--timeout` | `300` | Thời gian chờ đăng nhập (giây) |

---

## 5. Tham số chung (global)

Áp dụng cho mọi lệnh: `login`, `crawl-group`, `crawl-page`, `crawl`.

| Tham số | Mặc định | Mô tả |
|---------|----------|-------|
| `--db` | `~/.fb_crawl/facebook.db` | SQLite lưu lịch sử bài viết, comment |
| `--session` | `~/.fb_crawl/fb_session.json` | File session đã login |
| `-v`, `--verbose` | tắt | Log DEBUG — xem số URL feed/recheck |

**Quan trọng:** `-v` phải đặt **trước** subcommand:

```powershell
python -m fb_crawl.cli -v crawl-group "URL" -o output\group_result.json
```

Log mẫu khi bật `-v`:

```
Discovered 23 post URLs on page beatvn.network
Crawl 27 URL (feed=23, recheck=4)
Fetching 27 posts (concurrency=2)
Đã lưu 27 bài viết → output\page_result.json
```

---

## 6. Crawl Facebook Group

### Lệnh

```powershell
python -m fb_crawl.cli crawl-group <GROUP_URL> [OPTIONS]
```

**Alias:** `crawl` (= `crawl-group`)

### Bảng tham số đầy đủ

| Tham số | Mặc định | Mô tả |
|---------|----------|-------|
| `target_url` | *(bắt buộc)* | URL nhóm, VD: `https://www.facebook.com/groups/380912805062832` |
| `-o`, `--output` | stdout | Ghi JSON ra file |
| `--new-post-hours` | `48` | Bài **mới** nếu đăng trong N giờ |
| `--recent-comment-minutes` | `60` | Bài có **comment mới** trong N phút |
| `--max-scrolls` | `50` | Số lần scroll feed khi tìm URL bài |
| `--max-comments` | `100` | Số comment tối đa mỗi bài |
| `--concurrency` | `3` | Số tab song song khi crawl từng bài |
| `--feed-only` | tắt | Chỉ crawl feed, bỏ recheck DB (nhanh hơn) |
| `--show-browser` | tắt | Hiện trình duyệt khi crawl |

### Lệnh mẫu — full tham số (Windows)

```powershell
conda activate fb_crawl
cd C:\path\to\crawling_facebook

python -m fb_crawl.cli ^
  --db "%USERPROFILE%\.fb_crawl\facebook.db" ^
  --session "%USERPROFILE%\.fb_crawl\fb_session.json" ^
  -v ^
  crawl-group ^
  "https://www.facebook.com/groups/380912805062832" ^
  -o output\group_result.json ^
  --new-post-hours 48 ^
  --recent-comment-minutes 60 ^
  --max-scrolls 10 ^
  --max-comments 100 ^
  --concurrency 3
```

### Ví dụ theo mục đích

**Monitor nhanh:**

```powershell
python -m fb_crawl.cli crawl-group "https://www.facebook.com/groups/380912805062832" ^
  -o output\group_result.json ^
  --max-scrolls 2 --max-comments 30 --feed-only --concurrency 1
```

**Crawl đầy đủ + theo dõi comment bài cũ:**

```powershell
python -m fb_crawl.cli -v crawl-group "https://www.facebook.com/groups/380912805062832" ^
  -o output\group_result.json ^
  --max-scrolls 10 --max-comments 100 --concurrency 3 ^
  --new-post-hours 48 --recent-comment-minutes 45
```

**macOS / Linux:**

```bash
./scripts/fb-crawl.sh -v crawl-group \
  'https://www.facebook.com/groups/380912805062832' \
  -o output/group_result.json \
  --new-post-hours 48 --recent-comment-minutes 60 \
  --max-scrolls 10 --max-comments 100 --concurrency 3
```

### Nguồn URL được crawl

| Nguồn | Khi nào |
|-------|---------|
| **Feed** | Scroll `--max-scrolls` lần, thu URL trên feed |
| **Recheck DB** | Bài có comment trong cửa sổ thời gian, tối đa 25 bài — **chỉ khi không dùng `--feed-only`** |

---

## 7. Crawl Facebook Page

### Lệnh

```powershell
python -m fb_crawl.cli crawl-page <PAGE_URL> [OPTIONS]
```

### Bảng tham số đầy đủ

Giống `crawl-group` (xem mục 6). Tham số `target_url` là URL Page:

| Ví dụ URL | Mô tả |
|-----------|-------|
| `https://www.facebook.com/beatvn.network` | Page theo slug |
| `https://www.facebook.com/profile.php?id=123456789` | Page theo ID số |

### Lệnh mẫu — full tham số (Windows)

```powershell
conda activate fb_crawl
cd C:\path\to\crawling_facebook

python -m fb_crawl.cli ^
  --db "%USERPROFILE%\.fb_crawl\facebook.db" ^
  --session "%USERPROFILE%\.fb_crawl\fb_session.json" ^
  -v ^
  crawl-page ^
  "https://www.facebook.com/beatvn.network" ^
  -o output\page_result.json ^
  --new-post-hours 48 ^
  --recent-comment-minutes 60 ^
  --max-scrolls 15 ^
  --max-comments 100 ^
  --concurrency 2
```

> **Khuyến nghị Page:** dùng `--max-scrolls 15` trở lên để lấy đủ bài trong 48h. Page đăng nhiều bài/ngày (như Beatvn) cần scroll sâu hơn Group.

**Page theo ID + monitor nhanh:**

```powershell
python -m fb_crawl.cli crawl-page "https://www.facebook.com/profile.php?id=123456789" ^
  -o output\page_result.json ^
  --max-scrolls 5 --max-comments 50 --feed-only --concurrency 2
```

**macOS / Linux:**

```bash
./scripts/fb-crawl.sh -v crawl-page \
  'https://www.facebook.com/beatvn.network' \
  -o output/page_result.json \
  --new-post-hours 48 --recent-comment-minutes 60 \
  --max-scrolls 15 --max-comments 100 --concurrency 2
```

### Kiểm tra thời gian bài trong output

```powershell
python -c "import json; d=json.load(open('output/page_result.json',encoding='utf-8')); [print(p['post_id'][:30], p.get('published_at'), p.get('filter_reason')) for p in d['posts']]"
```

---

## 8. Logic lọc và parse thời gian

### Điều kiện đưa bài vào JSON output

Một bài vào file JSON khi thỏa **một trong hai** điều kiện:

| `filter_reason` | Điều kiện |
|-----------------|-----------|
| `new_post` | Bài đăng trong `--new-post-hours` giờ (mặc định **48h**) |
| `recent_comments` | Có comment mới trong `--recent-comment-minutes` phút (mặc định **60 phút**) so với DB |

- Hai điều kiện **độc lập** — comment mới không phụ thuộc ngưỡng 48h của bài.
- Bài vừa trong 48h vừa có comment mới → ghi `new_post` (kiểm tra trước).
- Bài khác vẫn crawl và lưu DB nhưng **không** có trong JSON.

### Định dạng thời gian được hỗ trợ

Tool parse các chuỗi thời gian Facebook phổ biến:

| Hiển thị trên FB | Ví dụ |
|------------------|-------|
| Tương đối (VN) | `34 phút`, `2 giờ`, `1 ngày`, `vừa xong` |
| Tương đối (EN) | `34 min`, `2 hr`, `2 days ago`, `just now` |
| Hôm qua / Yesterday | `Hôm qua lúc 11:45`, `Yesterday at 11:45 AM` |
| Hôm nay / Today | `Hôm nay lúc 9:30`, `Today at 9:30 AM` |
| Ngày tháng | `18 tháng 6 lúc 11:45`, `June 18 at 11:45 AM` |
| Unix timestamp | `data-utime` trên thẻ `<abbr>` (nếu có) |

Kết quả lưu trong field `published_at` (ISO 8601 UTC) trong JSON.

---

## 9. Gợi ý chọn tham số

| Mục đích | Gợi ý |
|----------|-------|
| Monitor nhanh vài phút/lần | `--max-scrolls 2 --max-comments 30 --feed-only --concurrency 1` |
| Crawl Page nhiều bài/ngày | `--max-scrolls 15+ --concurrency 2` |
| Theo dõi comment mới trên bài cũ | Bỏ `--feed-only`, `--recent-comment-minutes 45`–`60` |
| Archive / crawl sâu | `--max-scrolls 20+ --max-comments 100` |
| Máy yếu / tránh rate limit FB | `--concurrency 1` hoặc `2` |
| Debug lỗi | `-v --show-browser` |

---

## 10. File và thư mục quan trọng

| Đường dẫn | Mô tả |
|-----------|-------|
| `~/.fb_crawl/fb_session.json` | Session đăng nhập Facebook |
| `~/.fb_crawl/facebook.db` | SQLite: bài viết, comment, lịch sử crawl |
| `output/group_result.json` | Output crawl group (tùy `-o`) |
| `output/page_result.json` | Output crawl page (tùy `-o`) |

**Windows:** `~` = `C:\Users\<TEN_USER>\`

### Cấu trúc JSON output (rút gọn)

```json
{
  "source_type": "page",
  "page_id": "beatvn.network",
  "page_url": "https://www.facebook.com/beatvn.network",
  "page_name": "Beatvn",
  "crawled_at": "2026-06-19T06:00:00+00:00",
  "post_count": 20,
  "posts": [
    {
      "post_id": "pfbid0v57LZtVBBW8MYrZPx3RgRrzMsGGzFtQdAnzBGrzW3p8hZ9gRGYi5Se66zdAcZ9VEl",
      "url": "https://www.facebook.com/beatvn.network/posts/pfbid0v57...",
      "published_at": "2026-06-18T11:45:00+00:00",
      "content": "...",
      "comments": [],
      "filter_reason": "new_post",
      "source_type": "page"
    }
  ]
}
```

---

## 11. Xử lý lỗi thường gặp

| Lỗi | Cách xử lý |
|-----|------------|
| `ModuleNotFoundError: fb_crawl` | `pip install -e .` trong thư mục project |
| `fb-crawl` không nhận lệnh | Dùng `python -m fb_crawl.cli` |
| Playwright thiếu browser | `playwright install chromium` |
| `Cannot navigate to invalid URL` | Dùng `"URL"` thay `'URL'` trên Windows; CLI tự strip dấu nháy thừa |
| Chỉ crawl được 1–2 bài | Tăng `--max-scrolls` (Page: 15+); chạy `-v` xem `Discovered N post URLs` |
| `post_count` thấp dù nhiều bài trên FB | Bài cũ hơn 48h không vào JSON; tăng `--new-post-hours` nếu cần |
| `published_at: null` | Bài vẫn có thể vào JSON; kiểm tra log `-v` |
| Crawl chậm | Thêm `--feed-only`; giảm `--concurrency` |
| Session hết hạn | `python -m fb_crawl.cli login` |
| `conda run` lỗi encoding | `conda activate fb_crawl` rồi chạy trực tiếp |

---

## 12. Tóm tắt lệnh nhanh

### Cài đặt (Windows Anaconda)

```powershell
conda create -n fb_crawl python=3.12 -y
conda activate fb_crawl
cd C:\path\to\crawling_facebook
pip install -e .
playwright install chromium
```

### Login

```powershell
python -m fb_crawl.cli login
```

### Crawl Group

```powershell
python -m fb_crawl.cli -v crawl-group "https://www.facebook.com/groups/GROUP_ID" ^
  -o output\group_result.json ^
  --new-post-hours 48 --recent-comment-minutes 60 ^
  --max-scrolls 10 --max-comments 100 --concurrency 3
```

### Crawl Page

```powershell
python -m fb_crawl.cli -v crawl-page "https://www.facebook.com/beatvn.network" ^
  -o output\page_result.json ^
  --new-post-hours 48 --recent-comment-minutes 60 ^
  --max-scrolls 15 --max-comments 100 --concurrency 2
```

### Xem help

```powershell
python -m fb_crawl.cli --help
python -m fb_crawl.cli login --help
python -m fb_crawl.cli crawl-group --help
python -m fb_crawl.cli crawl-page --help
```
