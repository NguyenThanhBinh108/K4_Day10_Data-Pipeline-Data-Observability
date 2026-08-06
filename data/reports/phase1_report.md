# Báo cáo Pha 1 — Baseline trên dữ liệu sạch

_Sinh tự động lúc 2026-08-06T10:25:20.154547+00:00 từ artifact thật trong `data/`._

## 1. Nguồn dữ liệu và cấu hình

| Thuộc tính | Giá trị |
| --- | --- |
| Nguồn | `Crossref REST API` |
| Query | `agentic retrieval augmented generation large language model` |
| Filter | `from-pub-date:2026-02-07,has-abstract:true` |
| Thời điểm lấy dữ liệu | `2026-08-06T08:36:03.911604+00:00` |
| Số raw record | `23` |
| Số dòng sau cleaning | `23` |
| Số record bị loại khi cleaning | `0` |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector collection | `papers-baseline` |
| Retrieval top_k | `4` |
| LLM provider | `gemini` |
| LLM model | `gemini-2.5-flash` |
| source_mode | `reused snapshot` |
| judge_mode | `heuristic fallback (LLM judge khong dung duoc)` |

## 2. Kết quả đánh giá

| Metric | Giá trị | Ý nghĩa |
| --- | ---: | --- |
| `retrieval_hit_rate` | 1 | Tỉ lệ câu hỏi truy hồi trúng ít nhất một ground-truth document |
| `mean_token_f1` | 1 | Trung bình token-F1 giữa câu trả lời và ground truth |
| `judge_accuracy` | 1 | Tỉ lệ câu được LLM judge chấm là đúng về bản chất |
| `mean_judge_score` | 5 | Điểm trung bình của judge, thang 1-5 |
| `samples` | 23 | Số câu hỏi trong test set |
| `ragas` | — | Bỏ qua — đặt `RUN_RAGAS=1` để bật |

## 3. Data quality checks

**Tổng kết:** 6/6 pass — trạng thái chung `PASS` trên 23 dòng.

| Check | Dimension | Kỳ vọng | Quan sát | Kết quả |
| --- | --- | --- | ---: | --- |
| `row_count_min` | Completeness | `>= 10` | 23 | PASS |
| `paper_id_not_null` | Completeness | `== 0` | 0 | PASS |
| `paper_id_unique` | Uniqueness | `== 0` | 0 | PASS |
| `title_not_empty` | Completeness | `== 0` | 0 | PASS |
| `summary_min_length` | Validity | `== 0` | 0 | PASS |
| `freshness_age_days` | Timeliness | `== 0` | 0 | PASS |

## 4. Freshness

| Thuộc tính | Giá trị |
| --- | --- |
| Ngưỡng freshness | `180 ngày` |
| Published mới nhất | `2026-08-01` |
| Published cũ nhất | `2026-02-12` |
| age_days lớn nhất | `175` |
| Số dòng quá hạn | `0` |
| Tổng số dòng | `23` |
| Trạng thái | `Fresh` |

## 5. Trạng thái

- Data quality: `PASS`
- Freshness: `Fresh (stale_rows=0)`
- Baseline này là mốc so sánh cho corrupted và repaired. Cả ba trạng thái phải đánh giá trên cùng `data/eval/test_set.json`.

