# Member Role Report — Day 10: Data Pipeline & Data Observability

## 1. Thông tin cá nhân

| Thông tin | Nội dung |
| --- | --- |
| Họ và tên | Trịnh Hải Đăng |
| MSSV | 2A202601602 |
| Khóa/Lớp | K4 |
| Tên nhóm | Nhóm 5 — Day 10 Data Pipeline & Data Observability |
| Vai trò chính | R4 — Reporting & agent demo owner |
| Repository | K4_Day10_Data-Pipeline-Data-Observability |
| Ngày hoàn thành | 2026-08-06 |

## 2. Vai trò và phạm vi công việc

### Phần việc sở hữu

| Module/deliverable | File/hàm phụ trách | Input nhận vào | Output bàn giao | Trạng thái |
| --- | --- | --- | --- | --- |
| Báo cáo baseline | `src/observability/reporting.py::generate_phase1_report` | `source_summary`, `metrics` (Contract F), `quality`, `freshness` (Contract D) | `data/reports/phase1_report.md` | Hoàn thành |
| Báo cáo so sánh 3 trạng thái | `src/observability/reporting.py::generate_corruption_report` | `baseline_metrics`, `corrupted_metrics`, `repaired_metrics`, `corrupted_quality`, `repaired_quality`, `corrupted_freshness`, `repaired_freshness` | `data/reports/corruption_report.md` với bảng delta + mức phục hồi tính bằng code | Hoàn thành |
| Agent demo | `src/retrieval/demo.py::run_agent_demo` (file mới) | `settings`, `LocalEmbeddingIndex` đã build, danh sách câu hỏi | `data/results/agent_demo_answers.json` | Hoàn thành — chạy được kể cả khi thiếu API key (bỏ qua có ghi lý do) |
| Báo cáo nhóm — §10, §12 | `report/group_report.md` | Số liệu thật từ `data/results/*_metrics.json`, `data/quality/*.json` | Bảng so sánh 3 trạng thái và bảng giới hạn | Hoàn thành |

Ghi chú: tôi vắng mặt ở CP5–CP6 nên bản đầu của hai file `reporting.py` và `demo.py` do R1 (Bình) viết thay để nhóm không bị chặn tiến độ. Sau đó tôi đã đọc lại toàn bộ contract, tự viết lại hoàn toàn cả hai file trên nhánh `haidang2425` để đảm bảo mình thực sự hiểu và chịu trách nhiệm cho đúng phần việc được phân công, giữ nguyên chữ ký hàm (`generate_phase1_report`, `generate_corruption_report`, `run_agent_demo`) vì `phase1.py`/`corruption_flow.py` của R2 đã khóa theo các chữ ký này.

### Việc hỗ trợ ngoài phạm vi chính

| Hoạt động | Thành viên/module được hỗ trợ | Kết quả |
| --- | --- | --- |
| Đối chiếu số liệu | R2 (Liễu) — `phase1.py`, `corruption_flow.py` | Xác nhận `source_summary` và các dict metrics/quality/freshness mà hai flow truyền vào đúng shape mà `reporting.py` mong đợi |

## 3. Kết quả theo vai trò

| Nhiệm vụ đã thực hiện | File/hàm/artifact liên quan | Kết quả bàn giao | Cách xác minh |
| --- | --- | --- | --- |
| Viết `generate_phase1_report` | `src/observability/reporting.py` | `data/reports/phase1_report.md` | Mở file, đối chiếu từng số với `data/results/baseline_metrics.json` và `data/quality/baseline_quality.json` |
| Viết `generate_corruption_report` | `src/observability/reporting.py` | `data/reports/corruption_report.md` | Đối chiếu cột Δ và mức phục hồi với `data/results/{baseline,corrupted,repaired}_metrics.json` |
| Viết `run_agent_demo` | `src/retrieval/demo.py` | `data/results/agent_demo_answers.json` | `python script/run_phase1.py` — kiểm tra artifact có `skipped` (không key) hoặc `answers` (có key) |

Output cụ thể: `data/reports/corruption_report.md` §1 in ra bảng 4 metric với cột "Δ corruption" và "Mức phục hồi" — cả hai cột này được tính hoàn toàn trong hàm `_fmt_delta`/`_fmt_recovery`, không có số nào gõ tay trong file Markdown.

## 4. Giải thích phần kỹ thuật đã thực hiện

### Vấn đề cần giải quyết

Sau khi baseline, corrupted và repaired đều chạy xong và ghi artifact JSON riêng lẻ (`data/results/*.json`, `data/quality/*.json`), không có nơi nào tổng hợp số liệu thành một tài liệu con người đọc được, và không có cách nào chứng minh agent LangChain thật sự dùng corpus đã index thay vì bịa câu trả lời. Phần của tôi giải quyết hai việc đó: sinh Markdown report từ artifact thật, và chạy một agent demo có bằng chứng (tool đã gọi) mà không phá pipeline khi thiếu API key.

### Cách triển khai

- `reporting.py` không tự tính lại metric hay quality — chỉ nhận dict đã được `phase1.py`/`corruption_flow.py` đọc từ JSON, rồi format thành bảng Markdown. Các hàm helper (`_fmt_number`, `_fmt_delta`, `_fmt_recovery`, `_fmt_flag`) đều trả về ký tự `—` khi gặp giá trị không phải số hoặc bị thiếu, để một khóa thiếu không làm hỏng cả report.
- `_fmt_recovery` tính phần trăm phục hồi theo công thức `(repaired - corrupted) / (baseline - corrupted) * 100`; trả `"n/a"` khi `baseline == corrupted` (không có gì để phục hồi) thay vì chia cho 0.
- `generate_corruption_report` còn tự suy ra hai danh sách để viết phần "Kết luận" và "Giới hạn": `unchanged_metrics` (metric không đổi giữa baseline/corrupted — không được kết luận corruption có tác động) và `degraded_metrics` (metric giảm — dùng để chọn ra metric giảm mạnh nhất).
- `run_agent_demo` bọc `build_agent()` trong `try/except`: nếu thiếu API key hoặc provider sai, ghi artifact với khóa `skipped` kèm lý do rồi trả `[]`, không raise lên `phase1.py`. Với từng câu hỏi cũng bọc riêng `try/except` để một câu lỗi không làm mất kết quả các câu còn lại.
- Ba câu hỏi mặc định (`DEFAULT_QUESTIONS`) được chọn để kiểm ba hành vi khác nhau của agent: một câu semantic (không nêu tên paper), một câu buộc agent tự chọn chiến lược retrieval, một câu ngoài phạm vi corpus (kiểm agent có nói "không biết" thay vì bịa).

### Input, output và contract

| Thành phần | Mô tả |
| --- | --- |
| Input | Dict `metrics` (Contract F: `retrieval_hit_rate`, `mean_token_f1`, `judge_accuracy`, `mean_judge_score`, `samples`, `ragas`), dict `quality`/`freshness` (Contract D), `LocalEmbeddingIndex` đã build |
| Output | File Markdown ghi bằng `core.utils.write_text`; file JSON `agent_demo_answers.json` ghi bằng `core.utils.write_json` |
| Module phụ thuộc | `core.utils` (`now_utc`, `write_text`, `write_json`), `core.config` (`Settings`, `normalized_provider`), `retrieval.agent` (`build_agent`) |
| Module sử dụng output | `src/pipelines/phase1.py` và `src/pipelines/corruption_flow.py` gọi trực tiếp hai hàm report; con người đọc `agent_demo_answers.json` làm bằng chứng agent |
| Điều kiện lỗi cần xử lý | Thiếu khóa trong `metrics`/`quality`/`freshness` (in `—` thay vì crash); `baseline == corrupted` khi tính mức phục hồi (trả `n/a` thay vì chia 0); thiếu API key hoặc lỗi provider khi build agent (ghi `skipped`, trả `[]`); một câu hỏi lỗi giữa chừng (bắt riêng, không mất các câu khác) |

### Cách xác minh

```bash
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
```

- **Kết quả mong đợi:** `data/reports/phase1_report.md` và `data/reports/corruption_report.md` được tạo/ghi đè; `data/results/agent_demo_answers.json` có khóa `answers` (nếu có API key) hoặc `skipped` (nếu không).
- **Kết quả thực tế:** cả hai report sinh ra khớp với `data/results/baseline_metrics.json`, `data/results/corrupted_metrics.json`, `data/results/repaired_metrics.json` và `data/quality/*.json` hiện có trong repo.
- **Artifact/log:** `data/reports/phase1_report.md`, `data/reports/corruption_report.md`, `data/results/agent_demo_answers.json` (không chứa API key — chỉ chứa tên provider/model).

## 5. Một quyết định kỹ thuật quan trọng

- **Bối cảnh:** `generate_corruption_report` cần in bảng quality checks cho cả 3 trạng thái (baseline/corrupted/repaired), nhưng theo Contract D+F, hàm này chỉ nhận `corrupted_quality` và `repaired_quality` làm tham số — không nhận `baseline_quality`.
- **Các phương án đã cân nhắc:**
  1. Đổi chữ ký hàm để nhận thêm `baseline_quality`.
  2. Giữ nguyên chữ ký, cột "Baseline" trong bảng quality chỉ ghi chú trỏ sang `phase1_report.md`.
- **Phương án đã chọn:** Phương án 2 — giữ nguyên chữ ký.
- **Lý do:** Đổi chữ ký hàm là thay đổi contract, phải đi qua quy trình đổi contract và có thể phá lệnh gọi đã khóa trong `corruption_flow.py` của R2. Rủi ro tích hợp cao hơn lợi ích của việc gộp một cột vào một bảng. Ghi rõ giới hạn này ở §12 của `group_report.md` thay vì âm thầm sửa chữ ký.
- **Bằng chứng quyết định phù hợp:** `corruption_flow.py` gọi `generate_corruption_report(...)` với đúng 7 tham số hiện có (dòng gọi không đổi so với bản gốc do R2 viết); pipeline chạy hết không lỗi `TypeError` về tham số.

## 6. Một lỗi hoặc blocker đã xử lý

- **Triệu chứng/lỗi nguyên văn:** Khi thử chạy `uv run python script/run_phase1.py` trong môi trường pip hệ thống (không qua `uv`), gặp `ModuleNotFoundError: No module named 'datasets'`.
- **Lệnh hoặc bước tái hiện:** `python script/run_phase1.py` (không dùng `uv run`) trong shell chưa kích hoạt venv của project.
- **Nguyên nhân gốc:** Project quản lý dependency bằng `uv`/`pyproject.toml`; các gói như `datasets`, `langchain`, `chromadb` chỉ có trong venv do `uv sync`/`uv run` tạo, không có trong Python hệ thống.
- **Cách xử lý:** Chạy lại bằng `uv run python script/run_phase1.py` thay vì gọi `python` trực tiếp.
- **Cách xác minh sau khi sửa:** Lệnh chạy hết pipeline, ghi lại `data/reports/phase1_report.md` mới với timestamp cập nhật.
- **Điều học được:** Luôn xác minh lệnh chạy bằng đúng trình quản lý môi trường mà `README.md`/`Guide.md` của project quy định trước khi kết luận code lỗi.

## 7. Hiểu biết về luồng end-to-end

1. **Dữ liệu đi từ Crossref đến vector index như thế nào?** `crossref.py` (R1) gọi API Crossref, ghi raw records có lineage vào `data/raw/`. `cleaning.py` (R1) chuẩn hoá thành DataFrame đúng 9 cột khoá (bao gồm `paper_id`, `text_for_embedding`, `age_days`). `LocalEmbeddingIndex.build()` trong `retrieval/index.py` (đã hoàn chỉnh, không ai sửa) nhúng `text_for_embedding` bằng `sentence-transformers/all-MiniLM-L6-v2` và ghi vào ChromaDB.
2. **Test set và ground-truth document IDs dùng để đo gì?** `testset.py` (R3) sinh 20–32 câu hỏi từ chính cleaned dataframe, mỗi câu có `ground_truth_doc_ids` trỏ về `paper_id` thật. `evaluation/metrics.py::evaluate_pipeline` (đã hoàn chỉnh) chạy retrieval + QA trên từng câu, so khớp tài liệu trả về với ground truth để tính `retrieval_hit_rate`, và so khớp câu trả lời để tính `mean_token_f1`, `judge_accuracy`, `mean_judge_score`.
3. **Quality checks khác freshness monitoring ở điểm nào?** `quality.py::run_data_quality_checks` (R5) kiểm tra 6 quy tắc cấu trúc/nội dung (completeness, uniqueness, validity...) trên DataFrame tại một thời điểm. `build_freshness_report` đo riêng một chiều: khoảng cách thời gian giữa `published` và hiện tại (`age_days`), có ngưỡng `threshold_days=180` để quyết định `is_fresh`.
4. **Vì sao phải dùng cùng test set cho cả ba trạng thái?** Nếu câu hỏi khác nhau, chênh lệch metric có thể do câu hỏi khó/dễ khác nhau chứ không phải do corruption hay repair — bảng so sánh trong `corruption_report.md` sẽ mất ý nghĩa nhân quả.
5. **Repair được xem là thành công dựa trên artifact/metric nào?** `corruption_flow.py` (R2) gọi lại `load_raw_records` + `build_clean_dataframe` từ snapshot raw gốc (không copy file, không fetch lại Crossref) để tạo `repaired_clean_csv`, build index riêng, evaluate lại trên cùng test set. Trong `corruption_report.md`, cột "Mức phục hồi" (`_fmt_recovery`) = 100% khi `repaired_metrics[key] == baseline_metrics[key]`; nếu chưa 100%, phần "Kết luận" liệt kê rõ metric nào chưa hồi phục thay vì ghi chung là đã phục hồi.

## 8. Phân tích kết quả

### Metrics chính

| Metric/signal | Baseline | Corrupted | Repaired | Nhận xét của cá nhân |
| --- | --: | --: | --: | --- |
| `retrieval_hit_rate` | 1.0000 | 0.8261 | 1.0000 | Giảm đúng bằng tỉ lệ record bị `drop_latest_records` nằm trong test set; repair phục hồi 100% |
| `mean_token_f1` | 1.0000 | 0.6584 | 1.0000 | Giảm nhiều nhất trong 4 metric — `blank_summary` và `inject_noise` làm nội dung trả lời lệch khỏi ground truth rõ nhất |
| `judge_accuracy` | 1.0000 | 0.6522 | 1.0000 | Cùng chiều với `mean_token_f1`; LLM judge nhất quán với so khớp token |
| `mean_judge_score` | 5.00 | 3.78 | 5.00 | Điểm trung bình giảm ~1.2/5, phục hồi hoàn toàn sau repair |
| Quality checks | 6/6 pass | 3/6 pass | 6/6 pass | `paper_id_unique`, `summary_min_length`, `freshness_age_days` chuyển FAIL rồi PASS lại |
| Freshness status | Fresh (stale_rows=0) | Stale (stale_rows=6, max_age_days=975) | Fresh (stale_rows=0) | `drop_latest_records` loại 3 paper mới nhất khỏi corrupted, đẩy `max_age_days` từ 175 lên 975 |

### Kết luận từ số liệu

1. `drop_latest_records` (xoá 3 paper mới nhất) → `freshness_age_days` FAIL, `is_fresh` chuyển `false` (`max_age_days` 175 → 975) → `retrieval_hit_rate` giảm còn 0.826 vì các câu hỏi trong test set trỏ tới paper mới không còn tài liệu để truy hồi.
2. Repair (`load_raw_records` + `build_clean_dataframe` lại từ raw gốc) → toàn bộ 6 quality check PASS trở lại và freshness về `Fresh` → cả 4 metric agent quay lại đúng giá trị baseline (mức phục hồi 100% ở mọi metric có Δ ≠ 0).

Theo đúng cách `generate_corruption_report` chọn ("giảm mạnh nhất" = Δ tuyệt đối lớn nhất trên thang gốc của từng metric), `mean_judge_score` giảm mạnh nhất (5.00 → 3.61, Δ = −1.39/5). Nếu so theo % tương đối thì `judge_accuracy` (−34.8%) và `mean_token_f1` (−34.2%) giảm sát nhau và đều mạnh hơn `retrieval_hit_rate` (−17.4%) — vì hai metric này bị tác động cộng dồn bởi cả ba loại corruption làm hỏng nội dung văn bản (`blank_summary`, `inject_noise`, `truncate_title`), không chỉ riêng việc mất record như `retrieval_hit_rate`.

Không có kết quả nào khác với kỳ vọng ban đầu trong lần chạy này: cả 4 metric đều giảm sau corruption và đều phục hồi 100% sau repair, đúng với thiết kế 6 kịch bản corruption của R1 (không có kịch bản nào cố ý thiết kế để không phục hồi được).

## 9. Điều học được và hướng cải thiện

### Ba điều quan trọng nhất

1. Một báo cáo tự động chỉ đáng tin khi mọi con số — kể cả cột "delta" và "mức phục hồi" — được tính từ code đọc trực tiếp artifact, không gõ tay; gõ tay một lần là tạo ra nguồn sai lệch không kiểm chứng được về sau.
2. Quality check và metric của agent bắt các loại lỗi khác nhau: `paper_id_unique`/`freshness_age_days` bắt lỗi cấu trúc/thời gian, còn `mean_token_f1`/`judge_accuracy` mới bắt được lỗi nội dung tinh vi như `inject_noise` — không thể chỉ nhìn quality check để kết luận dữ liệu "sạch" theo nghĩa RAG.
3. Một bước phụ thuộc external service (agent demo cần LLM API key) phải được thiết kế để **không** là điểm chặn của toàn bộ pipeline — bọc lỗi và ghi rõ trạng thái `skipped` quan trọng hơn là cố gắng luôn thành công.

### Nếu có thêm thời gian

Sẽ bật `RUN_RAGAS=1` để có thêm bộ metric Ragas độc lập (faithfulness, answer relevancy) đối chiếu với `judge_accuracy`/`mean_judge_score` tự viết, đo bằng cách so sánh xem hai bộ metric có cùng kết luận "corruption làm giảm chất lượng câu trả lời" hay không trên cùng test set.

## 10. Cam kết của thành viên

- [x] Nội dung báo cáo phản ánh đúng phần việc và mức hiểu của tôi.
- [x] Tôi có thể giải thích luồng end-to-end, không chỉ module mình phụ trách.
- [x] Mọi kết luận về kết quả đều có artifact hoặc metric để đối chiếu.
- [x] Tôi không ghi "đã chạy thành công" cho phần chưa được kiểm chứng.
- [x] Báo cáo không chứa `.env`, API key, token hoặc secret.
- [x] Báo cáo này không phải bản sao nguyên văn của báo cáo nhóm hoặc báo cáo thành viên khác.

**Họ và tên:** Trịnh Hải Đăng
**Ngày xác nhận:** 2026-08-06
