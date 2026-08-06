# DATA CONTRACT — Day 10 Data Pipeline & Observability

> Chốt tại CP0. Mọi thành viên code theo đúng file này.
> Sửa contract = phải thông báo cả nhóm + cập nhật file này + ghi vào `group_report.md`. Không sửa ngầm.

**Nguyên tắc gốc:** phần lớn contract dưới đây **không phải do nhóm tự chọn** — chúng bị ép bởi code đã có sẵn trong starter (`index.py`, `qa.py`, `metrics.py`, `config.py`). Cột 🔒 = bị code sẵn ép, cấm đổi. Cột 🔓 = nhóm tự quyết, đã chốt giá trị dưới đây.

---

## 0. Sơ đồ handoff

```text
Crossref API
  │
  │  Contract A — RAW SCHEMA          owner: R2 (Ingestion)
  ▼
data/raw/crossref_records.json  ──────────────────────────┐
  │                                                        │ (nguồn repair)
  │  Contract B — CLEAN SCHEMA        owner: R3 (Cleaning) │
  ▼                                                        │
data/clean/papers_clean.csv|json                           │
  │                    │                                   │
  │                    └──► Contract C — EVAL SCHEMA   owner: R5
  │                              data/eval/test_set.json    │
  │  (build index)                        │                │
  ▼                                       │                │
ChromaDB collection                       │                │
  │                                       ▼                │
  └──────────────► evaluate_pipeline ◄────┘                │
                          │                                │
                          ▼                                │
        Contract F — METRICS SCHEMA                        │
        Contract D — QUALITY / FRESHNESS                   │
        Contract E — CORRUPTION LOG ◄──── corruption ──────┘
```

---

## Contract A — RAW SCHEMA 🔒

**Owner:** R2 · **File:** `src/ingestion/crossref.py` · **Artifact:** `data/raw/crossref_records.json`

Bị ép bởi `@dataclass PaperRecord` đã có sẵn. **Cấm thêm/bớt/đổi tên field** — vì `load_raw_records` phải làm được `PaperRecord(**item)`.

| Field | Type | Bắt buộc | Nguồn Crossref | Rule chốt |
|---|---|---|---|---|
| `paper_id` | `str` | ✅ | `item["DOI"]` | **lowercase**, strip. Là stable ID xuyên suốt raw→clean→index→eval. Thiếu ⇒ **drop record** |
| `title` | `str` | ✅ | `item["title"][0]` | `normalize_whitespace`. Rỗng ⇒ **drop record** |
| `summary` | `str` | ✅ | `item["abstract"]` | Strip JATS XML (`<jats:p>`…), `html.unescape`, `normalize_whitespace`. `len < 80` ⇒ **drop record** |
| `authors` | `list[str]` | ❌ | `item["author"][]` | `f"{given} {family}".strip()`; bỏ phần tử rỗng; không có ⇒ `[]` |
| `categories` | `list[str]` | ❌ | `item["subject"]` | Không có ⇒ `[]` |
| `primary_category` | `str` | ✅ | `categories[0]` | Fallback `"uncategorized"` |
| `published` | `str` | ✅ | **`min(issued, created)`** — xem ghi chú dưới | Format **`YYYY-MM-DD`**. Thiếu tháng/ngày ⇒ điền `01`. Parse fail ⇒ **drop record**. `age_days > 180` ⇒ **drop record** |
| `updated` | `str` | ❌ | `item["deposited"]` → fallback `item["created"]` | `YYYY-MM-DD`, không có ⇒ `""` |
| `abs_url` | `str` | ❌ | `item["URL"]` | Không có ⇒ `""` |
| `pdf_url` | `str` | ❌ | `item["link"][]` có `content-type == "application/pdf"` | Không có ⇒ `""` |
| `comment` | `str` | ❌ | `item["container-title"][0]` → fallback `item["type"]` | Không có ⇒ `""` |

**Rule chung:** không field nào được là `None`. Thiếu ⇒ `""` hoặc `[]`, không phải `None`.

**Query đã chốt** (đọc từ `settings`, không hard-code):

| Param | Giá trị |
|---|---|
| endpoint | `https://api.crossref.org/works` |
| `query.bibliographic` | `settings.source_query` |
| `filter` | `settings.source_filter` = `from-pub-date:<today-180d>,has-abstract:true` |
| `rows` | `settings.max_results` = 24 |
| `sort` / `order` | **`relevance` / `desc`** — xem ghi chú dưới |
| `User-Agent` | `Day10DataLab/1.0 (mailto:<email nhóm>)` — Crossref yêu cầu polite pool |
| retry | 4 lần, backoff `2**attempt` giây, cho `429` / `500` / `502` / `503` / timeout |

**2 artifact bắt buộc:**
- `settings.paths.raw_api_response` — response JSON **thô, trước khi parse** (evidence lineage)
- `settings.paths.raw_records_json` — `[asdict(r) for r in records]`

**Rule bất biến:** sau CP1, **không refetch** source (trừ khi cả nhóm đồng ý). Đây là snapshot dùng cho cả baseline lẫn repair — refetch giữa chừng làm comparison mất công bằng.

### Ba quyết định dữ liệu đã kiểm chứng trên corpus thật

Cả ba đều phát hiện được khi chạy fetch lần đầu và đã sửa. Nêu trong `group_report.md` §5.

**1. `published = min(issued, created)`, không dùng thẳng `issued`.**
Crossref `issued` là ngày xuất bản **danh nghĩa do nhà xuất bản khai** và rất hay nằm ở tương lai (số tạp chí sắp phát hành). Lần chạy đầu cho ra `issued` = 2027–2028 trong khi `created` = 2026-05…07 ⇒ `age_days` từ **−679 đến −147**, toàn bộ freshness monitoring vô nghĩa. `created` là thời điểm bản ghi thực sự vào Crossref, luôn ở quá khứ. Sau khi sửa: `age_days` = 5…175.

**2. Áp lại cửa sổ tuổi trên ngày hiệu lực.**
Filter `from-pub-date` của Crossref áp trên `issued`, còn ta dùng `min(issued, created)` ⇒ một số bản ghi lọt qua filter nguồn nhưng ngày hiệu lực rơi ngoài 180 ngày. Không áp lại thì baseline có sẵn dòng stale và tín hiệu freshness **không còn phân biệt được baseline với corrupted**. `parse_crossref_payload(payload, max_age_days=...)` lọc lại. Sau khi sửa: baseline `stale_rows = 0`.

**3. `sort=relevance`, không phải `sort=published`.**
Sắp theo ngày chỉ lấy các bản ghi có `issued` xa nhất ở tương lai ⇒ corpus lần chạy đầu toàn *"Mind Reader Robot: an Arduino-Based Game"*, *"Augmented Reality in Teacher Education"* — không dính dáng gì tới query về agentic RAG. Độ tươi đã được đảm bảo bởi filter `from-pub-date`, nên sort nên dành cho độ liên quan. Sau khi sửa: *SafeRAG*, *JADE-Plus: Multimodal Agentic RAG*, *Pioneering agentic RAG in software engineering*.

---

## Contract B — CLEAN SCHEMA 🔒

**Owner:** R3 · **File:** `src/ingestion/cleaning.py` · **Artifact:** `data/clean/papers_clean.csv` + `.json`

Bị ép bởi `LocalEmbeddingIndex._build_documents` ([index.py:44-66](src/retrieval/index.py#L44-L66)) — đọc **9 cột theo tên cứng**. Thiếu 1 cột ⇒ `KeyError` khi build index.

| Cột | dtype | 🔒/🔓 | Ai đọc | Rule |
|---|---|---|---|---|
| `paper_id` | `str` | 🔒 | index, eval, quality | = raw `paper_id`. **Unique sau dedupe** |
| `title` | `str` | 🔒 | index, qa lookup | `normalize_whitespace`, non-empty |
| `summary` | `str` | 🔒 | index metadata, qa answer | Text sạch. Baseline yêu cầu `>= 80` chars |
| `authors_joined` | `str` | 🔒 | index metadata, qa answer | `", ".join(authors)`; rỗng ⇒ `"Unknown"` |
| `categories_joined` | `str` | 🔒 | index metadata, qa answer | `", ".join(categories)`; rỗng ⇒ `"uncategorized"` |
| `published` | `str` **`YYYY-MM-DD`** | 🔒 | index metadata, qa answer, freshness | **Phải là `str`, KHÔNG phải `pd.Timestamp`** |
| `abs_url` | `str` | 🔒 | index metadata | có thể `""` |
| `pdf_url` | `str` | 🔒 | index metadata | có thể `""` |
| `text_for_embedding` | `str` | 🔒 | index document content | Xem template dưới. Không rỗng |
| `age_days` | `int` | 🔓 | quality, freshness, corruption | `(run_date.date() - published_date).days` |
| `summary_chars` | `int` | 🔓 | quality check | `len(summary)` |
| `authors` | `list[str]` | 🔓 | — | Giữ để truy vết; **không đưa vào metadata** |
| `categories` | `list[str]` | 🔓 | — | Giữ để truy vết; **không đưa vào metadata** |
| `primary_category` | `str` | 🔓 | báo cáo | |
| `updated`, `comment` | `str` | 🔓 | báo cáo | |

### ⚠️ Rule ChromaDB (nguyên nhân lỗi số 1)

9 cột 🔒 đi thẳng vào `metadata` của Chroma. Chroma **chỉ nhận `str` / `int` / `float` / `bool`**.

```python
# BẮT BUỘC ở cuối build_clean_dataframe:
for col in ["paper_id","title","summary","authors_joined","categories_joined",
            "published","abs_url","pdf_url","text_for_embedding"]:
    df[col] = df[col].fillna("").astype(str)
df["age_days"] = df["age_days"].fillna(0).astype(int)
```

Cấm: `None`, `NaN`, `list`, `pd.Timestamp`, `numpy.int64` trong 9 cột trên.

### Template `text_for_embedding` (chốt — cấm đổi giữa chừng)

```python
text_for_embedding = (
    f"Title: {title}\n"
    f"Authors: {authors_joined}\n"
    f"Categories: {categories_joined}\n"
    f"Published: {published}\n"
    f"Summary: {summary}"
)
```

Lý do gộp đủ 5 field: corruption vào bất kỳ field nào cũng làm embedding lệch ⇒ đo được impact. Nếu chỉ embed `summary`, corrupt title/date sẽ **không đổi metric** và nhóm không chứng minh được gì.

### Cleaning rules (thứ tự thực thi, có log count)

| # | Rule | Dimension | Log |
|---|---|---|---|
| 1 | Drop `paper_id` rỗng | Completeness | `dropped_no_id` |
| 2 | Drop `title` rỗng | Completeness | `dropped_no_title` |
| 3 | Drop `len(summary) < 80` | Validity | `dropped_short_summary` |
| 4 | Drop `published` không parse được | Validity | `dropped_bad_date` |
| 5 | `drop_duplicates(subset="paper_id", keep="first")` | Uniqueness | `dropped_duplicate` |
| 6 | Sort `published` desc, `reset_index(drop=True)` | — | — |

**Rule bất biến:** mọi filter/dedupe phải để lại **count**. Cấm làm mất record âm thầm — CP1 pass criteria yêu cầu truy vết được lý do record bị loại.

**Hàm này được gọi 2 lần** (baseline ở phase1, repaired ở corruption_flow) ⇒ phải **thuần** (pure): cùng input → cùng output, không đọc/ghi file, không phụ thuộc state ngoài.

---

## Contract C — EVAL SCHEMA 🔒

**Owner:** R5 · **File:** `src/evaluation/testset.py` · **Artifact:** `data/eval/test_set.json`

Bị ép bởi `evaluate_pipeline` ([metrics.py:113-131](src/evaluation/metrics.py#L113-L131)) — đọc 5 key.

| Key | Type | Rule |
|---|---|---|
| `id` | `str` | `"q001"`, `"q002"`… duy nhất |
| `question_type` | `str` | Enum chốt: `summary` \| `authors` \| `date` — **KHÔNG dùng `categories`**, xem cảnh báo dưới |
| `question` | `str` | Theo template bên dưới. **Bắt buộc chứa title trong nháy đơn `'...'`** |
| `ground_truth` | `str` | Lấy **nguyên văn** từ cột clean tương ứng |
| `ground_truth_doc_ids` | `list[str]` | `[row["paper_id"]]` — lấy từ clean data, **cấm tự bịa ID** |

### Bảng khớp question ↔ answer (bắt buộc)

`qa.py::_extract_answer` route theo **từ khóa trong câu hỏi**. Sai từ khóa ⇒ agent trả lời sai field ⇒ `token_f1` tụt ⇒ baseline vô nghĩa.

| `question_type` | Template câu hỏi | Từ khóa trigger | `ground_truth` = cột |
|---|---|---|---|
| `authors` | `Who authored the paper titled '{title}'?` | `who authored` | `authors_joined` |
| `date` | `When was the paper titled '{title}' published?` | `when was` | `published` |
| `summary` | `Summarize the paper titled '{title}'.` | (mặc định) | `first_sentence(summary)` |
| ~~`categories`~~ | ~~`What categories does the paper titled '{title}' belong to?`~~ | ~~`what categories`~~ | **cấm dùng** |

Vì sao phải có `'{title}'`: `qa.py:33` dùng `re.search(r"'([^']+)'", question)` để lookup exact và đẩy paper đúng lên đầu kết quả retrieval.

> ### ⚠️ Cấm dùng `question_type = categories`
>
> Đo trên corpus thật: Crossref trả `subject` **rỗng 23/23 bản ghi** (Crossref đã ngừng
> duy trì trường này cho phần lớn thành viên), nên `categories_joined = "uncategorized"`
> ở **mọi** paper.
>
> Nếu vẫn tạo câu hỏi loại này, `ground_truth` giống hệt nhau ở mọi câu và
> `token_f1 = 1.0` **bất kể retrieval trả về paper nào**. Hệ quả: baseline bị thổi
> phồng, và corruption sẽ không làm nhóm câu hỏi này thay đổi ⇒ che mất impact thật.
>
> **Dùng 3 loại còn lại.** Để bù số câu, tăng số paper: 7–10 paper × 3 loại ⇒ **21–30 câu**.
> Trường `categories_joined` vẫn nằm trong schema và vẫn vào metadata index — chỉ không
> được dùng làm ground truth.

### Rule chọn paper

- 7–10 paper × 3 question_type ⇒ **21–30 câu**
- **Phải gồm ≥ 2 paper mới nhất** (`published` cao nhất) — vì corruption sẽ drop latest records; nếu test set không đụng tới paper mới thì corruption không thể hiện được impact
- **Phải gồm ≥ 2 paper cũ nhất** — để có đối chứng
- Chọn paper có `summary` dài, `authors_joined` không rỗng
- **Seed cố định** (`random.Random(42)`) nếu có chọn ngẫu nhiên

### 🔒 Rule quan trọng nhất của cả bài lab

> Test set được sinh **một lần duy nhất** ở CP2 rồi **KHÓA**.
> Baseline, corrupted, repaired đều đánh giá trên **đúng file `data/eval/test_set.json` đó**.
> `phase1.py` chỉ sinh lại khi file chưa tồn tại hoặc `REFRESH_TEST_SET=1`.
> `corruption_flow.py` **chỉ đọc, không bao giờ ghi** file này.

Sinh lại test set giữa chừng ⇒ toàn bộ bảng so sánh 3 trạng thái mất giá trị.

---

## Contract D — QUALITY & FRESHNESS SCHEMA 🔓

**Owner:** R5 · **File:** `src/observability/quality.py`

### D1. `run_data_quality_checks(df, settings, report_name) -> dict`

Ghi ra `settings.paths.quality_dir / f"{report_name}.json"`.

```json
{
  "report_name": "baseline_quality",
  "generated_at": "2026-08-06T10:00:00+00:00",
  "total_rows": 22,
  "checks": [
    {"name": "row_count_min", "dimension": "Completeness",
     "expected": ">= 10", "observed": 22, "success": true}
  ],
  "success_count": 6, "failed_count": 0, "success": true
}
```

Bộ check chốt (6 check, tên cố định để so sánh 3 trạng thái):

| `name` | dimension | expected | observed |
|---|---|---|---|
| `row_count_min` | Completeness | `>= 10` | `len(df)` |
| `paper_id_not_null` | Completeness | `== 0` | số dòng `paper_id` rỗng |
| `paper_id_unique` | Uniqueness | `== 0` | `len(df) - df.paper_id.nunique()` |
| `title_not_empty` | Completeness | `== 0` | số dòng `title` rỗng |
| `summary_min_length` | Validity | `== 0` | số dòng `len(summary) < 80` |
| `freshness_age_days` | Timeliness | `== 0` | số dòng `age_days > 180` |

`report_name` chốt: `baseline_quality` · `corrupted_quality` · `repaired_quality`.

### D2. `build_freshness_report(df, settings, report_path) -> dict`

```json
{
  "generated_at": "...", "threshold_days": 180,
  "latest_published": "2026-07-30", "oldest_published": "2026-02-11",
  "max_age_days": 176, "stale_rows": 0, "total_rows": 22,
  "is_fresh": true
}
```

`is_fresh = (stale_rows == 0)` với `stale_rows = (df.age_days > settings.freshness_threshold_days).sum()`.

Path chốt: baseline+repaired dùng `settings.paths.freshness_report`; corrupted ghi thêm `quality_dir / "freshness_report_corrupted.json"` để **không ghi đè**.

**Rule:** cả 2 hàm phải nhận DataFrame bất kỳ (baseline / corrupted / repaired), không đọc file, không hard-code trạng thái.

---

## Contract E — CORRUPTION LOG SCHEMA 🔓

**Owner:** R3 · **File:** `src/ingestion/corruption.py` · **Artifact:** `data/results/corruption_log.json`

```json
{
  "generated_at": "...",
  "selection_strategy": "stratified-by-published-desc",
  "rows_before": 22, "rows_after": 21,
  "unique_paper_ids_after": 18,
  "operations": [
    {"type": "drop_latest_records", "count": 3,
     "paper_ids": ["10.1000/abc", "..."],
     "params": {"n": 3},
     "expected_signal": "freshness stale + retrieval miss"}
  ]
}
```

6 kịch bản chốt:

| `type` | params | Tác động | Quality signal kỳ vọng |
|---|---|---|---|
| `drop_latest_records` | `n=3` | Xóa 3 dòng `published` mới nhất | `freshness_age_days` ↑, `row_count` ↓ |
| `blank_summary` | `ratio=0.2` | `summary=""` | `summary_min_length` fail |
| `inject_noise` | `ratio=0.25` | Chèn `"lorem ipsum ### %%%"` vào summary | metric ↓, quality có thể vẫn pass |
| `truncate_title` | `ratio=0.2, keep=12` | `title = title[:12]` | qa lookup exact hỏng |
| `stale_dates` | `ratio=0.25, days=800` | `published -= 800d`, **tính lại `age_days`** | `freshness_age_days` fail, `is_fresh=false` |
| `duplicate_rows` | `n=3` | `pd.concat` lặp dòng | `paper_id_unique` fail |

### Cách chọn record bị hỏng: phân tầng, không random

Contract C bắt buộc test set chứa cả paper **mới nhất** lẫn **cũ nhất**. Nếu corruption chọn ngẫu nhiên
thì có thể trượt hết các paper được hỏi, và metric sẽ **không đổi** — nhóm không chứng minh được gì.

Vì vậy `_spread_ids` chọn các dòng **trải đều trên thứ tự `published` giảm dần**, mỗi kịch bản lệch
một `offset` khác nhau để không dồn hết vào cùng một nhóm dòng. Kết quả tất định, không cần seed,
và **chắc chắn giao với test set**.

### 🔒 3 rule bắt buộc

1. **Rebuild `text_for_embedding`** cho mọi dòng bị sửa, theo **đúng template Contract B**. Quên bước này ⇒ embedding vẫn sạch ⇒ metric không đổi ⇒ nhóm không chứng minh được gì.
2. **Giữ nguyên schema Contract B** — corrupted DataFrame vẫn phải đủ 9 cột 🔒 và đúng dtype, vì nó cũng đi qua `LocalEmbeddingIndex.build`.
3. **Không mutate `df` đầu vào** — `df = df.copy()` ngay dòng đầu. Baseline DataFrame phải nguyên vẹn.

---

## Contract F — METRICS SCHEMA 🔒

**Owner:** sinh tự động bởi `evaluate_pipeline` — **không ai được viết tay**.

```json
{
  "samples": 24,
  "retrieval_hit_rate": 0.958,
  "mean_token_f1": 0.842,
  "judge_accuracy": 0.916,
  "mean_judge_score": 4.5,
  "ragas": {"skipped": "Set RUN_RAGAS=1 to enable the slower Ragas pass."}
}
```

`retrieval_hit_rate` = tỉ lệ câu có ít nhất 1 `retrieved_doc_ids` nằm trong `ground_truth_doc_ids`.

**Rule:** report chỉ được đọc số từ 3 file `data/results/*_metrics.json`. Cấm gõ tay số vào markdown. Cấm "sửa" metrics khi kết quả không đẹp — sửa data contract, rồi chạy lại.

---

## Contract G — PATHS & COLLECTIONS 🔒

Đã cố định trong [config.py:80-109](src/core/config.py#L80-L109). **Cấm hard-code path**; luôn dùng `settings.paths.*`.

| Trạng thái | clean | embeddings manifest | collection | metrics | answers |
|---|---|---|---|---|---|
| baseline | `clean_csv` / `clean_json` | `embeddings_json` | `papers-baseline` | `baseline_metrics` | `baseline_answers` |
| corrupted | `corrupted_clean_csv/json` | `corrupted_embeddings_json` | `papers-corrupted` | `corrupted_metrics` | `corrupted_answers` |
| repaired | `repaired_clean_csv/json` | `repaired_embeddings_json` | `papers-repaired` | `repaired_metrics` | `repaired_answers` |

Collection name **tự suy ra** từ đường dẫn manifest ([index.py:68-81](src/retrieval/index.py#L68-L81)) — chỉ cần truyền đúng `embeddings_output_path`, 3 collection tách biệt, baseline không bị ghi đè.

**Rule bất biến:** `corruption_flow.py` **cấm ghi** vào bất kỳ path baseline nào (`clean_csv`, `embeddings_json`, `baseline_metrics`, `baseline_answers`, `eval_testset`).

---

## Contract H — REPAIR 🔒

**Repair = chạy lại cleaning từ `data/raw/crossref_records.json`.**

```python
records = load_raw_records(settings.paths.raw_records_json)   # đúng snapshot của baseline
repaired = build_clean_dataframe(records, now_utc())          # cùng hàm, cùng rule
```

Cấm tuyệt đối:
- Copy `papers_clean.csv` sang `papers_clean_repaired.csv`
- Sửa tay dòng bị corrupt trong corrupted DataFrame
- Fetch lại Crossref (dữ liệu nguồn đã đổi ⇒ comparison mất công bằng)

**Tiêu chí repair thành công:** `repaired_metrics` ≈ `baseline_metrics` **và** `repaired_quality.success == true` **và** `freshness.is_fresh == true`. Nếu chưa hồi phục hoàn toàn ⇒ **ghi đúng sự thật** trong report, kèm giả thuyết.

---

## Chữ ký chốt contract (CP0)

| Vai trò | Thành viên | MSSV | GitHub | File sở hữu | Contract phụ trách | Đồng ý |
|---|---|---|---|---|---|---|
| R1 — Data foundation + release admin | Nguyễn Thanh Bình | 2A202601274 | @NguyenThanhBinh108 | `ingestion/crossref.py`, `ingestion/cleaning.py`, `ingestion/corruption.py` | **A, B, E** | ☐ |
| R2 — Pipeline orchestration | Đỗ Thu Liễu | 2A202601898 | @thulieu0503 | `pipelines/phase1.py`, `pipelines/corruption_flow.py` | **G, H** | ☐ |
| R3 — Evaluation owner | Trần Chí Vũ | 2A202601044 | @Chivu171 | `evaluation/testset.py` | **C** | ☐ |
| R4 — Reporting & agent demo | Trịnh Hải Đăng | 2A202601602 | @haidang2425 | `observability/reporting.py`, `retrieval/demo.py` | đọc **D, F** | ☐ |
| R5 — Data quality & freshness | Đỗ Văn Linh | 2A202601190 | @DoVanLinh12 | `observability/quality.py`, `script/smoke_retrieval.py` | **D** | ☐ |

Xem phân công chi tiết và timeline tại [PHAN_CONG.md](PHAN_CONG.md).

**Quy trình đổi contract:** phát hiện vấn đề → báo R1 → R1 xác nhận ảnh hưởng tới ai → sửa file này + commit riêng `contract: ...` → thông báo nhóm → owner liên quan sửa code. Không ai tự đổi schema trong branch riêng.
