# Báo cáo so sánh — Baseline / Corrupted / Repaired

_Sinh tự động lúc 2026-08-06T10:04:53.392330+00:00 từ `data/results/*_metrics.json`, `data/quality/*.json` và `data/results/corruption_log.json`._

Cả ba trạng thái được đánh giá trên **cùng một** `data/eval/test_set.json`, cùng embedding model và cùng `top_k`. Nếu không, các cột dưới đây không so sánh được.

## 1. Bảng so sánh metrics

| Metric | Baseline | Corrupted | Repaired | Δ corruption | Mức phục hồi |
| --- | ---: | ---: | ---: | ---: | ---: |
| `retrieval_hit_rate` | 1 | 0.8261 | 1 | -0.1739 | 100% |
| `mean_token_f1` | 1 | 0.6584 | 1 | -0.3416 | 100% |
| `judge_accuracy` | 1 | 0.6522 | 1 | -0.3478 | 100% |
| `mean_judge_score` | 5 | 3.61 | 5 | -1.39 | 100% |

## 2. Data quality checks

| Check | Baseline | Corrupted | Repaired |
| --- | --- | --- | --- |
| `row_count_min` | PASS (`23`) | PASS (`23`) | PASS (`23`) |
| `paper_id_not_null` | PASS (`0`) | PASS (`0`) | PASS (`0`) |
| `paper_id_unique` | PASS (`0`) | FAIL (`3`) | PASS (`0`) |
| `title_not_empty` | PASS (`0`) | PASS (`0`) | PASS (`0`) |
| `summary_min_length` | PASS (`0`) | FAIL (`5`) | PASS (`0`) |
| `freshness_age_days` | PASS (`0`) | FAIL (`6`) | PASS (`0`) |

- Baseline: 6/6 pass, tổng `PASS`
- Corrupted: 3/6 pass, tổng `FAIL`
- Repaired: 6/6 pass, tổng `PASS`

## 3. Freshness

| Thuộc tính | Baseline | Corrupted | Repaired |
| --- | --- | --- | --- |
| Trạng thái | Fresh (stale_rows=0) | Stale (stale_rows=6) | Fresh (stale_rows=0) |
| `max_age_days` | `175` | `975` | `175` |
| `latest_published` | `2026-08-01` | `2026-07-03` | `2026-08-01` |
| `oldest_published` | `2026-02-12` | `2023-12-05` | `2026-02-12` |

## 4. Kết luận rút ra từ số liệu

1. Corruption làm 3 quality check chuyển sang FAIL (`paper_id_unique`, `summary_min_length`, `freshness_age_days`), và freshness lật sang `is_fresh=false` (`max_age_days` = `975`).
2. Chất lượng agent giảm ở 4 metric. Giảm mạnh nhất là `mean_judge_score`: 5 → 3.6087 (-1.3913).
3. Repair chạy lại cleaning từ `data/raw/crossref_records.json` và khôi phục 4/4 metric về đúng mức baseline (`retrieval_hit_rate`, `mean_token_f1`, `judge_accuracy`, `mean_judge_score`).

## 5. Giới hạn của kết luận

- Các quality check **vẫn đạt** sau corruption: `row_count_min`, `paper_id_not_null`, `title_not_empty`. Nghĩa là quality check không bắt được mọi dạng lỗi dữ liệu — ví dụ nhiễu trong summary và title bị cắt chỉ lộ ra qua metric của agent.
- Crossref là nguồn sống nên số liệu giữa các nhóm sẽ khác nhau. Chỉ so sánh trong cùng bài làm, trên cùng snapshot raw và cùng test set.

