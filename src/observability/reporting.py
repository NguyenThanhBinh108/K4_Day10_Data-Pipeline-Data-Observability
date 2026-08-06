"""Markdown reporting — Contract D (quality) + Contract F (metrics) la input.

Owner: R4 (Trinh Hai Dang).

Hai bao cao deu **chi doc so tu artifact that** va tinh delta bang code. Khong hardcode
so lieu, khong lam tron de nhin dep hon. Neu mot trang thai chua chay thi in ro la chua
co du lieu chu khong doan.

Nguyen tac quan trong nhat cua `generate_corruption_report`: **khong ket luan qua muc**.
Bao cao tu liet ke ca cac tin hieu KHONG doi giua baseline va corrupted, de nguoi doc
biet corruption anh huong toi dau chu khong tuong moi thu deu bi anh huong.
"""

from __future__ import annotations

from typing import Any

from core.utils import now_utc, write_text

# Cac metric so hoc trong Contract F. "ragas" bi bo qua vi la dict long nhau.
METRIC_KEYS = [
    ("retrieval_hit_rate", "Tỉ lệ câu hỏi truy hồi trúng ít nhất một ground-truth document"),
    ("mean_token_f1", "Trung bình token-F1 giữa câu trả lời và ground truth"),
    ("judge_accuracy", "Tỉ lệ câu được LLM judge chấm là đúng về bản chất"),
    ("mean_judge_score", "Điểm trung bình của judge, thang 1-5"),
]

MISSING = "—"


def _num(value: Any, digits: int = 4) -> str:
    """Format so; tra ve dau gach neu khong phai so (chua chay, hoac loi)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return MISSING
    return f"{value:.{digits}f}".rstrip("0").rstrip(".") if digits else str(value)


def _delta(after: Any, before: Any, digits: int = 4) -> str:
    """Chenh lech co dau. Dung cho cot 'thay doi do corruption'."""
    if not isinstance(after, (int, float)) or not isinstance(before, (int, float)):
        return MISSING
    if isinstance(after, bool) or isinstance(before, bool):
        return MISSING
    diff = after - before
    return f"{diff:+.{digits}f}".rstrip("0").rstrip(".") if diff else "0"


def _recovery(baseline: Any, corrupted: Any, repaired: Any) -> str:
    """Muc phuc hoi: repaired da lay lai bao nhieu phan cua khoang bi mat.

    100% = ve dung baseline. 0% = khong phuc hoi gi. Am = con te hon corrupted.
    Tra dau gach khi corruption khong lam metric thay doi (khong co gi de phuc hoi).
    """
    values = (baseline, corrupted, repaired)
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in values):
        return MISSING
    lost = baseline - corrupted
    if abs(lost) < 1e-12:
        return "n/a"
    return f"{(repaired - corrupted) / lost * 100:.0f}%"


def _flag(value: Any) -> str:
    if value is True:
        return "PASS"
    if value is False:
        return "FAIL"
    return MISSING


def _quality_summary(quality: dict[str, Any]) -> str:
    if not quality:
        return MISSING
    passed, failed = quality.get("success_count"), quality.get("failed_count")
    if passed is None or failed is None:
        return MISSING
    return f"{passed}/{passed + failed} pass"


def _fresh_summary(freshness: dict[str, Any]) -> str:
    if not freshness:
        return MISSING
    if "is_fresh" not in freshness:
        return MISSING
    state = "Fresh" if freshness["is_fresh"] else "Stale"
    return f"{state} (stale_rows={freshness.get('stale_rows', MISSING)})"


def _source_table(source_summary: dict[str, Any]) -> list[str]:
    """Render source_summary. Cac khoa duoi day do phase1.py truyen vao.

    Khoa nao thieu se hien dau gach thay vi lam vo bao cao, nen phase1 co the bo sung
    dan ma khong phai sua file nay.
    """
    labels = [
        ("source", "Nguồn"),
        ("query", "Query"),
        ("filter", "Filter"),
        ("fetched_at", "Thời điểm lấy dữ liệu"),
        ("raw_records", "Số raw record"),
        ("clean_rows", "Số dòng sau cleaning"),
        ("dropped", "Số record bị loại khi cleaning"),
        ("embedding_model", "Embedding model"),
        ("collection", "Vector collection"),
        ("top_k", "Retrieval top_k"),
        ("llm_provider", "LLM provider"),
        ("llm_model", "LLM model"),
    ]
    lines = ["| Thuộc tính | Giá trị |", "| --- | --- |"]
    for key, label in labels:
        if key in source_summary:
            lines.append(f"| {label} | `{source_summary[key]}` |")
    # Khoa la do phase1 tu them: van in ra thay vi bo di am tham.
    known = {key for key, _ in labels}
    for key, value in source_summary.items():
        if key not in known:
            lines.append(f"| {key} | `{value}` |")
    return lines


def _metrics_table(metrics: dict[str, Any]) -> list[str]:
    lines = ["| Metric | Giá trị | Ý nghĩa |", "| --- | ---: | --- |"]
    for key, meaning in METRIC_KEYS:
        digits = 2 if key == "mean_judge_score" else 4
        lines.append(f"| `{key}` | {_num(metrics.get(key), digits)} | {meaning} |")
    lines.append(f"| `samples` | {metrics.get('samples', MISSING)} | Số câu hỏi trong test set |")

    ragas = metrics.get("ragas")
    if isinstance(ragas, dict) and "skipped" in ragas:
        lines.append(f"| `ragas` | {MISSING} | Bỏ qua — đặt `RUN_RAGAS=1` để bật |")
    elif isinstance(ragas, dict) and "error" in ragas:
        lines.append(f"| `ragas` | {MISSING} | Lỗi: {ragas['error']} |")
    elif isinstance(ragas, dict) and ragas:
        for key, value in ragas.items():
            lines.append(f"| `ragas.{key}` | {_num(value)} | |")
    return lines


def _checks_table(quality: dict[str, Any]) -> list[str]:
    checks = quality.get("checks") or []
    if not checks:
        return ["_Chưa có quality check nào._"]
    lines = [
        "| Check | Dimension | Kỳ vọng | Quan sát | Kết quả |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for check in checks:
        lines.append(
            f"| `{check.get('name', MISSING)}` | {check.get('dimension', MISSING)} "
            f"| `{check.get('expected', MISSING)}` | {check.get('observed', MISSING)} "
            f"| {_flag(check.get('success'))} |"
        )
    return lines


def _freshness_table(freshness: dict[str, Any]) -> list[str]:
    if not freshness:
        return ["_Chưa có freshness report._"]
    rows = [
        ("Ngưỡng freshness", f"{freshness.get('threshold_days', MISSING)} ngày"),
        ("Published mới nhất", freshness.get("latest_published", MISSING)),
        ("Published cũ nhất", freshness.get("oldest_published", MISSING)),
        ("age_days lớn nhất", freshness.get("max_age_days", MISSING)),
        ("Số dòng quá hạn", freshness.get("stale_rows", MISSING)),
        ("Tổng số dòng", freshness.get("total_rows", MISSING)),
        ("Trạng thái", "Fresh" if freshness.get("is_fresh") else "Stale"),
    ]
    return ["| Thuộc tính | Giá trị |", "| --- | --- |"] + [f"| {k} | `{v}` |" for k, v in rows]


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Bao cao baseline: nguon du lieu, metrics, quality checks va freshness."""
    failed = [c for c in (quality.get("checks") or []) if not c.get("success")]

    lines = [
        "# Báo cáo Pha 1 — Baseline trên dữ liệu sạch",
        "",
        f"_Sinh tự động lúc {now_utc().isoformat()} từ artifact thật trong `data/`._",
        "",
        "## 1. Nguồn dữ liệu và cấu hình",
        "",
        *_source_table(source_summary),
        "",
        "## 2. Kết quả đánh giá",
        "",
        *_metrics_table(metrics),
        "",
        "## 3. Data quality checks",
        "",
        f"**Tổng kết:** {_quality_summary(quality)} — "
        f"trạng thái chung `{_flag(quality.get('success'))}` trên {quality.get('total_rows', MISSING)} dòng.",
        "",
        *_checks_table(quality),
        "",
    ]

    if failed:
        lines += [
            "> **Cảnh báo:** baseline đã có check không đạt: "
            + ", ".join(f"`{c['name']}` (quan sát `{c['observed']}`)" for c in failed)
            + ". Phải xử lý trước khi chạy corruption flow, nếu không sẽ không phân biệt được "
            "lỗi do corruption với lỗi có sẵn từ đầu.",
            "",
        ]

    lines += [
        "## 4. Freshness",
        "",
        *_freshness_table(freshness),
        "",
        "## 5. Trạng thái",
        "",
        f"- Data quality: `{_flag(quality.get('success'))}`",
        f"- Freshness: `{_fresh_summary(freshness)}`",
        "- Baseline này là mốc so sánh cho corrupted và repaired. "
        "Cả ba trạng thái phải đánh giá trên cùng `data/eval/test_set.json`.",
        "",
    ]
    write_text(report_path, "\n".join(lines) + "\n")


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Bao cao so sanh baseline / corrupted / repaired.

    Cot delta va muc phuc hoi deu tinh bang code tu ba file metrics that.
    """
    baseline_metrics = baseline_metrics or {}
    corrupted_metrics = corrupted_metrics or {}
    repaired_metrics = repaired_metrics or {}

    lines = [
        "# Báo cáo so sánh — Baseline / Corrupted / Repaired",
        "",
        f"_Sinh tự động lúc {now_utc().isoformat()} từ `data/results/*_metrics.json`, "
        "`data/quality/*.json` và `data/results/corruption_log.json`._",
        "",
        "Cả ba trạng thái được đánh giá trên **cùng một** `data/eval/test_set.json`, "
        "cùng embedding model và cùng `top_k`. Nếu không, các cột dưới đây không so sánh được.",
        "",
        "## 1. Bảng so sánh metrics",
        "",
        "| Metric | Baseline | Corrupted | Repaired | Δ corruption | Mức phục hồi |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    unchanged: list[str] = []
    degraded: list[tuple[str, Any, Any]] = []

    for key, _ in METRIC_KEYS:
        digits = 2 if key == "mean_judge_score" else 4
        base, corr, rep = (m.get(key) for m in (baseline_metrics, corrupted_metrics, repaired_metrics))
        lines.append(
            f"| `{key}` | {_num(base, digits)} | {_num(corr, digits)} | {_num(rep, digits)} "
            f"| {_delta(corr, base, digits)} | {_recovery(base, corr, rep)} |"
        )
        if isinstance(base, (int, float)) and isinstance(corr, (int, float)):
            if abs(base - corr) < 1e-12:
                unchanged.append(key)
            elif corr < base:
                degraded.append((key, base, corr))

    lines += [
        "",
        "## 2. Data quality checks",
        "",
        "| Check | Baseline | Corrupted | Repaired |",
        "| --- | --- | --- | --- |",
    ]

    # Baseline quality khong nam trong tham so cua ham nay theo contract, nen cot baseline
    # duoc suy tu chinh corrupted/repaired: mot check chi co the "hong" neu truoc do dat.
    corrupted_checks = {c["name"]: c for c in (corrupted_quality.get("checks") or [])}
    repaired_checks = {c["name"]: c for c in (repaired_quality.get("checks") or [])}
    flipped: list[str] = []

    for name in list(corrupted_checks) or list(repaired_checks):
        corr_check = corrupted_checks.get(name, {})
        rep_check = repaired_checks.get(name, {})
        corr_cell = f"{_flag(corr_check.get('success'))} (`{corr_check.get('observed', MISSING)}`)"
        rep_cell = f"{_flag(rep_check.get('success'))} (`{rep_check.get('observed', MISSING)}`)"
        lines.append(f"| `{name}` | xem `phase1_report.md` | {corr_cell} | {rep_cell} |")
        if corr_check.get("success") is False:
            flipped.append(name)

    lines += [
        "",
        f"- Corrupted: {_quality_summary(corrupted_quality)}, tổng `{_flag(corrupted_quality.get('success'))}`",
        f"- Repaired: {_quality_summary(repaired_quality)}, tổng `{_flag(repaired_quality.get('success'))}`",
        "",
        "## 3. Freshness",
        "",
        "| Thuộc tính | Corrupted | Repaired |",
        "| --- | --- | --- |",
        f"| Trạng thái | {_fresh_summary(corrupted_freshness)} | {_fresh_summary(repaired_freshness)} |",
        f"| `max_age_days` | `{corrupted_freshness.get('max_age_days', MISSING)}` "
        f"| `{repaired_freshness.get('max_age_days', MISSING)}` |",
        f"| `latest_published` | `{corrupted_freshness.get('latest_published', MISSING)}` "
        f"| `{repaired_freshness.get('latest_published', MISSING)}` |",
        f"| `oldest_published` | `{corrupted_freshness.get('oldest_published', MISSING)}` "
        f"| `{repaired_freshness.get('oldest_published', MISSING)}` |",
        "",
        "## 4. Kết luận rút ra từ số liệu",
        "",
    ]

    if flipped:
        lines.append(
            f"1. Corruption làm {len(flipped)} quality check chuyển sang FAIL "
            f"({', '.join(f'`{n}`' for n in flipped)}), "
            + (
                f"và freshness lật sang `is_fresh=false` (`max_age_days` = "
                f"`{corrupted_freshness.get('max_age_days', MISSING)}`)."
                if corrupted_freshness.get("is_fresh") is False
                else "trong khi freshness không đổi."
            )
        )
    else:
        lines.append("1. Không quality check nào chuyển sang FAIL sau corruption.")

    if degraded:
        worst = min(degraded, key=lambda item: item[2] - item[1])
        lines.append(
            f"2. Chất lượng agent giảm ở {len(degraded)} metric. Giảm mạnh nhất là "
            f"`{worst[0]}`: {_num(worst[1])} → {_num(worst[2])} ({_delta(worst[2], worst[1])})."
        )
    else:
        lines.append(
            "2. **Không metric nào của agent giảm sau corruption.** Không được kết luận corruption "
            "có tác động lên chất lượng trả lời. Cần kiểm tra: corruption có chạm vào các paper nằm "
            "trong test set không, và `text_for_embedding` đã được build lại sau khi làm hỏng dữ liệu chưa."
        )

    if repaired_metrics:
        recovered = [
            key
            for key, _ in METRIC_KEYS
            if isinstance(baseline_metrics.get(key), (int, float))
            and isinstance(repaired_metrics.get(key), (int, float))
            and abs(repaired_metrics[key] - baseline_metrics[key]) < 1e-9
        ]
        lines.append(
            f"3. Repair chạy lại cleaning từ `data/raw/crossref_records.json` và khôi phục "
            f"{len(recovered)}/{len(METRIC_KEYS)} metric về đúng mức baseline"
            + (f" ({', '.join(f'`{k}`' for k in recovered)})." if recovered else ".")
        )
        if len(recovered) < len(METRIC_KEYS):
            lines.append(
                "   Các metric còn lại chưa về đúng baseline — nêu rõ trong báo cáo nhóm kèm giả thuyết, "
                "không được ghi là đã phục hồi hoàn toàn."
            )
    else:
        lines.append("3. Chưa có `repaired_metrics.json` — chưa kết luận được về khả năng phục hồi.")

    lines += [
        "",
        "## 5. Giới hạn của kết luận",
        "",
    ]

    if unchanged:
        lines.append(
            "- Các metric **không đổi** giữa baseline và corrupted: "
            + ", ".join(f"`{k}`" for k in unchanged)
            + ". Không được kết luận corruption ảnh hưởng lên những chỉ số này."
        )
    passed_after_corruption = [
        name for name, check in corrupted_checks.items() if check.get("success") is True
    ]
    if passed_after_corruption:
        lines.append(
            "- Các quality check **vẫn đạt** sau corruption: "
            + ", ".join(f"`{n}`" for n in passed_after_corruption)
            + ". Nghĩa là quality check không bắt được mọi dạng lỗi dữ liệu — "
            "ví dụ nhiễu trong summary và title bị cắt chỉ lộ ra qua metric của agent."
        )
    lines += [
        "- Crossref là nguồn sống nên số liệu giữa các nhóm sẽ khác nhau. "
        "Chỉ so sánh trong cùng bài làm, trên cùng snapshot raw và cùng test set.",
        "",
    ]
    write_text(report_path, "\n".join(lines) + "\n")
