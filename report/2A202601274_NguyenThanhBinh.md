# Member Role Report — Day 10: Data Pipeline & Data Observability

> **Trạng thái bản nháp:** §1–§6 và §8 (phần quality/freshness) đã điền bằng số liệu thật từ artifact.
> §7, §9, §10 và các ô `[ ]` trong bảng metrics agent còn trống — phải tự viết/điền sau khi
> `run_phase1.py` và `run_corruption_flow.py` chạy xong. Xóa khối chú thích này trước khi nộp.

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Nguyễn Thanh Bình |
| MSSV | 2A202601274 |
| Khóa/Lớp | K4 |
| Tên nhóm | [Tên hoặc mã nhóm] |
| Vai trò chính | R1 — Data foundation owner + release admin |
| Repository | https://github.com/NguyenThanhBinh108/K4_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Raw ingestion | `src/ingestion/crossref.py` — `parse_crossref_payload`, `fetch_source_records`, `load_raw_records` | Crossref REST API | `data/raw/crossref_response.json` (thô), `data/raw/crossref_records.json` (23 record đã parse) | Hoàn thành |
| Cleaning & data modeling | `src/ingestion/cleaning.py` — `build_clean_dataframe`, `build_text_for_embedding`, `enforce_clean_dtypes` | 23 `PaperRecord` | `data/clean/papers_clean.csv` + `.json` (23 dòng × 16 cột) | Hoàn thành |
| Corruption | `src/ingestion/corruption.py` — `corrupt_clean_dataframe` | Clean dataframe | `data/clean/papers_clean_corrupted.*`, `data/results/corruption_log.json` | Hoàn thành |
| Data contract | `DATA_CONTRACT.md` | Code có sẵn trong starter | 8 contract A–H cho cả nhóm | Hoàn thành |
| Bằng chứng lineage | `script/verify_data_lineage.py` | Toàn bộ artifact data | 24 assertion tự động, exit code | Hoàn thành |
| Release admin | `.gitignore`, merge, commit `data/` | PR của 4 thành viên | Nhánh `main` tích hợp | Đang thực hiện |

Không sở hữu: `src/pipelines/` (Liễu), `src/evaluation/testset.py` (Vũ), `src/observability/` (Đăng, Linh).

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Phát hiện `subject` rỗng 23/23, cảnh báo trước khi code | Vũ — `evaluation/testset.py` | Contract C cấm `question_type=categories`, tránh baseline bị thổi phồng |
| Bàn giao số liệu đích của 6 quality check trên baseline/corrupted | Linh — `observability/quality.py` | Linh có bảng kỳ vọng để assert thay vì đoán |
| Cố định 9 cột khóa và dtype trước khi build index | Liễu — `pipelines/phase1.py` | Tránh lỗi metadata ChromaDB khi ghép pipeline |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Gọi Crossref có retry/backoff, lưu 2 dạng raw artifact | `src/ingestion/crossref.py`, `data/raw/` | 24 item nhận, 23 record hợp lệ | `python script/verify_data_lineage.py` |
| Bóc JATS XML, chuẩn hóa ngày, dedupe, tính `age_days` | `src/ingestion/cleaning.py`, `data/clean/papers_clean.csv` | 23 dòng, `paper_id` unique, không `NaN` | `df.attrs["cleaning_stats"]` + script lineage |
| 6 kịch bản corruption có log | `src/ingestion/corruption.py`, `data/results/corruption_log.json` | 17/23 paper bị tác động, 3 quality check lật trạng thái | Script lineage mục 2 |
| Chứng minh repair từ raw | `script/verify_data_lineage.py` mục 3 | 23/23 bản ghi trùng khớp baseline trên 5 trường | Script lineage mục 3 |

Một output cụ thể mà phần việc của tôi tạo ra:

`script/verify_data_lineage.py` chạy 24 assertion và trả exit code. Nó truy một `paper_id`
(`10.2118/234689-pa`) qua bốn tầng — raw API response → raw records → clean dataset → embedding
manifest — và xác nhận `title`, `published`, `text_for_embedding` giữ nguyên qua cả ba lần chuyển đổi.
Sau đó nó đối chiếu corrupted dataset với từng dòng trong `corruption_log.json`, và cuối cùng chạy lại
cleaning từ raw để chứng minh repair khôi phục đúng 23/23 bản ghi trên 5 trường, chứ không phải copy
lại file baseline.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Toàn bộ pipeline RAG đứng trên chất lượng của khối data. Nếu raw không truy vết được thì không repair
được; nếu clean schema sai một cột thì index không build được; nếu corruption chỉ làm hỏng metadata mà
không chạm vào embedding thì metric không đổi và cả bài lab không chứng minh được gì.

### Cách triển khai

**Ingestion.** Gọi `https://api.crossref.org/works` với `query.bibliographic`, filter
`from-pub-date,has-abstract:true`, retry 4 lần backoff `2**attempt` cho 429/5xx và honor header
`Retry-After`. Lưu response **thô trước khi parse** làm bằng chứng lineage, rồi mới parse thành
`PaperRecord` và lưu snapshot thứ hai. Abstract của Crossref là JATS XML nên phải strip tag và
`html.unescape` hai lần (entity còn lồng trong tag đã bỏ). Ngày ở dạng `date-parts` có thể thiếu
tháng/ngày nên điền `01`.

**Cleaning.** 5 rule loại bỏ, mỗi rule đều đếm và ghi vào `df.attrs["cleaning_stats"]` — không làm mất
record âm thầm. Dedupe theo `paper_id`, tính `age_days`, build `text_for_embedding` gộp cả 5 trường.
Bước cuối `enforce_clean_dtypes` ép mọi cột khóa về `str`/`int` vì ChromaDB chỉ nhận
`str/int/float/bool` trong metadata — một `NaN` hay `pd.Timestamp` lọt vào là `collection.add` báo lỗi.

**Corruption.** `df.copy(deep=True)` ngay dòng đầu để baseline nguyên vẹn. 6 kịch bản, mỗi kịch bản ghi
`paper_ids`, `params` và `expected_signal` vào log. Sau khi sửa dữ liệu thì **rebuild
`text_for_embedding` bằng chính hàm của cleaning** — import lại `build_text_for_embedding` chứ không
chép template, để hai bên không bao giờ lệch nhau.

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Crossref REST API (ingestion); `list[PaperRecord]` (cleaning); clean DataFrame (corruption) |
| Output | 2 raw artifact JSON; DataFrame 16 cột trong đó 9 cột khóa; corrupted DataFrame + corruption log |
| Module phụ thuộc | `core/config.py` (paths, query, ngưỡng freshness), `core/utils.py` |
| Module sử dụng output | `pipelines/phase1.py`, `pipelines/corruption_flow.py`, `evaluation/testset.py`, `observability/quality.py`, `retrieval/index.py` |
| Điều kiện lỗi cần xử lý | Crossref 429/5xx và timeout; abstract thiếu hoặc quá ngắn; `date-parts` thiếu tháng/ngày; DOI trùng; `subject` rỗng |

### Cách xác minh

```bash
python script/verify_data_lineage.py
```

- **Kết quả mong đợi:** 24 assertion PASS, exit code 0.
- **Kết quả thực tế:** 24/24 PASS. Lineage nguyên vẹn qua 4 tầng; corruption khớp log; repair khôi phục 23/23 bản ghi.
- **Artifact/log:** `data/raw/`, `data/clean/`, `data/results/corruption_log.json`. Không chứa secret.

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** Lần fetch đầu tiên cho ra `age_days` **âm** (−679 … −147) và `published` nằm ở
  **2026-12 … 2028-06**, trong khi hôm chạy là 2026-08-06. Toàn bộ phần freshness monitoring trở nên
  vô nghĩa, và corruption `stale_dates` cộng thêm 800 ngày vẫn không đủ đẩy bản ghi qua ngưỡng 180 ngày.
- **Các phương án đã cân nhắc:**
  1. Giữ `issued` và hạ ngưỡng freshness — che triệu chứng, không sửa nguyên nhân.
  2. Dùng `created` (thời điểm bản ghi vào Crossref) làm `published` — luôn ở quá khứ nhưng mất
     ý nghĩa "ngày xuất bản".
  3. Lấy `min(issued, created)`.
- **Phương án đã chọn:** Phương án 3.
- **Lý do:** Crossref `issued` là ngày xuất bản **danh nghĩa do nhà xuất bản khai** — với số tạp chí
  sắp phát hành, nó nằm ở tương lai. `created` là thời điểm bản ghi thực sự tồn tại trong Crossref.
  `min()` cho ra ngày sớm nhất mà paper thực sự có mặt, giữ được ngữ nghĩa "đã công bố" mà không bao
  giờ ra tương lai. Correctness thắng, và không phải chỉnh ngưỡng của người khác.
- **Bằng chứng quyết định phù hợp:** Sau khi đổi, `age_days` = 5 … 175 (đều dương), `published` =
  2026-02-12 … 2026-08-01, baseline `stale_rows = 0` → `is_fresh = true`, và corruption `stale_dates`
  đẩy `max_age_days` từ 175 lên 975 → `is_fresh = false`. Tín hiệu freshness giờ phân biệt được
  baseline với corrupted.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng:** `corruption_log.json` cho thấy `inject_noise` và `truncate_title` tác động lên
  **đúng cùng 4 `paper_id`**, trong khi hai kịch bản này lẽ ra phải rơi vào hai nhóm bản ghi khác nhau.
  Hệ quả: corruption dồn vào 13/23 paper, để lại nhiều paper hoàn toàn sạch, làm impact đo được yếu đi.
- **Lệnh hoặc bước tái hiện:** đọc `paper_ids` của hai operation trong `data/results/corruption_log.json`
  và so sánh hai tập hợp.
- **Nguyên nhân gốc:** Hàm chọn bản ghi `_spread_ids` lấy các dòng trải đều theo `published` giảm dần,
  mỗi kịch bản lệch một `offset`. Nhưng `inject_noise` chọn trên frame **đã lọc bỏ** các dòng
  `blank_summary` — mà các dòng đó nằm cách đều nhau đúng bằng step, nên việc lọc làm tọa độ dịch đi
  vừa đúng bằng chênh lệch offset giữa hai kịch bản, khử lẫn nhau và cho ra cùng một tập chỉ số.
- **Cách xử lý:** Chọn trên **toàn bộ frame** rồi mới trừ các dòng đã blank, thay vì chọn trên frame
  đã lọc. Ghi chú nguyên nhân ngay tại chỗ trong `corruption.py` để không ai vô tình đảo lại.
- **Cách xác minh sau khi sửa:** đếm giao của mọi cặp kịch bản. Trước: `inject_noise ∩ truncate_title`
  = 4/4. Sau: mọi cặp giao nhau nhiều nhất 1 bản ghi, tổng số paper bị tác động tăng từ 13 lên **17/23**.
- **Điều học được:** Lấy mẫu tất định dễ đọc và dễ tái hiện hơn random, nhưng khi lấy mẫu trên các frame
  đã bị lọc khác nhau thì các chỉ số có thể trùng nhau một cách không hiển nhiên. Phải kiểm tra giao của
  các tập được chọn, chứ không chỉ kiểm tra kích thước từng tập.

## 7. Hiểu biết về luồng end-to-end

> **Tự viết bằng lời của mình.** Năm câu hỏi dưới đây phải trả lời được khi bảo vệ. Gợi ý mốc để bám:
> (1) 4 tầng trong `verify_data_lineage.py`; (2) `ground_truth_doc_ids` so với `retrieved_doc_ids` trong
> `metrics.py`; (3) quality đo tính đúng đắn của bảng, freshness đo độ tươi theo thời gian;
> (4) đổi test set thì 3 cột số không còn so sánh được; (5) tiêu chí repair trong Contract H.

1. Dữ liệu đi từ Crossref đến vector index như thế nào?
2. Evaluation set và ground-truth document IDs dùng để đo retrieval/answer quality ra sao?
3. Quality checks khác freshness monitoring ở điểm nào trong bài lab?
4. Vì sao phải dùng cùng test set cho baseline, corrupted và repaired?
5. Repair được xem là thành công dựa trên artifact và metric nào?

**Câu trả lời:**

[Viết câu trả lời tại đây.]

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | ---: | ---: | ---: | --- |
| `retrieval_hit_rate` | [ ] | [ ] | [ ] | Chờ `run_phase1.py` và `run_corruption_flow.py` |
| `mean_token_f1` | [ ] | [ ] | [ ] | Chờ |
| `judge_accuracy` | [ ] | [ ] | [ ] | Chờ |
| `mean_judge_score` | [ ] | [ ] | [ ] | Chờ |
| Quality checks pass | 6/6 | 3/6 | [ ] | 3 check lật trạng thái, xem bảng dưới |
| Freshness status | fresh | stale | [ ] | `max_age_days` 175 → 975 |

Chi tiết 6 quality check (đo trên `data/clean/papers_clean.csv` và `papers_clean_corrupted.csv`):

| Check | Baseline | Corrupted | Kết quả |
| --- | ---: | ---: | --- |
| `row_count_min` (≥10) | 23 | 23 | pass → pass |
| `paper_id_not_null` (=0) | 0 | 0 | pass → pass |
| `paper_id_unique` (=0) | 0 | 3 | **PASS → FAIL** |
| `title_not_empty` (=0) | 0 | 0 | pass → pass |
| `summary_min_length` (=0) | 0 | 5 | **PASS → FAIL** |
| `freshness_age_days` (=0) | 0 | 6 | **PASS → FAIL** |

Freshness: baseline `is_fresh=true`, `max_age_days=175`, khoảng 2026-02-12 … 2026-08-01.
Corrupted `is_fresh=false`, `max_age_days=975`, khoảng 2023-12-05 … 2026-07-03.

### Kết luận từ số liệu

1. `stale_dates` đẩy lùi `published` 800 ngày trên 5 bản ghi → `freshness_age_days` từ 0 lên 6 dòng vi
   phạm và `is_fresh` lật từ `true` sang `false` → [chờ metric agent].
2. Repair chạy lại `build_clean_dataframe` từ `data/raw/crossref_records.json` → 23/23 bản ghi trùng
   khớp baseline trên `title`, `summary`, `published`, `authors_joined`, `text_for_embedding`, và 3
   paper bị `drop_latest_records` xóa đã quay lại → [chờ metric agent].

Corruption nào ảnh hưởng rõ nhất và vì sao?

[Điền sau khi có metrics. Giả thuyết của tôi: `drop_latest_records` — vì các paper bị xóa hẳn khỏi
index nên retrieval không thể trả về chúng, `retrieval_hit_rate` sẽ tụt thẳng trên mọi câu hỏi liên
quan; các corruption khác chỉ làm embedding lệch chứ document vẫn còn.]

Kết quả nào khác với kỳ vọng ban đầu?

[Điền sau khi có metrics.]

**Hai điều cần lưu ý khi đọc bảng trên:**

- `row_count_min`, `paper_id_not_null` và `title_not_empty` **không đổi** giữa baseline và corrupted.
  Không được kết luận "mọi tín hiệu quality đều phát hiện được corruption" — chỉ 3/6 check phát hiện.
  `inject_noise` và `truncate_title` không làm check nào fail; chúng chỉ lộ ra qua metric của agent.
- Số liệu của nhóm khác sẽ khác vì Crossref là nguồn sống. Chỉ so sánh trong cùng bài làm, trên cùng
  test set và cùng snapshot raw.

## 9. Điều học được và hướng cải thiện

> **Tự viết bằng lời của mình.** Gợi ý mốc: bài học về lineage/raw artifact; bài học về ngữ nghĩa của
> trường dữ liệu từ nguồn bên ngoài (`issued` vs `created`, `subject` rỗng); bài học về việc corruption
> phải chạm vào embedding chứ không chỉ metadata.

### Ba điều quan trọng nhất

1. [Điều học được về data pipeline.]
2. [Điều học được về data quality/observability.]
3. [Điều học được về ảnh hưởng của data đến RAG agent.]

### Nếu có thêm thời gian

[Nêu một cải thiện cụ thể, lý do và cách đo cải thiện đó.]

## 10. Cam kết của thành viên

> Chỉ tự đánh dấu sau khi đã đọc lại và xác nhận từng dòng là đúng với phần việc của mình.

- [ ] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [ ] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [ ] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [ ] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [ ] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [ ] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Nguyễn Thanh Bình
**Ngày xác nhận:** [YYYY-MM-DD]
