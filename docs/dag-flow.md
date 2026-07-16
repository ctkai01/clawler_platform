# Sơ đồ flow chạy DAG (Airflow) + crawl Facebook

FB Group/Page và Forum/News đi theo 2 luồng khác hẳn nhau kể từ khi FB
chuyển sang RabbitMQ + `fb-celery-worker` (Airflow không còn chạy Playwright
trực tiếp). Đọc đúng phần áp dụng cho loại nguồn bạn đang quan tâm.

## Tổng quan

```mermaid
flowchart TD
    subgraph FB["FB Group/Page — RabbitMQ + fb-celery-worker"]
        FBG["facebook_groups_crawl<br/>*/10 phút"]
        FBP["facebook_pages_crawl<br/>*/10 phút"]
        MQ[["RabbitMQ queue fb_crawl"]]
        W["1+ fb-celery-worker<br/>(hub + máy khác qua Tailscale)"]
        FBG -- "dispatch() publish batch" --> MQ
        FBP -- "dispatch() publish batch" --> MQ
        MQ --> W
    end

    subgraph HTTP["Forum/News — Airflow thuần"]
        FORUM["forums_crawl<br/>*/5 phút · queue http_crawler"]
        NEWS["news_crawl<br/>*/5 phút · queue http_crawler"]
    end

    CP["content_pipeline<br/>schedule=None (chỉ chạy khi được trigger)"]

    FBG -. "trigger ngay sau dispatch,<br/>KHÔNG đợi crawl xong" .-> CP
    FBP -. "trigger ngay sau dispatch,<br/>KHÔNG đợi crawl xong" .-> CP
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

## FB Group/Page

### 1. Dispatch (Airflow, queue `http_crawler` — nhẹ, không Playwright)

```mermaid
flowchart LR
    A["dispatch()<br/>dispatch_due_sources(platform_type)"]
    B["Lấy tối đa 200 nguồn tới hạn<br/>(crawl_interval_sec)"]
    C["Khoá Redis từng nguồn<br/>(tránh dispatch trùng)"]
    D["Gom theo fb_session_key,<br/>chia batch tối đa 10 nguồn"]
    E[["Publish crawl_batch_task<br/>lên RabbitMQ (queue fb_crawl)"]]
    F["trigger_content_pipeline()<br/>chạy NGAY, không đợi crawl xong"]
    A --> B --> C --> D --> E
    A --> F
```

`platform_app/crawlers/dispatch_tasks.py` — `dispatch_due_sources()` chỉ
query Postgres và publish message, **không** import Playwright (queue
`http_crawler` không có Chromium). Việc crawl thật xảy ra bất đồng bộ ở
`fb-celery-worker`, ngoài tầm nhìn của Airflow — vì vậy
`trigger_content_pipeline()` bắn ngay sau dispatch, xử lý dữ liệu của batch
**trước đó** đã crawl xong, không phải batch vừa dispatch.

Gom nhóm theo `fb_session_key`: nguồn cùng key (kể cả `NULL` — chưa gán
cũng tính 1 nhóm) rơi vào chung batch. Group **cần được gán cụ thể** (do
phải là thành viên mới đọc được nội dung) — hiện tất cả FB Group đều đang
`fb_session_key = NULL`, bị crawl bằng account round-robin ngẫu nhiên như
Page, dễ gây lỗi/crawl rỗng nếu account đó chưa join group.

### 2. `fb-celery-worker` (1+ instance, có thể chạy trên nhiều máy)

```mermaid
flowchart TD
    A["crawl_batch_task(platform_type, target_ids, session_key)"]
    B["AccountPool.acquire_specific(key) / acquire()<br/>— account LIVE, cooldown 15p<br/>(FB_ACCOUNT_COOLDOWN_MINUTES)"]
    C["ProxyPool.acquire() — round-robin,<br/>đổi IP nếu proxy có reset_url"]
    D["1 browser Playwright dùng chung cả batch<br/>storage_state = fb_accounts.session_data (Postgres)"]
    E["Với từng target: cuộn feed → lọc bài mới/<br/>cần recheck comment → fetch chi tiết → lưu DB"]
    F["CheckpointError: dừng cả batch,<br/>account → CHECKPOINT (cách ly)"]
    G["Lỗi khác (session_expired/not_a_member):<br/>chỉ tính riêng target đó, batch tiếp tục"]

    A --> B --> C --> D --> E
    E -.-> F
    E -.-> G
```

`platform_app/crawlers/batch_tasks.py` (`crawl_batch_task`) +
`account_pool.py` + `proxy_pool.py`. Nhiều worker cùng consume 1 queue
`fb_crawl` (RabbitMQ tự chia — competing consumer, không cấu hình cứng
worker nào nhận batch nào) — an toàn khi chạy song song vì `AccountPool`
khoá theo dòng Postgres (`FOR UPDATE SKIP LOCKED`), không có 2 batch nào
tranh được cùng 1 account.

Chi tiết chạy 1 worker trên máy khác qua Tailscale:
[`fb-worker-remote.md`](fb-worker-remote.md). Chi tiết session/account pool:
[`fb-session-pool.md`](fb-session-pool.md).

### Giới hạn thông lượng thật sự

Bị chặn bởi **số account**, không phải số worker/concurrency: mỗi account
cooldown 15 phút giữa 2 lần dùng → tối đa `(số account) × 4` batch/giờ, mỗi
batch 10 nguồn. Ví dụ với 5 account: tối đa 20 batch/giờ = 200 nguồn/giờ —
dù có bao nhiêu worker/slot rảnh cũng không vượt được mốc này. Tăng
`FB_CELERY_CONCURRENCY` hay thêm worker chỉ có ích khi số account đủ để lấp
đầy các slot đó; nếu ít account mà tăng concurrency quá cao, các slot dư chỉ
nhận "không có account khả dụng" và bỏ qua, không tốn tài nguyên thật (chưa
mở browser) nhưng cũng không tăng tốc.

## Forum/News

Vẫn giữ nguyên cấu trúc cũ, chạy hoàn toàn trong Airflow — 3 task giống nhau
cho cả 2 DAG:

```mermaid
flowchart LR
    A["get_due_targets()<br/>queue: http_crawler<br/>lấy tối đa 100 nguồn tới hạn<br/>(BATCH_CAP)"]
    B["crawl_one.expand(target=...)<br/>pool http_pool, concurrency 30<br/>— HTTP thuần, không cần Playwright"]
    C["trigger_content_pipeline()<br/>trigger_rule=all_done<br/>chỉ trigger SAU KHI crawl xong thật"]
    A --> B --> C
```

`get_due_targets` trả tối đa 100 nguồn/lần chạy (`BATCH_CAP` trong
`dag_forums.py`/`dag_news.py`) — nếu backlog nhiều hơn (vd vừa import CSV
hàng loạt), mất thêm vài chu kỳ mới crawl hết.

## Vì sao `content_pipeline` không chạy theo lịch riêng

`content_pipeline` có `schedule=None` — chỉ chạy khi 1 trong 4 DAG crawl
trigger nó ở cuối, thay vì tự poll theo lịch cố định (cách cũ, đã bỏ vì lãng
phí — DAG chạy dù không có gì mới để xử lý). Khi 2+ DAG trigger gần như cùng
lúc, `trigger_dag()` dùng `execution_date` chính xác tới microsecond
(`replace_microseconds=False`) để tránh đụng độ; nếu vẫn đụng (cực hiếm),
DAG gọi sau chỉ bắt `DagRunAlreadyExists` và bỏ qua — mục tiêu
(content_pipeline chạy) đã đạt được bởi DAG kia rồi.

**Lưu ý riêng cho FB** (khác Forum/News): trigger bắn ngay sau *dispatch*,
không đợi *crawl* xong thật (xem mục "FB Group/Page" ở trên) — vì crawl FB
giờ chạy bất đồng bộ ngoài Airflow.

## Bên trong `content_pipeline`

- `keyword_filter` → `classify`: **tuần tự** — `classify` (gọi LLM, tốn tiền)
  chỉ chạy trên document đã được `keyword_filter` đánh dấu `matched` (lọc
  theo `organization_keywords`/`keywords_catalog` của từng tổ chức).
- `entity_match`, `topic_tag`: **độc lập**, không phụ thuộc `keyword_filter`
  — chạy trên toàn bộ document mới, miễn phí (không gọi LLM).

Xem chi tiết đầy đủ 4 cơ chế này ở
[`classification-pipeline.md`](classification-pipeline.md).
