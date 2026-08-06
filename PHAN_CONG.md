# PHÂN CÔNG & QUY TẮC CHỐNG TRÙNG CHÉO

**Day 10 — Data Pipeline & Data Observability** · Nhóm 5 người · 4 giờ (CP0–CP6)

> Mỗi file có **đúng một chủ sở hữu**. Mọi ràng buộc giữa các phần việc được viết ra trước trong [DATA_CONTRACT.md](DATA_CONTRACT.md) thay vì thỏa thuận miệng, nên năm người có thể code song song mà không chờ nhau và không sửa đè lên nhau.

Nguồn: `phan-cong-day-10-data-pipeline-4h(2).html` · [Guide.md](Guide.md) · [Rubric.md](Rubric.md) · [report/README.md](report/README.md) và code trong `src/`.

---

## 1. Năm vai trò

Hai điều chỉnh so với bảng phân công gốc, ghi lý do vào `group_report.md`:

1. **Bình gom toàn bộ `src/ingestion/`** — ingestion, cleaning và corruption về một người. Ba module này chia sẻ Contract A, B, E; gom lại thì phần thương lượng schema xuyên người biến mất, đây là nguồn xung đột lớn nhất của bài.
2. **Orchestration tách khỏi data.** Vì Bình đã ôm 3 file nặng nhất, `src/pipelines/` chuyển sang Liễu. Người orchestrate không cần viết logic, chỉ nối các hàm đã khóa chữ ký — nhưng phải hiểu toàn bộ contract, nên đây là vai trò học được nhiều nhất.

Bản gốc cho vai RAG phụ trách `src/retrieval/`, nhưng thư mục đó đã viết sẵn hoàn chỉnh trong starter nên không còn code để giao. Phần việc đó được thay bằng hai file mới (`retrieval/demo.py`, `script/smoke_retrieval.py`) chia cho Đăng và Linh.

### R1 — Nguyễn Thanh Bình · Data foundation owner + release admin

`2A202601274` · `@NguyenThanhBinh108` · **chủ repo**

| | |
|---|---|
| **Sở hữu** | `src/ingestion/crossref.py`<br>`src/ingestion/cleaning.py`<br>`src/ingestion/corruption.py`<br>`DATA_CONTRACT.md` · `.gitignore` |
| **Contract** | **A** (raw schema) · **B** (clean schema) · **E** (corruption log) · nguồn của **H** (repair) |
| **Giao** | Raw records có lineage · clean dataset đúng 9 cột khóa · corrupted dataset + corruption log |
| **Xác minh** | `data/raw/` có 2 file · `papers_clean.csv` đủ 9 cột, `paper_id` unique, không `NaN` · `corruption_log.json` đủ 6 kịch bản |
| **Admin** | Người **duy nhất commit `data/`**, duyệt PR, duyệt mọi thay đổi contract |

Ba file này là toàn bộ đường đi của dữ liệu. `build_clean_dataframe` được gọi **hai lần** (baseline và repaired) nên phải thuần: cùng input → cùng output, không đọc/ghi file, không phụ thuộc state ngoài.

**Deadline gắt nhất:** `crossref.py` phải xong và `data/raw/crossref_records.json` phải tồn tại **trước phút 30**. Bốn người còn lại đều bị chặn cho tới lúc đó.

### R2 — Đỗ Thu Liễu · Pipeline orchestration owner

`2A202601898` · `@thulieu0503`

| | |
|---|---|
| **Sở hữu** | `src/pipelines/phase1.py`<br>`src/pipelines/corruption_flow.py` |
| **Contract** | **G** (paths & collections) · **H** (repair) — người thực thi, không được vi phạm |
| **Giao** | Hai flow chạy end-to-end, sinh đủ artifact trong `data/` |
| **Xác minh** | `python script/run_phase1.py` rồi `python script/run_corruption_flow.py` |

Không viết logic mới — chỉ gọi hàm của 4 người kia theo đúng thứ tự. Hai rule không được phá:

- `corruption_flow.py` **cấm ghi** vào bất kỳ path baseline nào (`clean_csv`, `embeddings_json`, `baseline_metrics`, `baseline_answers`, `eval_testset`)
- Repair = gọi lại `load_raw_records` + `build_clean_dataframe`, **không** copy file, **không** fetch lại Crossref

### R3 — Trần Chí Vũ · Evaluation owner

`2A202601044` · `@Chivu171`

| | |
|---|---|
| **Sở hữu** | `src/evaluation/testset.py` |
| **Contract** | **C** (eval schema) |
| **Giao** | Test set 20–32 câu, khóa cứng sau CP2, dùng chung cho cả 3 trạng thái |
| **Xác minh** | Mở `test_set.json`: mọi `ground_truth_doc_ids` tồn tại trong `papers_clean.csv` |

Một file, nhưng là **artifact rủi ro cao nhất cả bài**. Câu hỏi phải khớp đúng từ khóa mà `qa.py::_extract_answer` route theo, và phải bọc title trong nháy đơn `'...'` để `qa.py` lookup exact. Sai một trong hai thì baseline thấp bất thường và toàn bộ phép so sánh 3 trạng thái mất ý nghĩa.

Cũng phải chọn **≥ 2 paper mới nhất** vào test set — vì corruption sẽ drop latest records; nếu test set không đụng tới paper mới thì corruption không thể hiện được impact.

### R4 — Trịnh Hải Đăng · Reporting & agent demo owner

`2A202601602` · `@haidang2425`

| | |
|---|---|
| **Sở hữu** | `src/observability/reporting.py`<br>`src/retrieval/demo.py` *(tạo mới)* |
| **Contract** | Đọc **D** (quality) + **F** (metrics), không định nghĩa schema mới |
| **Giao** | `phase1_report.md` · `corruption_report.md` có bảng 3 trạng thái + delta · `agent_demo_answers.json` |
| **Xác minh** | Mọi con số trong 2 report phải khớp `data/results/*_metrics.json` và `data/quality/*.json` |

Cột delta trong comparison report phải **tính bằng code**, không gõ tay. Không sửa `src/retrieval/index.py`, `qa.py`, `agent.py` — chỉ đọc và dùng.

### R5 — Đỗ Văn Linh · Data quality & freshness owner

`2A202601190` · `@DoVanLinh12`

| | |
|---|---|
| **Sở hữu** | `src/observability/quality.py`<br>`script/smoke_retrieval.py` *(tạo mới)* |
| **Contract** | **D** (quality & freshness schema) |
| **Giao** | 6 quality check chạy được trên cả 3 trạng thái · freshness report · smoke test retrieval |
| **Xác minh** | `python script/smoke_retrieval.py` → semantic search + exact lookup trả về document đúng |

Hai hàm phải nhận DataFrame **bất kỳ** (baseline / corrupted / repaired), không đọc file, không hard-code trạng thái. Tên 6 check phải cố định giữa 3 lần chạy thì bảng so sánh mới đối chiếu được.

---

## 2. Ma trận sở hữu file

Mười file cần viết, năm chủ sở hữu, **không file nào có hai người**. Đây là cơ chế chống trùng chéo cấp một: cần đổi một file không thuộc về mình thì **nhắn chủ sở hữu**, không tự sửa.

| File | Chủ sở hữu | Hàm phải viết | Contract |
|---|---|---|---|
| `src/ingestion/crossref.py` | **R1** Bình | `parse_crossref_payload` · `fetch_source_records` · `load_raw_records` | A |
| `src/ingestion/cleaning.py` | **R1** Bình | `build_clean_dataframe` | A → B |
| `src/ingestion/corruption.py` | **R1** Bình | `corrupt_clean_dataframe` | B → B + E |
| `src/pipelines/phase1.py` | **R2** Liễu | `main` | A–D, F, G |
| `src/pipelines/corruption_flow.py` | **R2** Liễu | `main` | C–H |
| `src/evaluation/testset.py` | **R3** Vũ | `build_test_set` | B → C |
| `src/observability/reporting.py` | **R4** Đăng | `generate_phase1_report` · `generate_corruption_report` | D + F |
| `src/retrieval/demo.py` *(mới)* | **R4** Đăng | `run_agent_demo` | G |
| `src/observability/quality.py` | **R5** Linh | `run_data_quality_checks` · `build_freshness_report` | B → D |
| `script/smoke_retrieval.py` *(mới)* | **R5** Linh | — | B |

### Vùng cấm — không ai sửa

| File | Vì sao |
|---|---|
| `src/core/config.py` | Định nghĩa toàn bộ path, collection name, query, ngưỡng freshness. Sửa ở đây là phá Contract G của cả nhóm |
| `src/core/utils.py` | Helper dùng chung — thêm hàm được, đổi hàm cũ thì không |
| `src/retrieval/index.py` · `qa.py` · `llm.py` · `embeddings.py` · `agent.py` | Đã hoàn chỉnh. Chính chúng *ép* ra Contract B và C |
| `src/evaluation/metrics.py` | Đã hoàn chỉnh. Sửa ở đây là tự chấm điểm cho mình |
| `script/run_phase1.py` · `run_corruption_flow.py` | Chỉ là 2 dòng gọi `main()` |
| `pyproject.toml` · `requirements.txt` · `uv.lock` | Đổi dependency giữa chừng làm môi trường 5 máy lệch nhau |

> **Nếu buộc phải sửa vùng cấm:** dừng lại, báo Bình, ghi lý do vào `DATA_CONTRACT.md`, commit riêng với prefix `contract:`. Đây gần như luôn là dấu hiệu bạn hiểu sai contract chứ không phải starter sai.

---

## 3. Bảy quy tắc chống trùng chéo

1. **Contract trước, code sau.** `DATA_CONTRACT.md` phải được merge vào `main` ở CP0, **trước khi bất kỳ ai mở branch implement**. Contract là nguồn duy nhất, không phải tin nhắn nhóm chat.

2. **Một branch một người.** Chỉ chạm file mình sở hữu. Không ai push thẳng lên `main` ngoài Bình.

3. **Chữ ký hàm bị khóa.** Tên hàm, tham số và kiểu trả về đã nằm trong docstring của starter và trong contract. Đổi chữ ký = phá code Liễu đang gọi. Cần đổi thì đi qua quy trình đổi contract.

4. **Merge theo đúng thứ tự phụ thuộc:** Bình → Vũ + Linh (song song) → Đăng → Liễu. Liễu merge cuối vì `pipelines/` gọi tất cả những người kia.

5. **Chỉ Bình commit `data/`.** Thư mục này *không* nằm trong `.gitignore`, nên nếu năm người cùng chạy pipeline rồi cùng commit thì mọi file JSON/CSV sẽ xung đột. Bốn người còn lại chạy `git restore data/` trước khi commit.

6. **Chỉ Liễu chạy entrypoint.** Muốn thử hàm của mình thì gọi trực tiếp trong REPL và `print`, hoặc ghi ra thư mục scratch. Đừng dùng `run_phase1.py` để debug một hàm.

7. **Snapshot raw bị đóng băng sau CP1.** Crossref là nguồn sống. Fetch lại giữa chừng làm baseline và repaired dựa trên hai tập dữ liệu khác nhau, và bảng so sánh mất giá trị.

### Branch của từng người

| Thành viên | GitHub | Branch | Thứ tự merge |
|---|---|---|---:|
| Nguyễn Thanh Bình — R1 | `@NguyenThanhBinh108` | `r1-ingestion-data` | 1 |
| Trần Chí Vũ — R3 | `@Chivu171` | `r3-evaluation` | 2 |
| Đỗ Văn Linh — R5 | `@DoVanLinh12` | `r5-quality` | 2 |
| Trịnh Hải Đăng — R4 | `@haidang2425` | `r4-reporting-demo` | 3 |
| Đỗ Thu Liễu — R2 | `@thulieu0503` | `r2-pipelines` | 4 |

> **Quyền trên repo:** repo đang đứng tên `@NguyenThanhBinh108`. Thêm bốn người còn lại làm collaborator **ngay ở CP0** — nếu để đến CP3 mới thêm thì cả nhóm phải gửi patch tay đúng lúc gấp nhất.

### Sửa `.gitignore` ngay ở CP0

ChromaDB ghi ra một file SQLite nhị phân. Git không merge được nhị phân, mà nó lại tái tạo được hoàn toàn từ pipeline, nên đừng đưa nó vào lịch sử.

```gitignore
# thêm vào cuối .gitignore
data/chroma/*
!data/chroma/.gitkeep
```

> **Giữ lại phần còn lại của `data/`.** Các artifact JSON/CSV/Markdown **phải** được commit — rubric trừ điểm khi thiếu file quan trọng, và báo cáo phải trỏ tới artifact thật. Chỉ loại trừ vector store nhị phân.

---

## 4. Timeline 4 giờ

Bảy checkpoint theo đúng file phân công gốc. Mỗi mốc có một cổng nghiệm thu — **không qua cổng thì không sang mốc sau**, vì mọi mốc phía sau đều đứng trên artifact của mốc trước.

### CP0 · 00:00–00:30 (30 phút) — Khởi động, chốt contract, ingestion raw

| | |
|---|---|
| **R1** Bình | Chốt + merge `DATA_CONTRACT.md`, sửa `.gitignore`, add collaborator, tạo 5 branch. Rồi viết cả 3 hàm `crossref.py`, fetch thật, ghi 2 file raw |
| **R2** Liễu | Tạo venv 3.13 + `pip install -e .`, đọc `config.py` nắm toàn bộ `settings.paths`, vẽ sơ đồ 10 bước của `phase1.py` |
| **R3** Vũ | Đọc `metrics.py` + `qa.py`; chốt 4 template câu hỏi khớp từ khóa của `_extract_answer` |
| **R4** Đăng | Đọc `index.py`, `agent.py`; chốt khung 2 report và câu hỏi dùng cho agent demo |
| **R5** Linh | Đọc Contract D; chốt tên và ngưỡng của 6 quality check |

**✓ Cổng:** hai file trong `data/raw/` tồn tại · `paper_id` ổn định · contract đã merge · mỗi người biết rõ artifact mình bàn giao

### CP1 · 00:30–01:05 (35 phút) — Cleaning, data model & quality gate đầu tiên

| | |
|---|---|
| **R1** Bình | Hoàn thiện `cleaning.py`: normalize, parse date, dedupe, `age_days`, `text_for_embedding`, log count từng rule. Ép dtype trước khi return |
| **R5** Linh | Hoàn thiện `run_data_quality_checks` + `build_freshness_report`, test trên clean data của Bình |
| **R3** Vũ | Chọn paper đại diện từ cleaned dataframe, viết draft question/ground truth kiểm chứng được |
| **R4** Đăng | Đọc vài `text_for_embedding` thật; dựng khung `generate_phase1_report` |
| **R2** Liễu | Ghép `phase1.py` bước 1–4; rà soát raw count → clean count, ghi bất thường thành blocker |

**✓ Cổng:** clean CSV/JSON đọc được · `paper_id` unique · có `text_for_embedding` và `age_days` · truy vết được lý do từng record bị loại

### CP2 · 01:05–01:35 (30 phút) — Test set, index & smoke test

| | |
|---|---|
| **R3** Vũ | Sinh test set 20–32 câu rồi **khóa file**; kiểm mọi `ground_truth_doc_ids` có trong index |
| **R5** Linh | Viết `smoke_retrieval.py`, build thử collection, chạy 1 semantic search + 1 exact lookup |
| **R4** Đăng | Viết `run_agent_demo`, bọc `try/except` để không có API key vẫn không làm hỏng pipeline |
| **R1** Bình | Xác nhận không còn `text_for_embedding` rỗng; truy một `paper_id` xuyên suốt raw → clean → metadata index |
| **R2** Liễu | Ghép `phase1.py` bước 5–6, build `papers-baseline` từ clean data |

**✓ Cổng:** `test_set.json` + embedding manifest + collection baseline tồn tại · semantic search, exact lookup và agent đều trả kết quả có nguồn

### CP3 · 01:35–02:00 (25 phút) — Baseline chạy end-to-end

| | |
|---|---|
| **R2** Liễu | Hoàn thiện `phase1.py` đủ 10 bước, chạy `run_phase1.py` tới khi sạch traceback |
| **R4** Đăng | Hoàn thiện `generate_phase1_report`, đối chiếu từng số với JSON thật |
| **R3** Vũ | Đọc một hit và một miss trong `baseline_answers.json`, giải thích được vì sao |
| **R5** Linh | Ghi lại baseline quality/freshness signals làm mốc so sánh sau giờ nghỉ |
| **R1** Bình | Kiểm `age_days` và `text_for_embedding` trong artifact đã ghi; **commit toàn bộ `data/`** |

**✓ Cổng:** `baseline_metrics.json`, answers, quality/freshness và `phase1_report.md` **khớp nhau** — không phải chỉ script exit code 0

### CP4 · 02:00–02:15 (15 phút) — Nghỉ

| | |
|---|---|
| **R1** Bình | Chốt 6 kịch bản corruption sẽ chạy, rồi nghỉ thật |
| **R2** Liễu | Ghi checklist baseline và một blocker còn tồn |

**✓ Cổng:** nghỉ đủ 15 phút — thời gian này đã nằm trong tổng 4 giờ

### CP5 · 02:15–03:15 (60 phút) — Corruption có kiểm soát & đo impact

| | |
|---|---|
| **R1** Bình | Viết `corrupt_clean_dataframe` 6 kịch bản, **rebuild `text_for_embedding`**, `df.copy()` để không mutate baseline, ghi corruption log đủ id/type/param/before-after |
| **R2** Liễu | Ghép `corruption_flow.py`: corrupt → index riêng → evaluate → quality/freshness. Kiểm không path baseline nào bị ghi đè |
| **R5** Linh | Chạy quality/freshness trên corrupted, lưu report riêng, nối corruption log với signal thay đổi |
| **R3** Vũ | Evaluate corrupted trên **test set cũ**; tìm một case xấu đi có bằng chứng; kiểm judge không âm thầm fallback |
| **R4** Đăng | Xác nhận `papers-baseline` chưa bị mutate; ghi lại delta đầu tiên vào khung comparison report |

**✓ Cổng:** corruption log + corrupted clean/index/answers/metrics/quality đầy đủ · baseline **không** bị ghi đè

### CP6 · 03:15–04:00 (45 phút) — Repair từ raw, so sánh, review & demo

| | |
|---|---|
| **R2** Liễu | Ghép nhánh repair (`load_raw_records` → `build_clean_dataframe`), chạy full corruption flow |
| **R4** Đăng | Hoàn thiện `generate_corruption_report`: bảng 3 trạng thái + cột delta **tính bằng code** |
| **R3** Vũ | Tính delta 4 metric, giải thích metric nào hồi phục và metric nào chưa, kèm giả thuyết |
| **R5** Linh | Quality/freshness trên repaired; nêu rõ nếu recovery chưa hoàn toàn |
| **R1** Bình | Chứng minh record bị drop/corrupt đã phục hồi bằng lineage · checklist cuối: đủ artifact, report khớp output, không secret · merge tất cả vào `main` |

**✓ Cổng:** repaired artifacts + comparison report có đủ baseline–corrupted–repaired và delta · repo sạch secret · demo dùng artifact thật

---

## 5. Hai file mới

Để Đăng và Linh có deliverable code thật mà không đụng vào `src/retrieval/` đã hoàn chỉnh, và để Liễu chỉ gọi một dòng trong `phase1.py` thay vì tự viết phần demo agent.

```python
# src/retrieval/demo.py — Đăng sở hữu, Liễu gọi 1 dòng từ phase1.py
def run_agent_demo(settings, index, questions: list[str]) -> list[dict]:
    """Chạy agent trên vài câu hỏi, ghi settings.paths.demo_answers.
    Bọc try/except: không có API key thì trả [] chứ không làm hỏng pipeline."""

# script/smoke_retrieval.py — Linh sở hữu, chạy độc lập, KHÔNG ghi vào data/
# đọc clean CSV -> build index tạm -> 1 semantic search + 1 exact lookup -> print
```

> **Vì sao tách file:** `settings.paths.demo_answers` đã có sẵn trong `config.py` — starter thiết kế để có bước demo này. Tách ra file riêng nghĩa là Liễu và Đăng không bao giờ sửa cùng một dòng.

---

## 6. Báo cáo

Nộp một `group_report.md` chung, cộng với **mỗi người một bản riêng** đặt tên `<MSSV>_HoTen.md`. Bản cá nhân **không được** là bản sao của báo cáo nhóm.

| Mục trong `group_report.md` | Người viết |
|---|---|
| §5 Nguồn dữ liệu, raw/clean schema, quy tắc cleaning · §9 Corruption scenarios & repair | **R1** Bình |
| §1 Thông tin nhóm · §3 Kiến trúc luồng dữ liệu · §4 Cách tái hiện · §11 Vấn đề tích hợp · §13 Checklist | **R2** Liễu |
| §6 Evaluation setup · §7 Baseline metrics | **R3** Vũ |
| §10 Bảng so sánh 3 trạng thái · §12 Giới hạn | **R4** Đăng |
| §8 Data quality và freshness | **R5** Linh |
| §2 Tóm tắt | **R2** Liễu tổng hợp, cả nhóm duyệt |

File báo cáo cá nhân cần nộp:

| Thành viên | Tên file |
|---|---|
| Nguyễn Thanh Bình | `report/2A202601274_NguyenThanhBinh.md` |
| Đỗ Thu Liễu | `report/2A202601898_DoThuLieu.md` |
| Trần Chí Vũ | `report/2A202601044_TranChiVu.md` |
| Trịnh Hải Đăng | `report/2A202601602_TrinhHaiDang.md` |
| Đỗ Văn Linh | `report/2A202601190_DoVanLinh.md` |

> **Điều bị trừ điểm nặng nhất: báo cáo không khớp artifact thật.** Mọi con số trong Markdown phải copy từ ba file `data/results/*_metrics.json`. Nếu repair chưa hồi phục hoàn toàn thì **ghi đúng như vậy** kèm giả thuyết — trung thực ăn điểm cao hơn một bảng đẹp nhưng bịa.

---

## 7. Definition of Done của cả nhóm

- [ ] `DATA_CONTRACT.md` đã được cả 5 người ký ở CP0 và merge vào `main`
- [ ] 4 thành viên đã là collaborator của repo
- [ ] `.gitignore` đã loại trừ `data/chroma/*`
- [ ] 10 file implement đã merge đúng thứ tự phụ thuộc, không ai sửa file của người khác
- [ ] `python script/run_phase1.py` chạy end-to-end
- [ ] `python script/run_corruption_flow.py` chạy sau baseline, không ghi đè baseline
- [ ] Baseline / corrupted / repaired dùng **cùng một** `data/eval/test_set.json`
- [ ] Bảng metrics trong report khớp `data/results/*_metrics.json`
- [ ] Không có `.env`, API key hay token trong source, report, log hay ảnh
- [ ] Mỗi thành viên nộp `<MSSV>_HoTen.md` riêng và giải thích được luồng end-to-end
