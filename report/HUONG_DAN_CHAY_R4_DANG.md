# Hướng dẫn chạy phần R4 (Trịnh Hải Đăng) — Reporting & agent demo

File này chỉ hướng dẫn xác minh phần việc của R4: `src/observability/reporting.py`
(`generate_phase1_report`, `generate_corruption_report`) và `src/retrieval/demo.py`
(`run_agent_demo`, file mới). Xem `report/README.md` và `PHAN_CONG.md` để biết bức
tranh toàn nhóm.

## 1. Chuẩn bị môi trường

Project quản lý dependency bằng `uv` (khai báo trong `pyproject.toml`/`uv.lock`).
Không dùng `python`/`pip` hệ thống trực tiếp — sẽ thiếu `datasets`, `langchain`,
`chromadb`... vì các gói này chỉ nằm trong venv do `uv` tạo.

```bash
# cài uv nếu máy chưa có (Windows PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# tại thư mục gốc repo
uv sync
```

Không sửa `pyproject.toml`, `requirements.txt`, `uv.lock` — đây là vùng cấm chung
của nhóm (xem `PHAN_CONG.md` mục "Vùng cấm").

## 2. (Tuỳ chọn) Cấu hình API key cho agent demo

`run_agent_demo` **không bắt buộc** phải có key mới chạy được pipeline — nếu thiếu
key, hàm tự ghi `data/results/agent_demo_answers.json` với khoá `"skipped"` và trả
về danh sách rỗng, không làm hỏng `phase1.py`. Muốn thấy agent demo trả lời thật:

```bash
# tạo file .env ở gốc repo (không commit file này)
echo LLM_PROVIDER=openrouter >> .env
echo OPENROUTER_API_KEY=<khoa-cua-ban> >> .env
```

Xem `src/core/config.py` để biết các biến `LLM_PROVIDER`/`*_API_KEY` khác được hỗ trợ
(OpenAI, Gemini...). Tuyệt đối không commit `.env` hay dán key vào report/log.

## 3. Chạy pipeline để sinh artifact mà reporting.py/demo.py phụ thuộc

Phần R4 chỉ **đọc** artifact do các phần khác tạo ra rồi in ra Markdown/JSON — nên
phải chạy đủ hai flow theo đúng thứ tự để có input:

```bash
uv run python script/run_phase1.py
uv run python script/run_corruption_flow.py
```

`run_phase1.py` gọi `generate_phase1_report` và `run_agent_demo` ở bước cuối.
`run_corruption_flow.py` gọi `generate_corruption_report` ở bước cuối.

## 4. Kiểm tra output của riêng phần R4

| Artifact | Sinh bởi | Cách kiểm tra nhanh |
| --- | --- | --- |
| `data/reports/phase1_report.md` | `generate_phase1_report` | Mở file, đối chiếu bảng metric với `data/results/baseline_metrics.json` và bảng quality với `data/quality/baseline_quality.json` |
| `data/reports/corruption_report.md` | `generate_corruption_report` | Đối chiếu cột Baseline/Corrupted/Repaired với 3 file `data/results/{baseline,corrupted,repaired}_metrics.json`; cột "Δ corruption" phải bằng Corrupted − Baseline |
| `data/results/agent_demo_answers.json` | `run_agent_demo` | Không có `.env`: JSON có khoá `"skipped"` + `"answers": []`. Có `.env` hợp lệ: JSON có `"answers"` với từng câu kèm `"tools_used"` (tên tool agent đã gọi, ví dụ `semantic_search_papers`) |

Lệnh xem nhanh nội dung (PowerShell):

```powershell
Get-Content data\reports\phase1_report.md
Get-Content data\reports\corruption_report.md
Get-Content data\results\agent_demo_answers.json
```

## 5. Chạy lại chỉ để thử reporting.py mà không đụng data/ (debug)

Theo quy tắc chung của nhóm, chỉ Bình (R1) được commit `data/`. Nếu chỉ muốn thử
nhanh một hàm trong `reporting.py` mà không chạy lại toàn bộ pipeline, gọi trực
tiếp trong REPL thay vì dùng `run_phase1.py`/`run_corruption_flow.py`:

```bash
uv run python
```

```python
import sys; sys.path.insert(0, "src")
from core.utils import read_json
from observability.reporting import generate_phase1_report

metrics = read_json("data/results/baseline_metrics.json")
quality = read_json("data/quality/baseline_quality.json")
freshness = read_json("data/quality/freshness_report.json")
generate_phase1_report(
    "data/reports/phase1_report.md",
    source_summary={"source": "crossref"},
    metrics=metrics,
    quality=quality,
    freshness=freshness,
)
```

## 6. Sau khi xác minh xong

Nếu bạn không phải R1 (Bình), phục hồi lại `data/` trước khi commit để tránh xung
đột với ai khác cũng đang chạy pipeline:

```bash
git restore data/
```

Chỉ giữ lại thay đổi trong `src/observability/reporting.py`, `src/retrieval/demo.py`,
`report/group_report.md` (mục 10 và 12), và file report cá nhân
`report/2A202601602_TrinhHaiDang.md`.

## 7. Definition of Done cho phần R4

- [ ] `data/reports/phase1_report.md` sinh ra không lỗi, mọi số khớp `data/results/baseline_metrics.json` và `data/quality/baseline_quality.json`
- [ ] `data/reports/corruption_report.md` có đủ cột Δ và mức phục hồi, khớp 3 file `*_metrics.json`
- [ ] `data/results/agent_demo_answers.json` tồn tại (dù skip hay chạy thật), không làm pipeline dừng giữa chừng
- [ ] `src/retrieval/index.py`, `qa.py`, `llm.py`, `agent.py` không bị sửa
- [ ] Không có API key hay `.env` trong commit
