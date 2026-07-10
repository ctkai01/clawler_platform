# Sơ đồ flow chạy DAG (Airflow)

## Tổng quan

```mermaid
flowchart TD
    subgraph Crawl["4 DAG crawl — chạy theo lịch cố định"]
        FBG["facebook_groups_crawl<br/>*/10 phút · queue fb_crawler"]
        FBP["facebook_pages_crawl<br/>*/10 phút · queue fb_crawler"]
        FORUM["forums_crawl<br/>*/5 phút · queue http_crawler"]
        NEWS["news_crawl<br/>*/5 phút · queue http_crawler"]
    end

    CP["content_pipeline<br/>schedule=None (chỉ chạy khi được trigger)"]

    FBG -- "trigger khi crawl xong" --> CP
    FBP -- "trigger khi crawl xong" --> CP
    FORUM -- "trigger khi crawl xong" --> CP
    NEWS -- "trigger khi crawl xong" --> CP

    subgraph Pipeline["Bên trong content_pipeline"]
        KF["keyword_filter<br/>(cổng chi phí, free)"]
        CL["classify<br/>(LLM, chỉ chạy trên bài đã match)"]
        EM["entity_match<br/>(free, chạy độc lập)"]
        TT["topic_tag<br/>(free, chạy độc lập)"]
        KF --> CL
    end

    CP --> KF
    CP --> EM
    CP --> TT
```

## Chi tiết từng DAG crawl

Cả 4 DAG đều có cấu trúc 3 task giống nhau:

```mermaid
flowchart LR
    A["get_due_targets()<br/>queue: http_crawler<br/>lấy tối đa 50 nguồn đang tới hạn<br/>(last_crawled_at NULL hoặc quá crawl_interval_sec)"]
    B["crawl_one.expand(target=...)<br/>Airflow dynamic task mapping<br/>— chạy song song theo giới hạn queue/pool"]
    C["trigger_content_pipeline()<br/>queue: http_crawler, trigger_rule=all_done<br/>tự trigger content_pipeline, bỏ qua nếu<br/>DagRunAlreadyExists (DAG khác vừa trigger rồi)"]
    A --> B --> C
```

`get_due_targets` chỉ trả về **tối đa 50 nguồn/lần chạy** (`BATCH_CAP`) — nếu
backlog nhiều hơn (vd vừa import CSV hàng loạt), phải mất thêm vài chu kỳ mới
crawl hết.

## Queue & giới hạn song song

| Queue | Worker | Concurrency | Dùng cho |
|---|---|---|---|
| `fb_crawler` | `airflow-worker-fb` | 3 (`fb_playwright_pool`) | `crawl_one` của FB Group/Page — nặng, cần Playwright/Chromium thật |
| `http_crawler` | `airflow-worker-http` | 30 (`http_pool`) | `get_due_targets`, `trigger_content_pipeline`, toàn bộ `content_pipeline`, `crawl_one` của Forum/News — nhẹ, HTTP thuần |

`crawl_one` của FB Group/Page còn bị giới hạn thêm bởi **số tài khoản
Facebook** đang có trong pool session (xem
[`fb-session-pool.md`](fb-session-pool.md)) — Page tự động round-robin giữa
các tài khoản, Group phải gán thủ công 1 tài khoản cụ thể (do yêu cầu đã là
thành viên group).

## Bên trong `crawl_one` khi target là FB Group/Page

```mermaid
flowchart TD
    A["crawl_target(target_id)<br/>platform_app/crawlers/facebook_runner.py"]
    B["_resolve_session_path(target)<br/>chọn file session/tài khoản FB sẽ dùng<br/>(xem fb-session-pool.md)"]
    C["fetch_page_name / fetch_group_name<br/>xác nhận session còn sống —<br/>None ⇒ SessionExpiredError"]
    D["discover_feed_post_urls()<br/>cuộn feed tối đa max_scrolls vòng,<br/>tự dừng sớm khi 2 vòng liên tiếp<br/>không thấy bài mới"]
    E["known_post_ids()<br/>lấy toàn bộ post_id đã có trong DB<br/>cho target này (1 query)"]
    F["list_posts_to_recheck()<br/>tối đa 25 bài ≤48h có comment,<br/>cần kiểm tra lại comment mới"]
    G["Lọc: chỉ giữ bài MỚI (chưa có trong DB)<br/>hoặc bài thuộc diện recheck —<br/>bỏ qua bài cũ đã ổn định"]
    H["fetch_posts_from_urls()<br/>mở từng bài (concurrency=3):<br/>load trang, thử phát video,<br/>mở rộng bình luận (≤max_comments)"]
    I["Lưu vào documents/document_comments<br/>(PgStorage)"]

    A --> B --> C --> D
    D --> E
    D --> F
    E --> G
    F --> G
    G --> H --> I
```

Trước đây bước **G** không tồn tại — mọi bài còn hiện trong feed đều bị fetch
lại toàn bộ (kể cả bài đã biết, đã ổn định), đây là phần tốn thời gian nhất
của cả DAG. Giờ chỉ fetch bài thật sự mới hoặc bài cần kiểm tra lại.

`discover_feed_post_urls`/`fetch_posts_from_urls` chạy trên 1 trình duyệt
Playwright có cấu hình chống bị nhận diện là bot: `user_agent` giống Chrome
desktop thật, `timezone_id: Asia/Ho_Chi_Minh` khớp `locale: vi-VN`, không
chặn tải font (trước đây có chặn).

## Vì sao `content_pipeline` không chạy theo lịch riêng

`content_pipeline` có `schedule=None` — **chỉ chạy khi được 1 trong 4 DAG
crawl trigger** ở cuối, thay vì tự poll theo lịch cố định (cách cũ, đã bỏ vì
lãng phí — DAG chạy dù không có gì mới để xử lý). Khi 2+ DAG crawl hoàn thành
gần như cùng lúc, `trigger_dag()` được gọi với `execution_date` chính xác tới
microsecond (`replace_microseconds=False`) để tránh đụng độ; nếu vẫn đụng
(cực hiếm), DAG gọi sau chỉ bắt `DagRunAlreadyExists` và bỏ qua — mục tiêu
(content_pipeline chạy) đã đạt được bởi DAG kia rồi.

## Bên trong `content_pipeline`

- `keyword_filter` → `classify`: **tuần tự** — `classify` (gọi LLM, tốn tiền)
  chỉ chạy trên document đã được `keyword_filter` đánh dấu `matched` (lọc
  theo `organization_keywords`/`keywords_catalog` của từng tổ chức).
- `entity_match`, `topic_tag`: **độc lập**, không phụ thuộc `keyword_filter`
  — chạy trên toàn bộ document mới, miễn phí (không gọi LLM).

Xem chi tiết đầy đủ 4 cơ chế này ở
[`classification-pipeline.md`](classification-pipeline.md).
