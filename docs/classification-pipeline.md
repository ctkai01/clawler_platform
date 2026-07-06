# Cơ chế phân loại bài viết

Sau khi crawl xong, mỗi document đi qua 4 cơ chế phân loại **độc lập với nhau**,
chạy tự động trong Airflow DAG `content_pipeline` (`airflow/dags/dag_content_pipeline.py`,
lịch mỗi 10 phút). Bốn cơ chế trả lời 4 câu hỏi khác nhau, dùng dữ liệu khác nhau,
và phục vụ các phần khác nhau của UI.

```
keyword_filter (cost gate)
      │
      ▼
   classify (LLM / rule-based sentiment)

entity_match       (chạy độc lập, không phụ thuộc keyword_filter)
topic_tag          (chạy độc lập, không phụ thuộc keyword_filter)
```

| | keyword_filter | classify | entity_match | topic_tag |
|---|---|---|---|---|
| Trả lời câu hỏi | "Bài này có liên quan gì đến ngành/brand không?" | "Sắc thái (tích cực/tiêu cực/trung tính) và mức độ nghiêm trọng?" | "Bài này nhắc tới thương hiệu/công ty nào?" | "Bài này thuộc chủ đề nghiệp vụ nào?" |
| Phạm vi dữ liệu | **Theo từng tổ chức** (`organization_keywords` → `keywords_catalog`); legacy target không thuộc org nào (`organization_id IS NULL`) vẫn dùng `config/keywords.yaml` chung | Global code, nhưng **mode** cấu hình theo từng org | Global (`entity_gazetteer`), lọc hiển thị theo org đã "chọn theo dõi" | **Theo từng tổ chức** (`organization_topics`) |
| Ai quản lý nội dung | Admin tạo trong `/admin/keywords`, tổ chức tự chọn ở trang chọn Entity/Keyword | Org (`org_main`, trang Cài đặt) chọn mode | Admin (`/admin/entities`) | Admin (`/admin/topics`), nhập tay hoặc import CSV |
| Số nhãn / bài | 1 boolean (matched/no_match) | 1 category + 1 sentiment + 1 severity | Nhiều (1 bài có thể nhắc nhiều thương hiệu) | **Đúng 1** chủ đề (hoặc "KHÁC") |
| Có tốn tiền không | Không | Có (LLM modes) | Không | Không |
| Cổng chặn bài nào chạy classify | **Chính là cổng này** | — | — | — |
| Lưu ở đâu | `documents.keyword_status`, `matched_keywords` | `documents.classification_*` | `document_entities` (bảng riêng, nhiều dòng/bài) | `documents.topic_tag_id`, `topic_tag_status` |
| Hiện ở đâu trên UI | (không hiện trực tiếp, chỉ là cổng nội bộ) | Badge sắc thái trên Documents/Report, filter theo sentiment | Report mục **II. Theo chủ đề (entity)**, badge entity trong Detail Panel, network graph | Report mục **III. Theo chủ đề (từ khóa)** |

---

## 1. `keyword_filter` — cổng lọc chi phí (Stage 1)

**File:** `platform_app/pipeline/keyword_filter.py`. Từ khóa nằm trong DB:
bảng `keywords_catalog` (admin tạo qua `/admin/keywords`, category
brand/competitor/industry/custom) + bảng `organization_keywords` (tổ chức tự
chọn dùng cái nào, qua trang chọn Entity/Keyword — trước đây lựa chọn này
**không có tác dụng thật**, giờ mới là nguồn dữ liệu chính thức cho cổng này).

Việc duy nhất của bước này: quyết định bài viết có **đáng để tốn tiền gọi LLM
phân loại hay không**. Không phải phân loại thật — chỉ là bộ lọc thô.

- Mỗi document mới (`keyword_status = 'pending'`) được so khớp với **đúng bộ
  từ khóa tổ chức đó đã chọn** (không dùng chung 1 danh sách cho mọi tổ
  chức): khớp **bất kỳ** từ khóa nào → `keyword_status = 'matched'` (lưu
  danh sách từ khóa khớp vào `matched_keywords`); không khớp gì → `no_match`.
- Tổ chức chưa chọn từ khóa nào → **không bài nào của họ được `matched`**,
  tức không bài nào từng được phân loại sắc thái — không tự "mượn" từ khóa
  của tổ chức khác.
- Ngoại lệ: crawl target không gắn tổ chức nào (`organization_id IS NULL`
  — dùng bởi dashboard nội bộ, có trước cả mô hình multi-tenant) vẫn dùng
  `config/keywords.yaml` như cũ, để không phá vỡ dashboard đó.
- **Chỉ document `matched` mới được đưa sang bước `classify`** — đây là lý do
  gọi là "cost gate".

## 2. `classify` — phân loại sắc thái (chỉ chạy trên bài đã "matched")

**File:** `platform_app/pipeline/classify.py`. Mode cấu hình per-org tại
`platform_app/pipeline/settings.py` (bảng `pipeline_settings`, cột
`organization_id`) — sửa qua trang **Cài đặt** (org_main).

3 mode:

- **normal** — rule-based bằng từ khóa + 1 bộ từ điển cảm xúc có sẵn
  (`csv/dataset_1000_tu_khoa_cam_xuc.csv`), miễn phí, không gọi LLM.
- **llm_text** — gửi tiêu đề + nội dung (cắt 4000 ký tự) cho LLM (mặc định
  `gpt-4o-mini`), LLM trả về category/sentiment/severity/reasoning.
- **llm_image** — như trên nhưng gửi kèm tối đa 3 ảnh của bài viết (chỉ áp
  dụng khi bài có ảnh, không thì tự rơi về llm_text).

Không có `mode` override (trường hợp DAG chạy tự động) thì mỗi tổ chức được
xử lý **riêng biệt theo đúng mode tổ chức đó đang chọn** — tổ chức A dùng
`normal`, tổ chức B dùng `llm_text` cùng lúc không ảnh hưởng nhau.

Kết quả ghi vào `documents.classification_category`,
`classification_sentiment`, `classification_severity`, `classification_reasoning`,
`classification_cost_usd` (tích lũy chi phí LLM thật đã gọi).

## 3. `entity_match` — gắn thương hiệu/công ty được nhắc tới

**File:** `platform_app/pipeline/entity_match.py`, dữ liệu tại `entity_gazetteer`
(quản lý qua `/admin/entities`).

- Chạy trên **mọi** document (không cần `keyword_status = 'matched'`), vì đây
  là dữ liệu miễn phí (rule-based), không liên quan tới cổng chi phí LLM.
- So khớp text bài viết với **surface form** của từng thương hiệu trong
  gazetteer (1 thương hiệu có nhiều surface form — "MobiFone", "mobifone",
  "Mobi Fone"...).
- **1 bài có thể khớp nhiều thương hiệu cùng lúc** — ghi nhiều dòng vào bảng
  `document_entities` (document_id, concept_id, canonical_name). Không khớp
  gì thì ghi 1 dòng sentinel `__none__` để không bị quét lại ở lần chạy sau.
- `organization_entities` là danh sách thương hiệu tổ chức đã "chọn theo dõi"
  — chỉ dùng để **lọc hiển thị** (report, badge, network graph chỉ hiện
  thương hiệu tổ chức quan tâm), KHÔNG ảnh hưởng việc gazetteer có gắn nhãn
  hay không (gazetteer luôn gắn nhãn theo toàn bộ danh mục).

Dùng cho mục **"II. Thông tin theo chủ đề (entity)"** trong Report, badge
entity + network đồ thị trong Detail Panel.

## 4. `topic_tag` — gắn chủ đề nghiệp vụ theo từ khóa (mới)

**File:** `platform_app/pipeline/topic_tag.py`, dữ liệu tại
`organization_topics` + `organization_topic_keywords` (quản lý qua
`/admin/topics`, nhập tay hoặc import CSV).

- Khác `entity_match` ở 2 điểm: (a) **theo từng tổ chức** — mỗi tổ chức có bộ
  chủ đề/từ khóa hoàn toàn riêng, không dùng chung; (b) **1 bài chỉ thuộc
  đúng 1 chủ đề** (không phải nhiều như entity).
- Chạy trên mọi document của tổ chức có ít nhất 1 chủ đề được cấu hình
  (không cần `keyword_status = 'matched'`, miễn phí).
- Với mỗi bài: đếm số lần khớp từ khóa của từng chủ đề trong
  (tiêu đề + nội dung, đã fold bỏ dấu/viết thường) → **chủ đề có tổng số
  lần khớp cao nhất thắng** → ghi `documents.topic_tag_id`. Không chủ đề nào
  khớp → `topic_tag_status = 'none'` (hiển thị là **"KHÁC"** trong report).
- `topic_tag_status` (`pending` / `tagged` / `none`) tồn tại để phân biệt
  "chưa xử lý" với "đã xử lý, không khớp gì" — nếu không có cột này thì cả
  2 trường hợp đều là `topic_tag_id = NULL`, không phân biệt được.
- **Mỗi khi admin thêm/sửa/xoá chủ đề hoặc từ khóa** (kể cả import CSV),
  toàn bộ document của tổ chức đó bị reset về `topic_tag_status = 'pending'`
  để lần chạy tiếp theo tính lại theo luật mới — không cần thao tác gì thêm.

Dùng cho mục **"III. Thông tin theo chủ đề (từ khóa)"** trong Report + sheet
"Theo chủ đề (từ khóa)" trong file Excel xuất ra.

---

## Vì sao có tới 3 cơ chế "theo chủ đề" khác nhau (keyword_filter / entity_match / topic_tag)?

Chúng giải quyết 3 bài toán khác nhau dù đều dựa trên so khớp từ khóa/tên:

- **keyword_filter**: "có nên tốn tiền phân tích bài này không" — chỉ cần
  biết có/không, không cần biết khớp cái gì.
- **entity_match**: "bài này nhắc tới công ty/thương hiệu nào" — dữ liệu
  dùng chung toàn hệ thống (1 gazetteer thương hiệu cho mọi ngành), 1 bài có
  thể nhắc nhiều thương hiệu.
- **topic_tag**: "theo cách phân loại nội bộ riêng của tổ chức này, bài này
  thuộc mảng nào" — mỗi tổ chức có taxonomy hoàn toàn khác nhau (viễn thông
  khác ngân hàng khác FMCG), và cần đúng 1 nhãn/bài để cộng dồn báo cáo không
  bị đếm trùng.

Nhập nhằng 3 cái này vào 1 bảng sẽ làm hỏng ngữ nghĩa của cả 3 (ví dụ:
keyword_filter cần giữ nguyên là cổng chi phí toàn hệ thống, không thể biến
thành theo-org mà không phá vỡ mô hình cost-gate hiện tại).
