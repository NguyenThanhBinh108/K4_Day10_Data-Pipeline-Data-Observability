# Group Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin bài nộp

| Thông tin         | Nội dung                                                                       |
| ------------------ | ------------------------------------------------------------------------------- |
| Khóa/Lớp         | K4                                                                              |
| Tên nhóm         | B52                                                                             |
| Repository         | https://github.com/NguyenThanhBinh108/K4_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06                                                                      |

### Thành viên và phân công

| STT | Họ và tên        | MSSV        | Vai trò chính                 | Module/deliverable sở hữu                                                                                            |
| --: | ------------------- | ----------- | ------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
|   1 | Nguyễn Thanh Bình | 2A202601274 | Data foundation + release admin | `ingestion/crossref.py`, `cleaning.py`, `corruption.py`, `DATA_CONTRACT.md`, `script/verify_data_lineage.py` |
|   2 | Đỗ Thu Liễu      | 2A202601898 | Pipeline orchestration          | `pipelines/phase1.py`, `pipelines/corruption_flow.py`                                                              |
|   3 | Trần Chí Vũ      | 2A202601044 | Evaluation                      | `evaluation/testset.py`                                                                                              |
|   4 | Trịnh Hải Đăng  | 2A202601602 | Reporting & agent demo          | `observability/reporting.py`, `retrieval/demo.py` — Bình hỗ trợ hoàn thiện                                        |
|   5 | Đỗ Văn Linh      | 2A202601190 | Data quality & freshness        | `observability/quality.py`, `script/smoke_retrieval.py`                                                            |

Một sửa lỗi trong `evaluation/testset.py` do Bình thực hiện lúc tích hợp — lý do ở mục 11.
Chi tiết tác giả từng thay đổi xem lịch sử commit.

Phân công chi tiết và quy tắc chống trùng chéo: [`PHAN_CONG.md`](../PHAN_CONG.md).
Hợp đồng dữ liệu dùng chung: [`DATA_CONTRACT.md`](../DATA_CONTRACT.md).

## 2. Tóm tắt kết quả

**Tóm tắt của nhóm:**

Nhóm hoàn thành toàn bộ vòng đời dữ liệu: lấy 24 bản ghi từ Crossref, giữ 23 bản ghi hợp lệ, làm sạch
thành dataset 23 dòng × 16 cột, embed bằng MiniLM-L6-v2 vào ChromaDB, sinh bộ test 23 câu rồi **khóa
lại**, và đánh giá agent trên cả ba trạng thái dữ liệu bằng đúng bộ test đó.

Baseline pipeline sinh đủ artifact: raw response thô, raw records, clean CSV/JSON, embedding manifest,
test set, metrics, answers, quality report, freshness report và `phase1_report.md`.

Corruption có tác động đo được rõ ràng: `mean_token_f1` tụt từ 1.0 xuống 0.6584 (−34%),
`retrieval_hit_rate` từ 1.0 xuống 0.8261, và 4/23 câu chuyển từ truy hồi trúng sang trượt hoàn toàn.
Ba trong sáu quality check lật từ PASS sang FAIL, freshness lật từ `is_fresh=true` sang `false` với
`max_age_days` nhảy từ 175 lên 975. Corruption ảnh hưởng rõ nhất là `drop_latest_records`: ba paper mới
nhất bị xóa khỏi index nên retrieval không thể trả về chúng ở bất kỳ câu hỏi nào.

Repair chạy lại cleaning từ `data/raw/crossref_records.json` — không gọi lại Crossref — và khôi phục
100% cả bốn metric về đúng mức baseline, quality trở lại 6/6, freshness trở lại `fresh`.

Giới hạn quan trọng nhất còn lại: baseline đạt tuyệt đối 1.0 ở cả bốn chỉ số, nên bài này chứng minh
được **delta** chứ chưa đo được độ khó thật của RAG. Chi tiết ở mục 12.

## 3. Kiến trúc và luồng dữ liệu

### Luồng end-to-end

```text
Crossref API (query.bibliographic, sort=relevance, filter from-pub-date + has-abstract)
    -> data/raw/crossref_response.json      thô, lưu TRƯỚC khi parse
    -> data/raw/crossref_records.json       23 PaperRecord   <-----------+
    -> data/clean/papers_clean.csv|json     23 dòng x 16 cột             |
    -> ChromaDB `papers-baseline` + embeddings manifest                  |
    -> data/eval/test_set.json              23 câu, KHÓA sau CP2         | nguồn
    -> baseline_metrics/answers + quality + freshness + phase1_report    | repair
                                                                         |
    -> corruption, 6 kịch bản                                            |
    -> ChromaDB `papers-corrupted` -> corrupted_metrics/answers/quality  |
                                                                         |
    -> repair: load_raw_records --------------------------------------- +
    -> ChromaDB `papers-repaired` -> repaired_metrics/answers/quality
    -> data/reports/corruption_report.md    bảng 3 trạng thái + delta
```

### Trách nhiệm của từng khối

| Khối             | Input                          | Xử lý chính                                                                     | Output/artifact                           | Owner               |
| ----------------- | ------------------------------ | ---------------------------------------------------------------------------------- | ----------------------------------------- | ------------------- |
| Ingestion         | Crossref REST API              | Retry/backoff 429+5xx, bóc JATS XML, parse`date-parts`                          | `data/raw/` (2 file)                    | Bình               |
| Cleaning          | 23`PaperRecord`              | 5 rule loại bỏ có đếm, dedupe,`age_days`, `text_for_embedding`, ép dtype | `data/clean/papers_clean.*`             | Bình               |
| Embedding/index   | Clean DataFrame                | MiniLM-L6-v2, cosine, 3 collection tách biệt                                     | `data/embeddings/*.json`                | Liễu (orchestrate) |
| Evaluation        | Clean DataFrame                | 23 câu, 3 loại, ground truth từ chính clean data                               | `data/eval/test_set.json`               | Vũ                 |
| Observability     | DataFrame bất kỳ             | 6 quality check + freshness, chạy được trên cả 3 trạng thái                | `data/quality/*.json`                   | Linh                |
| Reporting         | metrics + quality + freshness  | 2 báo cáo Markdown, delta tính bằng code                                       | `data/reports/*.md`                     | Đăng             |
| Corruption/repair | Clean DataFrame / raw snapshot | 6 kịch bản có log; repair = chạy lại cleaning từ raw                         | `corruption_log.json`, `*_repaired.*` | Bình               |
| Orchestration     | Tất cả                       | Ghép 2 flow, kiểm tra toàn vẹn baseline                                        | 2 entrypoint                              | Liễu               |

## 4. Cách tái hiện kết quả

### Cấu hình không chứa secret

| Biến/cấu hình             | Giá trị sử dụng                                                       |
| ---------------------------- | ------------------------------------------------------------------------- |
| `LLM_PROVIDER`             | `gemini`                                                                |
| `LLM_MODEL`                | `gemini-2.5-flash`                                                      |
| Embedding model              | `sentence-transformers/all-MiniLM-L6-v2`                                |
| Số lượng Crossref records | `rows=24` yêu cầu → 23 bản ghi hợp lệ                             |
| Retrieval`top_k`           | 4                                                                         |
| Freshness threshold          | 180 ngày                                                                 |
| Chọn bản ghi corruption    | `stratified-by-published-desc` — tất định, không seed ngẫu nhiên |
| Python                       | 3.13.3                                                                    |

Không dán nội dung API key hoặc file `.env` vào báo cáo.

### Lệnh cài đặt

```bash
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

### Lệnh chạy

```bash
python script/run_phase1.py
python script/run_corruption_flow.py
python script/verify_data_lineage.py    # 24 assertion về lineage và repair
python script/smoke_retrieval.py        # smoke test semantic search + exact lookup
```

### Kết quả tái hiện

| Lệnh                      | Trạng thái         | Thời điểm chạy gần nhất | Bằng chứng                                                     |
| -------------------------- | -------------------- | ----------------------------- | ---------------------------------------------------------------- |
| `run_phase1.py`          | Thành công, exit 0 | 2026-08-06                    | `data/reports/phase1_report.md`, `baseline_metrics.json`     |
| `run_corruption_flow.py` | Thành công, exit 0 | 2026-08-06                    | `data/reports/corruption_report.md`, `repaired_metrics.json` |
| `verify_data_lineage.py` | 24/24 assertion PASS | 2026-08-06                    | Output console, exit 0                                           |

> ### ⚠️ Điều kiện tái hiện của metrics judge
>
> `retrieval_hit_rate` và `mean_token_f1` **tái hiện chính xác 100%** trong mọi môi trường — chúng chỉ
> phụ thuộc embedding và dữ liệu.
>
> `judge_accuracy` và `mean_judge_score` **không** tái hiện được giữa hai chế độ judge. `metrics.py`
> gọi LLM judge, và khi lỗi thì rơi về heuristic dựa trên `token_f1`. Số liệu trong báo cáo này được
> sinh ở chế độ **heuristic fallback** vì môi trường chạy không có `GOOGLE_API_KEY`; `phase1_report.md`
> ghi rõ ở trường `judge_mode`. Một lần chạy trước đó có LLM judge cho `mean_judge_score` corrupted
> = 3.7826 thay vì 3.6087 — lệch ở 3/23 câu. Đây **không phải lỗi**, mà là hệ quả của việc judge phụ
> thuộc mô hình ngoài.

## 5. Ingestion, cleaning và data contract

### Nguồn dữ liệu

| Thuộc tính                | Giá trị                                                                                                                           |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Source                      | Crossref REST API —`https://api.crossref.org/works`                                                                              |
| Query                       | `query.bibliographic=agentic retrieval augmented generation large language model`                                                 |
| Filter                      | `from-pub-date:<today−180d>,has-abstract:true`                                                                                   |
| Sort                        | `relevance` desc                                                                                                                  |
| Thời điểm lấy dữ liệu | `2026-08-06T08:36:03Z` — mtime của raw snapshot                                                                                 |
| Số record nhận được    | 24 item → 23 hợp lệ, trên tổng 99.892 kết quả khớp                                                                          |
| Cơ chế retry/backoff      | 4 lần, backoff`2^attempt` giây cho 429/500/502/503/504 và lỗi mạng; honor header `Retry-After`; `User-Agent` polite pool |

### Ba quyết định dữ liệu quan trọng

Cả ba đều phát hiện khi chạy fetch lần đầu, không phải suy đoán trên giấy.

**1. `published = min(issued, created)`, không dùng thẳng `issued`.** Crossref `issued` là ngày xuất
bản **danh nghĩa do nhà xuất bản khai**; với các số tạp chí sắp phát hành nó nằm ở tương lai. Lần chạy
đầu cho `issued` = 2027–2028 trong khi `created` = 2026-05…07, dẫn tới `age_days` **âm, từ −679 đến
−147**, và toàn bộ freshness monitoring vô nghĩa. `created` là thời điểm bản ghi thực sự vào Crossref,
luôn ở quá khứ. Sau khi sửa: `age_days` = 5…175.

**2. Áp lại cửa sổ tuổi trên ngày hiệu lực.** Filter `from-pub-date` của Crossref áp trên `issued`, còn
ta dùng `min(issued, created)`, nên vài bản ghi lọt qua filter nguồn nhưng ngày hiệu lực rơi ngoài 180
ngày. Không áp lại thì baseline có sẵn 1 dòng stale và tín hiệu freshness **không còn phân biệt được
baseline với corrupted**. Sau khi sửa baseline `stale_rows = 0`. Đây là bản ghi duy nhất bị loại (24 → 23).

**3. `sort=relevance`, không phải `sort=published`.** Sắp theo ngày chỉ lấy các bản ghi có `issued` xa
nhất ở tương lai, cho ra corpus lần chạy đầu toàn *"Mind Reader Robot: an Arduino-Based Game"*,
*"Augmented Reality in Teacher Education"* — không dính dáng gì tới query về agentic RAG. Độ tươi đã
được filter đảm bảo, nên sort nên dành cho độ liên quan. Sau khi sửa, corpus gồm *SafeRAG*,
*JADE-Plus: Multimodal Agentic RAG*, *Pioneering agentic RAG in software engineering*.

### Raw và clean schema

| Trường                                   | Kiểu              | Bắt buộc? | Ý nghĩa                                                   | Xử lý khi thiếu/sai                            |
| ------------------------------------------ | ------------------ | ----------- | ----------------------------------------------------------- | ------------------------------------------------- |
| `paper_id`                               | `str`            | Có         | DOI lowercase, khóa liên kết xuyên suốt 3 trạng thái | Thiếu ⇒ drop record                             |
| `title`                                  | `str`            | Có         | Tiêu đề đã normalize whitespace                        | Rỗng ⇒ drop record                              |
| `summary`                                | `str`            | Có         | Abstract đã bóc JATS XML                                 | `len < 80` ⇒ drop record                       |
| `published`                              | `str YYYY-MM-DD` | Có         | `min(issued, created)`                                    | Parse fail hoặc`age_days > 180` ⇒ drop record |
| `authors` / `categories`               | `list[str]`      | Không      | Giữ để truy vết,**không** vào metadata          | Không có ⇒`[]`                               |
| `authors_joined` / `categories_joined` | `str`            | Có         | Bản ghép cho metadata ChromaDB                            | Rỗng ⇒`"Unknown"` / `"uncategorized"`       |
| `age_days`                               | `int`            | Có         | Cơ sở của freshness                                      | Không parse được ⇒`-1`                     |
| `text_for_embedding`                     | `str`            | Có         | Nội dung đưa vào embedding                              | Không được rỗng                              |

**Ràng buộc ChromaDB — nguyên nhân lỗi số 1 của bài lab.** Chín cột khóa đi thẳng vào `metadata` của
Chroma, mà Chroma chỉ nhận `str`/`int`/`float`/`bool`. Một `NaN`, `None`, `list` hay `pd.Timestamp` lọt
vào là `collection.add` báo lỗi. Hàm `enforce_clean_dtypes` ép kiểu ở bước cuối, và corruption gọi lại
chính hàm đó sau khi làm hỏng dữ liệu.

### Quy tắc cleaning

| Quy tắc                               | Quality dimension | Số record bị tác động | Cách xác minh                |
| -------------------------------------- | ----------------- | -------------------------: | ------------------------------ |
| Drop`paper_id` rỗng                 | Completeness      |                          0 | `df.attrs["cleaning_stats"]` |
| Drop`title` rỗng                    | Completeness      |                          0 | `df.attrs["cleaning_stats"]` |
| Drop`len(summary) < 80`              | Validity          |                          0 | `df.attrs["cleaning_stats"]` |
| Drop`published` không parse được | Validity          |                          0 | `df.attrs["cleaning_stats"]` |
| Dedupe theo`paper_id`                | Uniqueness        |                          0 | `df.attrs["cleaning_stats"]` |
| Lọc cửa sổ tuổi, ở bước parse   | Timeliness        |                          1 | 24 item → 23 record           |

Mọi rule đều **đếm và ghi lại**, không làm mất record âm thầm.

**Cách nhóm tạo `text_for_embedding`, document ID và `age_days`.**
`paper_id` là DOI viết thường, giữ nguyên xuyên suốt raw → clean → index metadata → `ground_truth_doc_ids`
→ repair; `verify_data_lineage.py` truy một `paper_id` qua cả bốn tầng để chứng minh.
`age_days = (ngày chạy − published).days`. `text_for_embedding` gộp cả năm trường:

```
Title: {title}
Authors: {authors_joined}
Categories: {categories_joined}
Published: {published}
Summary: {summary}
```

Gộp đủ năm trường là có chủ đích: corrupt bất kỳ trường nào cũng làm embedding lệch, nhờ vậy mới đo
được impact. Nếu chỉ embed `summary` thì corrupt title hoặc date sẽ **không làm metric thay đổi** và cả
bài lab không chứng minh được gì. Corruption import lại chính hàm `build_text_for_embedding` của
cleaning chứ không chép template, nên hai bên không bao giờ lệch nhau.

## 6. Evaluation setup

| Thành phần             | Cấu hình thực tế                                                                 |
| ------------------------ | ------------------------------------------------------------------------------------ |
| Số câu hỏi            | 23                                                                                   |
| Các`question_type`    | `summary` (8), `authors` (8), `date` (7)                                       |
| Ground-truth document ID | `[row["paper_id"]]` lấy từ clean data; `_validate_doc_ids` kiểm tra tồn tại |
| Embedding model          | `sentence-transformers/all-MiniLM-L6-v2`                                           |
| Vector store/collection  | ChromaDB cosine —`papers-baseline` / `papers-corrupted` / `papers-repaired`   |
| Retrieval`top_k`       | 4                                                                                    |
| LLM provider/model       | `gemini` / `gemini-2.5-flash`                                                    |
| Test set dùng chung     | `data/eval/test_set.json`, sinh một lần ở CP2 rồi khóa                        |

**Vì sao giữ nguyên test set qua ba trạng thái.** Metric chỉ so sánh được khi biến duy nhất thay đổi là
**dữ liệu**. Sinh lại test set giữa chừng thì câu hỏi, ground truth và `ground_truth_doc_ids` đều đổi,
và chênh lệch giữa các cột không còn quy được cho corruption. Xác minh thực tế: trường `id` trong
`baseline_answers.json`, `corrupted_answers.json` và `repaired_answers.json` khớp chính xác theo thứ tự
với `test_set.json`, và `question` + `ground_truth` giống hệt nhau qua cả ba lần chạy.

**Một loại câu hỏi đã bị loại bỏ có chủ đích.** Thiết kế ban đầu có `question_type = categories`. Đo
trên corpus thật cho thấy Crossref trả `subject` **rỗng 23/23 bản ghi**, nên `categories_joined = "uncategorized"` ở mọi paper. Vì `qa.py` trả thẳng `metadata["categories_joined"]` cho loại câu này,
`token_f1` bằng 1.0 **bất kể retrieval trả về paper nào** — 22% bộ test thành điểm cho không mà
corruption không bao giờ làm giảm được. Loại này bị cấm trong Contract C và đã gỡ khỏi `testset.py`.

## 7. Kết quả baseline

### Artifact checklist

| Artifact                 | Đường dẫn thực tế                  | Trạng thái | Ghi chú                                          |
| ------------------------ | ---------------------------------------- | ------------ | ------------------------------------------------- |
| Raw response/records     | `data/raw/`                            | Có          | `crossref_response.json` lưu trước khi parse |
| Cleaned dataset          | `data/clean/`                          | Có          | 23 dòng × 16 cột                               |
| Embedding manifest/index | `data/embeddings/`                     | Có          | 3 manifest cho 3 trạng thái                     |
| Evaluation set           | `data/eval/test_set.json`              | Có          | 23 câu, đã khóa                               |
| Baseline metrics         | `data/results/baseline_metrics.json`   | Có          |                                                   |
| Quality/freshness        | `data/quality/`                        | Có          | 3 quality + 3 freshness report                    |
| Baseline report          | `data/reports/phase1_report.md`        | Có          |                                                   |
| Agent demo               | `data/results/agent_demo_answers.json` | Có          | Ghi rõ lý do bỏ qua khi thiếu API key         |

### Baseline metrics

| Metric                 | Giá trị | Diễn giải                                                             |
| ---------------------- | --------: | ----------------------------------------------------------------------- |
| `retrieval_hit_rate` |    1.0000 | Cả 23 câu đều truy hồi trúng ít nhất một ground-truth document |
| `mean_token_f1`      |    1.0000 | Câu trả lời trùng khớp hoàn toàn với ground truth               |
| `judge_accuracy`     |    1.0000 | Judge chấm đúng toàn bộ                                            |
| `mean_judge_score`   |      5.00 | Điểm tối đa                                                         |
| Ragas                  |       N/A | Bỏ qua — cần`RUN_RAGAS=1`, tốn thời gian và API quota           |

**Đọc con số này cho đúng.** Baseline tuyệt đối 1.0 **không** có nghĩa agent giỏi. `qa.py` là extractive:
nó lấy thẳng field từ metadata của document top-1, còn ground truth cũng sinh từ đúng field đó — gần như
một vòng lặp kín. Giá trị của bài lab nằm ở **delta giữa ba trạng thái**, không nằm ở giá trị tuyệt đối.
Chi tiết ở mục 12.

## 8. Data quality và freshness

### Quality checks

| Check                  | Quality dimension | Ngưỡng/kỳ vọng | Kết quả baseline   | Bằng chứng                           |
| ---------------------- | ----------------- | ------------------ | -------------------- | -------------------------------------- |
| `row_count_min`      | Completeness      | `>= 10`          | Pass, observed`23` | `data/quality/baseline_quality.json` |
| `paper_id_not_null`  | Completeness      | `== 0`           | Pass, observed`0`  | `data/quality/baseline_quality.json` |
| `paper_id_unique`    | Uniqueness        | `== 0`           | Pass, observed`0`  | `data/quality/baseline_quality.json` |
| `title_not_empty`    | Completeness      | `== 0`           | Pass, observed`0`  | `data/quality/baseline_quality.json` |
| `summary_min_length` | Validity          | `== 0`           | Pass, observed`0`  | `data/quality/baseline_quality.json` |
| `freshness_age_days` | Timeliness        | `== 0`           | Pass, observed`0`  | `data/quality/baseline_quality.json` |

Baseline quality report có `success_count=6`, `failed_count=0`, `success=true` trên 23 dòng clean data. Sau corruption, `data/quality/corrupted_quality.json` cho thấy `success_count=3`, `failed_count=3`, `success=false`; các check fail là `paper_id_unique` observed `3`, `summary_min_length` observed `5`, và `freshness_age_days` observed `6`. Kết quả này khớp với `data/results/corruption_log.json`: `duplicate_rows`, `blank_summary`, và `stale_dates` là các corruption có signal trực tiếp trên quality/freshness.

### Freshness

| Thuộc tính               | Giá trị                                                                                                                |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Freshness được đo tại | `data/clean/papers_clean.csv`, report `data/quality/freshness_report.json`                                           |
| Timestamp mới nhất       | `2026-08-01`                                                                                                           |
| Ngưỡng freshness         | `180` ngày                                                                                                            |
| Trạng thái baseline      | Fresh,`is_fresh=true`                                                                                                  |
| Lý do                     | Baseline có`stale_rows=0`, `max_age_days=175`, `total_rows=23`, nên không dòng nào vượt ngưỡng 180 ngày. |

Corrupted freshness được lưu ở `data/quality/freshness_report_corrupted.json`: `is_fresh=false`, `stale_rows=6`, `max_age_days=975`, `latest_published=2026-07-03`, `oldest_published=2023-12-05`. Điều này xác nhận corruption `stale_dates` đã làm dữ liệu lỗi thời và được observability phát hiện trước khi dùng làm căn cứ trả lời.

## 9. Corruption scenarios và repair

| Corruption              | Cách tạo                                          | Record bị tác động | Quality signal kỳ vọng           | Tác động thực tế                            | Cách repair                |
| ----------------------- | --------------------------------------------------- | ---------------------: | ---------------------------------- | ------------------------------------------------ | --------------------------- |
| `drop_latest_records` | Xóa 3 dòng`published` mới nhất                |                      3 | freshness stale + retrieval miss   | 3/4 câu chuyển HIT→MISS thuộc nhóm này     | Chạy lại cleaning từ raw |
| `blank_summary`       | `summary = ""`                                    |                      4 | `summary_min_length` FAIL        | FAIL, observed 5 dòng                           | như trên                  |
| `inject_noise`        | Chèn`lorem ipsum ### %%% …` vào summary        |                      4 | embedding lệch,`token_f1` giảm | Không làm check nào FAIL, chỉ lộ qua metric | như trên                  |
| `truncate_title`      | `title = title[:12]`                              |                      4 | exact lookup theo title hỏng      | Không làm check nào FAIL, chỉ lộ qua metric | như trên                  |
| `stale_dates`         | `published -= 800 ngày`, tính lại `age_days` |                      5 | `freshness_age_days` FAIL        | FAIL, observed 6;`max_age_days` 175→975       | như trên                  |
| `duplicate_rows`      | `pd.concat` lặp dòng                            |                      3 | `paper_id_unique` FAIL           | FAIL, observed 3                                 | như trên                  |

Kết quả tổng: 23 → 23 dòng nhưng chỉ còn **20 `paper_id` duy nhất**, corruption chạm tới **17/23 paper**.

Corruption log:

- Đường dẫn: `data/results/corruption_log.json`
- Trạng thái: Có
- Nhận xét: log có `selection_strategy`, `rows_before/after`, `unique_paper_ids_after`, và với mỗi kịch
  bản là `type`, `count`, danh sách `paper_ids`, `params` và `expected_signal`. Đủ để tái hiện và đối
  chiếu từng bản ghi.

**Chọn bản ghi phân tầng, không random.** Contract C bắt bộ test chứa cả paper mới nhất lẫn cũ nhất. Nếu
corruption chọn ngẫu nhiên thì có thể trượt hết các paper được hỏi và metric sẽ **không đổi** — nhóm
không chứng minh được gì. Hàm `_spread_ids` chọn các dòng trải đều trên thứ tự `published` giảm dần, mỗi
kịch bản lệch một `offset`. Kết quả tất định, không cần seed, và chắc chắn giao với bộ test.

**Repair đảm bảo phục hồi từ nguồn đáng tin thế nào.** `corruption_flow.py` gọi
`load_raw_records(data/raw/crossref_records.json)` rồi `build_clean_dataframe(...)` — **đúng cùng một hàm
cleaning** đã tạo ra baseline. Không copy file baseline, không sửa tay bản ghi nào, và **không gọi lại
Crossref API**; nếu gọi lại thì nguồn đã đổi và phép so sánh mất công bằng.

Ba lớp bằng chứng cho việc repair là thật chứ không phải che kết quả lỗi:

1. `verify_data_lineage.py` xác nhận repaired trùng khớp baseline trên `title`, `summary`, `published`,
   `authors_joined` và `text_for_embedding` ở **23/23 bản ghi**, và 3 paper bị `drop_latest_records` xóa
   đã quay lại.
2. `corruption_flow.py` băm SHA-256 bảy artifact baseline trước và sau khi chạy, raise nếu có cái nào
   đổi — chạy thật: **7/7 không đổi**.
3. Ba collection ChromaDB tách biệt (`papers-baseline` / `papers-corrupted` / `papers-repaired`), xác
   minh qua trường `collection_name` trong ba embedding manifest.

## 10. So sánh baseline, corrupted và repaired

| Metric/signal            |                 Baseline |                Corrupted |                 Repaired |                       Thay đổi do corruption | Mức phục hồi | Nhận xét                                                                               |
| ------------------------ | -----------------------: | -----------------------: | -----------------------: | ---------------------------------------------: | --------------: | ---------------------------------------------------------------------------------------- |
| `retrieval_hit_rate`   |                    1.000 |                    0.826 |                    1.000 |                                         -0.174 |            100% | Corruption làm retrieval hit giảm, repair phục hồi về baseline                      |
| `mean_token_f1`        |                    1.000 |                    0.658 |                    1.000 |                                         -0.342 |            100% | Blank summary, truncate title và noise làm answer overlap giảm; repair phục hồi     |
| `judge_accuracy`       |                    1.000 |                    0.652 |                    1.000 |                                         -0.348 |            100% | Judge accuracy giảm theo corruption và quay về baseline sau repair                    |
| `mean_judge_score`     |                    5.000 |                    3.609 |                    5.000 |                                         -1.391 |            100% | Điểm judge giảm cùng chiều với quality/freshness failure, rồi phục hồi          |
| Quality checks pass/fail |                      6/0 |                      3/3 |                      6/0 |                   -3 check pass, +3 check fail |            100% | Repair làm`paper_id_unique`, `summary_min_length`, `freshness_age_days` pass lại |
| Freshness status         | Fresh (`stale_rows=0`) | Stale (`stale_rows=6`) | Fresh (`stale_rows=0`) | `is_fresh` đổi từ `true` sang `false` |            100% | `stale_dates` làm `max_age_days` tăng từ 175 lên 975; repair đưa về 175       |

### Hai chuỗi nhân quả có bằng chứng

1. **`stale_dates` + `drop_latest_records` → freshness lật → retrieval trượt.**
   Năm bản ghi bị đẩy lùi `published` 800 ngày và ba bản ghi mới nhất bị xóa hẳn.
   `data/quality/freshness_report_corrupted.json` cho `stale_rows` 0→6 và `is_fresh` true→false;
   `corrupted_quality.json` cho `freshness_age_days` FAIL. Hệ quả trên agent: `retrieval_hit_rate`
   1.0→0.8261, và 4/23 câu chuyển từ trúng sang trượt — trong đó `eval_summary_00`, `eval_authors_01` và
   `eval_date_02` đều hỏi về các paper đã bị xóa khỏi index.
2. **Repair từ raw → quality và freshness phục hồi → metric agent phục hồi.**
   `load_raw_records` + `build_clean_dataframe` tái tạo đúng 23/23 bản ghi.
   `repaired_quality.json` trở lại 6/6 pass, `freshness_report_repaired.json` trở lại `is_fresh=true`
   với `max_age_days=175`, và cả bốn metric agent trở lại đúng mức baseline.

### Corruption nào ảnh hưởng rõ nhất

`drop_latest_records`. Ba paper bị xóa **khỏi index**, nên retrieval không có cách nào trả về chúng ở bất
kỳ câu hỏi nào — mất mát tuyệt đối chứ không phải giảm chất lượng. Ba trong bốn câu chuyển HIT→MISS thuộc
nhóm này. Các corruption khác chỉ làm embedding lệch: document vẫn còn trong index nên retrieval vẫn có
cơ hội trúng.

### Kết quả khác kỳ vọng ban đầu

**`inject_noise` và `truncate_title` không làm quality check nào FAIL.** Cả hai làm hỏng nội dung thật sự
— summary bị chèn rác, title bị cắt còn 12 ký tự — nhưng dữ liệu vẫn *hợp lệ về cấu trúc*: không rỗng,
không trùng, không quá hạn. Chúng chỉ lộ ra qua `mean_token_f1`.

Nhóm đã kiểm tra giả thuyết này bằng cách đối chiếu `corrupted_quality.json` với danh sách `paper_ids`
của hai kịch bản đó trong `corruption_log.json`: các bản ghi bị chèn nhiễu và bị cắt title đều **không**
xuất hiện trong bất kỳ check nào bị FAIL.

Đây là bài học quan trọng nhất của cả bài lab: **quality check bắt được lỗi cấu trúc, không bắt được lỗi
ngữ nghĩa.** Một pipeline chỉ dựa vào quality gate sẽ báo "xanh" trong khi agent đang trả lời từ dữ liệu
rác. Muốn bắt loại lỗi này phải có evaluation trên bộ test cố định — đúng thứ bài lab đang làm.

### Các tín hiệu KHÔNG đổi

`row_count_min`, `paper_id_not_null` và `title_not_empty` giữ nguyên PASS ở cả ba trạng thái. Nhóm
**không** kết luận rằng mọi tín hiệu quality đều phát hiện được corruption — chỉ 3/6 check phát hiện.

## 11. Vấn đề tích hợp quan trọng

- **Triệu chứng:** Bộ test do `testset.py` sinh ra có 5/23 câu loại `categories`, cả 5 mang `ground_truth`
  giống hệt nhau là `"uncategorized"`.
- **Nguyên nhân:** Crossref trả `subject` rỗng cho toàn bộ 23 bản ghi — Crossref đã ngừng duy trì trường
  này với phần lớn thành viên. Vì `qa.py::_extract_answer` trả thẳng `metadata["categories_joined"]` cho
  loại câu hỏi này, `token_f1 = 1.0` bất kể retrieval trả về paper nào. Hệ quả: 22% bộ test là điểm cho
  không, baseline bị thổi phồng, và corruption không thể làm nhóm câu hỏi đó giảm nên delta bị nén lại.
- **Cách xử lý:** Gỡ `"categories"` khỏi `QUESTION_TYPES`, ghi lý do vào `DATA_CONTRACT.md` Contract C.
  Thay đổi được thực hiện lúc tích hợp và ghi rõ trong commit `fix(testset): bỏ question_type
  "categories"`.
- **Cách xác minh:** Sau khi sửa, bộ test còn 23 câu trên 23 paper, phân bố `summary` 8 / `authors` 8 /
  `date` 7, và **0 câu trùng `ground_truth`**.

Một vấn đề tích hợp thứ hai đáng ghi: 15 ký tự em-dash nằm trong lệnh `print()` của ba module. Console
Windows dùng codepage cp1252 nên ký tự ngoài bảng mã ném `UnicodeEncodeError` và giết pipeline giữa
chừng — lỗi này xảy ra thật khi kiểm thử. Đã đổi hết sang ASCII; file report vẫn ghi UTF-8 bình thường.

## 12. Giới hạn và hướng cải thiện

| Giới hạn hiện tại                           | Ảnh hưởng                                                                                                                                                                   | Hướng cải thiện có thể kiểm chứng                                                                                                                                                  |
| ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Baseline đạt tuyệt đối 1.0 ở cả 4 metric | `qa.py` extractive lấy đúng field mà ground truth sinh ra — gần như vòng lặp kín. Bài chứng minh được delta nhưng chưa đo được độ khó thật của RAG | Sinh ground truth bằng người hoặc bằng LLM độc lập với`qa.py` rồi đo lại. Kỳ vọng baseline tụt về khoảng 0.6–0.8, và delta do corruption vẫn phải quan sát được |
| Corpus chỉ 23 paper                            | Một câu hỏi = 1/23 = 4.3% metric. Thay đổi nhỏ trông như biến động lớn                                                                                             | Tăng`max_results` lên 100+, đo lại độ rộng khoảng tin cậy của delta                                                                                                            |
| `judge_accuracy` phụ thuộc API key          | Không tái hiện được giữa hai chế độ judge                                                                                                                            | Ghi`judge_mode` vào chính file metrics JSON, hoặc dùng judge tất định làm mặc định và LLM judge là tùy chọn                                                               |
| Quality check không bắt lỗi ngữ nghĩa      | `inject_noise` và `truncate_title` lọt qua toàn bộ 6 check                                                                                                             | Thêm check thống kê: độ dài summary lệch quá n độ lệch chuẩn so với phân phối baseline, tỉ lệ ký tự không phải chữ cái, độ dài title tối thiểu                 |
| Corruption tất định, chỉ một cấu hình    | Chỉ đo được một điểm, không biết quan hệ liều lượng – tác động                                                                                               | Quét`ratio` từ 0.1 đến 0.5 rồi vẽ đường `mean_token_f1` theo mức độ corruption                                                                                             |

## 13. Checklist trước khi nộp

- [X] Thông tin nhóm và repository chính xác
- [X] Phân công khớp với module, artifact và kết quả thực tế
- [X] Lệnh tái hiện đã được chạy lại trên phiên bản dùng để nộp — cả hai entrypoint exit 0
- [X] Baseline, corrupted và repaired dùng cùng evaluation set — đã xác minh `id` khớp theo thứ tự
- [X] Bảng metrics khớp với các file trong `data/results/`
- [X] Quality/freshness conclusions khớp với `data/quality/`
- [X] Các đường dẫn báo cáo và artifact truy cập được
- [X] Mỗi thành viên đã hoàn thành báo cáo vai trò riêng
- [X] Không có `.env`, API key, token hoặc secret trong source, report, log hay ảnh — đã quét toàn bộ lịch sử git
