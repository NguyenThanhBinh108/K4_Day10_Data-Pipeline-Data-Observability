"""Markdown reporting - Contract D (quality) + Contract F (metrics) la input.

Owner: R4 (Trinh Hai Dang).

Ca hai ham chi doc so tu artifact that (dict duoc phase1.py / corruption_flow.py
truyen vao sau khi da ghi ra data/results va data/quality) roi lap Markdown. Khong
tu tinh lai metric, khong hardcode con so, khong lam tron cho "dep". Neu mot khoa
bi thieu thi in dau gach ngang thay vi doan hoac lam vo report.

`generate_corruption_report` la noi de nguoi doc doi chieu 3 trang thai (baseline,
corrupted, repaired). Cot delta va muc phuc hoi phai tinh bang code tu chinh 3 file
metrics, khong go tay - neu go tay thi con so se lech moi lan pipeline chay lai.
"""

from __future__ import annotations

from typing import Any

from core.utils import now_utc, write_text

MISSING = "—"

# Bon metric so hoc trong Contract F. "ragas" khong nam trong list nay vi la dict
# long nhau (co the co "skipped" hoac "error" thay vi so).
METRIC_KEYS: list[tuple[str, str]] = [
    ("retrieval_hit_rate", "Ti le cau hoi truy hoi trung it nhat mot ground-truth document"),
    ("mean_token_f1", "Trung binh token-F1 giua cau tra loi va ground truth"),
    ("judge_accuracy", "Ti le cau duoc LLM judge cham la dung ve ban chat"),
    ("mean_judge_score", "Diem trung binh cua judge, thang 1-5"),
]


def _fmt_number(value: Any, digits: int = 4) -> str:
    """Format mot gia tri so; tra dau gach neu khong phai so (chua chay / loi)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return MISSING
    text = f"{value:.{digits}f}"
    return text.rstrip("0").rstrip(".") if digits else text


def _fmt_delta(after: Any, before: Any, digits: int = 4) -> str:
    """Chenh lech co dau giua hai gia tri so, dung cho cot 'thay doi do corruption'."""
    if not isinstance(after, (int, float)) or not isinstance(before, (int, float)):
        return MISSING
    if isinstance(after, bool) or isinstance(before, bool):
        return MISSING
    diff = after - before
    if abs(diff) < 1e-12:
        return "0"
    return f"{diff:+.{digits}f}".rstrip("0").rstrip(".")


def _fmt_recovery(baseline: Any, corrupted: Any, repaired: Any) -> str:
    """% cua khoang bi mat (baseline - corrupted) ma repaired lay lai duoc.

    100% nghia la repaired dung bang baseline, 0% nghia la khong phuc hoi gi,
    am nghia la repaired con te hon corrupted. "n/a" khi corruption khong lam
    metric doi (khong co gi de phuc hoi).
    """
    values = (baseline, corrupted, repaired)
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values):
        return MISSING
    lost = baseline - corrupted
    if abs(lost) < 1e-12:
        return "n/a"
    return f"{(repaired - corrupted) / lost * 100:.0f}%"


def _fmt_flag(value: Any) -> str:
    if value is True:
        return "PASS"
    if value is False:
        return "FAIL"
    return MISSING


def _quality_line(quality: dict[str, Any]) -> str:
    if not quality:
        return MISSING
    passed = quality.get("success_count")
    failed = quality.get("failed_count")
    if passed is None or failed is None:
        return MISSING
    return f"{passed}/{passed + failed} pass"


def _freshness_line(freshness: dict[str, Any]) -> str:
    if not freshness or "is_fresh" not in freshness:
        return MISSING
    state = "Fresh" if freshness["is_fresh"] else "Stale"
    return f"{state} (stale_rows={freshness.get('stale_rows', MISSING)})"


def _source_summary_table(source_summary: dict[str, Any]) -> list[str]:
    """Render source_summary do phase1.py truyen vao.

    Danh sach nhan duoi day chi la thu tu hien thi uu tien; khoa la khong co
    trong danh sach van duoc in ra o cuoi bang thay vi bi bo qua, de phase1.py
    co the them truong moi ma khong phai sua file nay.
    """
    known_labels = [
        ("source", "Nguon"),
        ("query", "Query"),
        ("filter", "Filter"),
        ("fetched_at", "Thoi diem lay du lieu"),
        ("raw_records", "So raw record"),
        ("clean_rows", "So dong sau cleaning"),
        ("dropped", "So record bi loai khi cleaning"),
        ("embedding_model", "Embedding model"),
        ("collection", "Vector collection"),
        ("top_k", "Retrieval top_k"),
        ("llm_provider", "LLM provider"),
        ("llm_model", "LLM model"),
    ]
    lines = ["| Thuoc tinh | Gia tri |", "| --- | --- |"]
    for key, label in known_labels:
        if key in source_summary:
            lines.append(f"| {label} | `{source_summary[key]}` |")
    known_keys = {key for key, _ in known_labels}
    for key, value in source_summary.items():
        if key not in known_keys:
            lines.append(f"| {key} | `{value}` |")
    return lines


def _metrics_table(metrics: dict[str, Any]) -> list[str]:
    lines = ["| Metric | Gia tri | Y nghia |", "| --- | ---: | --- |"]
    for key, meaning in METRIC_KEYS:
        digits = 2 if key == "mean_judge_score" else 4
        lines.append(f"| `{key}` | {_fmt_number(metrics.get(key), digits)} | {meaning} |")
    lines.append(f"| `samples` | {metrics.get('samples', MISSING)} | So cau hoi trong test set |")

    ragas = metrics.get("ragas")
    if isinstance(ragas, dict) and "skipped" in ragas:
        lines.append(f"| `ragas` | {MISSING} | Bo qua - dat `RUN_RAGAS=1` de bat |")
    elif isinstance(ragas, dict) and "error" in ragas:
        lines.append(f"| `ragas` | {MISSING} | Loi: {ragas['error']} |")
    elif isinstance(ragas, dict) and ragas:
        for key, value in ragas.items():
            lines.append(f"| `ragas.{key}` | {_fmt_number(value)} | |")
    return lines


def _quality_checks_table(quality: dict[str, Any]) -> list[str]:
    checks = quality.get("checks") or []
    if not checks:
        return ["_Chua co quality check nao._"]
    lines = [
        "| Check | Dimension | Ky vong | Quan sat | Ket qua |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for check in checks:
        lines.append(
            f"| `{check.get('name', MISSING)}` | {check.get('dimension', MISSING)} "
            f"| `{check.get('expected', MISSING)}` | {check.get('observed', MISSING)} "
            f"| {_fmt_flag(check.get('success'))} |"
        )
    return lines


def _freshness_table(freshness: dict[str, Any]) -> list[str]:
    if not freshness:
        return ["_Chua co freshness report._"]
    rows = [
        ("Nguong freshness", f"{freshness.get('threshold_days', MISSING)} ngay"),
        ("Published moi nhat", freshness.get("latest_published", MISSING)),
        ("Published cu nhat", freshness.get("oldest_published", MISSING)),
        ("age_days lon nhat", freshness.get("max_age_days", MISSING)),
        ("So dong qua han", freshness.get("stale_rows", MISSING)),
        ("Tong so dong", freshness.get("total_rows", MISSING)),
        ("Trang thai", "Fresh" if freshness.get("is_fresh") else "Stale"),
    ]
    return ["| Thuoc tinh | Gia tri |", "| --- | --- |"] + [f"| {k} | `{v}` |" for k, v in rows]


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Bao cao baseline: nguon du lieu, evaluation metrics, quality checks va freshness."""
    failed_checks = [c for c in (quality.get("checks") or []) if not c.get("success")]

    lines = [
        "# Bao cao Pha 1 - Baseline tren du lieu sach",
        "",
        f"_Sinh tu dong luc {now_utc().isoformat()} tu artifact that trong `data/`._",
        "",
        "## 1. Nguon du lieu va cau hinh",
        "",
        *_source_summary_table(source_summary),
        "",
        "## 2. Ket qua danh gia",
        "",
        *_metrics_table(metrics),
        "",
        "## 3. Data quality checks",
        "",
        f"**Tong ket:** {_quality_line(quality)} - trang thai chung "
        f"`{_fmt_flag(quality.get('success'))}` tren {quality.get('total_rows', MISSING)} dong.",
        "",
        *_quality_checks_table(quality),
        "",
    ]

    if failed_checks:
        details = ", ".join(f"`{c['name']}` (quan sat `{c['observed']}`)" for c in failed_checks)
        lines += [
            f"> **Canh bao:** baseline da co check khong dat: {details}. "
            "Phai xu ly truoc khi chay corruption flow, neu khong se khong phan biet duoc "
            "loi do corruption voi loi co san tu dau.",
            "",
        ]

    lines += [
        "## 4. Freshness",
        "",
        *_freshness_table(freshness),
        "",
        "## 5. Trang thai",
        "",
        f"- Data quality: `{_fmt_flag(quality.get('success'))}`",
        f"- Freshness: `{_freshness_line(freshness)}`",
        "- Baseline nay la moc so sanh cho corrupted va repaired. Ca ba trang thai phai "
        "danh gia tren cung `data/eval/test_set.json`.",
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

    Cot delta va muc phuc hoi tinh hoan toan bang code tu ba file metrics that,
    khong go tay so lieu.
    """
    baseline_metrics = baseline_metrics or {}
    corrupted_metrics = corrupted_metrics or {}
    repaired_metrics = repaired_metrics or {}

    lines = [
        "# Bao cao so sanh - Baseline / Corrupted / Repaired",
        "",
        f"_Sinh tu dong luc {now_utc().isoformat()} tu `data/results/*_metrics.json`, "
        "`data/quality/*.json` va `data/results/corruption_log.json`._",
        "",
        "Ca ba trang thai duoc danh gia tren **cung mot** `data/eval/test_set.json`, cung "
        "embedding model va cung `top_k`. Neu khong, cac cot duoi day khong so sanh duoc.",
        "",
        "## 1. Bang so sanh metrics",
        "",
        "| Metric | Baseline | Corrupted | Repaired | Delta corruption | Muc phuc hoi |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    unchanged_metrics: list[str] = []
    degraded_metrics: list[tuple[str, Any, Any]] = []

    for key, _ in METRIC_KEYS:
        digits = 2 if key == "mean_judge_score" else 4
        base = baseline_metrics.get(key)
        corr = corrupted_metrics.get(key)
        rep = repaired_metrics.get(key)
        lines.append(
            f"| `{key}` | {_fmt_number(base, digits)} | {_fmt_number(corr, digits)} "
            f"| {_fmt_number(rep, digits)} | {_fmt_delta(corr, base, digits)} "
            f"| {_fmt_recovery(base, corr, rep)} |"
        )
        if isinstance(base, (int, float)) and isinstance(corr, (int, float)):
            if abs(base - corr) < 1e-12:
                unchanged_metrics.append(key)
            elif corr < base:
                degraded_metrics.append((key, base, corr))

    lines += [
        "",
        "## 2. Data quality checks",
        "",
        "| Check | Baseline | Corrupted | Repaired |",
        "| --- | --- | --- | --- |",
    ]

    # Baseline quality khong nam trong tham so ham nay (contract chi truyen corrupted
    # + repaired) - cot baseline tro nguoi doc sang phase1_report.md thay vi doan lai.
    corrupted_checks = {c["name"]: c for c in (corrupted_quality.get("checks") or [])}
    repaired_checks = {c["name"]: c for c in (repaired_quality.get("checks") or [])}
    flipped_checks: list[str] = []

    for name in list(corrupted_checks) or list(repaired_checks):
        corr_check = corrupted_checks.get(name, {})
        rep_check = repaired_checks.get(name, {})
        corr_cell = f"{_fmt_flag(corr_check.get('success'))} (`{corr_check.get('observed', MISSING)}`)"
        rep_cell = f"{_fmt_flag(rep_check.get('success'))} (`{rep_check.get('observed', MISSING)}`)"
        lines.append(f"| `{name}` | xem `phase1_report.md` | {corr_cell} | {rep_cell} |")
        if corr_check.get("success") is False:
            flipped_checks.append(name)

    lines += [
        "",
        f"- Corrupted: {_quality_line(corrupted_quality)}, tong `{_fmt_flag(corrupted_quality.get('success'))}`",
        f"- Repaired: {_quality_line(repaired_quality)}, tong `{_fmt_flag(repaired_quality.get('success'))}`",
        "",
        "## 3. Freshness",
        "",
        "| Thuoc tinh | Corrupted | Repaired |",
        "| --- | --- | --- |",
        f"| Trang thai | {_freshness_line(corrupted_freshness)} | {_freshness_line(repaired_freshness)} |",
        f"| `max_age_days` | `{corrupted_freshness.get('max_age_days', MISSING)}` "
        f"| `{repaired_freshness.get('max_age_days', MISSING)}` |",
        f"| `latest_published` | `{corrupted_freshness.get('latest_published', MISSING)}` "
        f"| `{repaired_freshness.get('latest_published', MISSING)}` |",
        f"| `oldest_published` | `{corrupted_freshness.get('oldest_published', MISSING)}` "
        f"| `{repaired_freshness.get('oldest_published', MISSING)}` |",
        "",
        "## 4. Ket luan rut ra tu so lieu",
        "",
    ]

    if flipped_checks:
        flipped_text = ", ".join(f"`{n}`" for n in flipped_checks)
        if corrupted_freshness.get("is_fresh") is False:
            freshness_note = (
                "va freshness lat sang `is_fresh=false` (`max_age_days` = "
                f"`{corrupted_freshness.get('max_age_days', MISSING)}`)."
            )
        else:
            freshness_note = "trong khi freshness khong doi."
        lines.append(
            f"1. Corruption lam {len(flipped_checks)} quality check chuyen sang FAIL "
            f"({flipped_text}), {freshness_note}"
        )
    else:
        lines.append("1. Khong quality check nao chuyen sang FAIL sau corruption.")

    if degraded_metrics:
        worst_key, worst_base, worst_corr = min(degraded_metrics, key=lambda item: item[2] - item[1])
        lines.append(
            f"2. Chat luong agent giam o {len(degraded_metrics)} metric. Giam manh nhat la "
            f"`{worst_key}`: {_fmt_number(worst_base)} -> {_fmt_number(worst_corr)} "
            f"({_fmt_delta(worst_corr, worst_base)})."
        )
    else:
        lines.append(
            "2. **Khong metric nao cua agent giam sau corruption.** Khong duoc ket luan corruption "
            "co tac dong len chat luong tra loi. Can kiem tra: corruption co cham vao cac paper nam "
            "trong test set khong, va `text_for_embedding` da duoc build lai sau khi lam hong du lieu chua."
        )

    if repaired_metrics:
        recovered_metrics = [
            key
            for key, _ in METRIC_KEYS
            if isinstance(baseline_metrics.get(key), (int, float))
            and isinstance(repaired_metrics.get(key), (int, float))
            and abs(repaired_metrics[key] - baseline_metrics[key]) < 1e-9
        ]
        recovered_text = (
            f" ({', '.join(f'`{k}`' for k in recovered_metrics)})." if recovered_metrics else "."
        )
        lines.append(
            f"3. Repair chay lai cleaning tu `data/raw/crossref_records.json` va khoi phuc "
            f"{len(recovered_metrics)}/{len(METRIC_KEYS)} metric ve dung muc baseline{recovered_text}"
        )
        if len(recovered_metrics) < len(METRIC_KEYS):
            lines.append(
                "   Cac metric con lai chua ve dung baseline - neu ro trong bao cao nhom kem gia "
                "thuyet, khong duoc ghi la da phuc hoi hoan toan."
            )
    else:
        lines.append("3. Chua co `repaired_metrics.json` - chua ket luan duoc ve kha nang phuc hoi.")

    lines += [
        "",
        "## 5. Gioi han cua ket luan",
        "",
    ]

    if unchanged_metrics:
        unchanged_text = ", ".join(f"`{k}`" for k in unchanged_metrics)
        lines.append(
            f"- Cac metric **khong doi** giua baseline va corrupted: {unchanged_text}. "
            "Khong duoc ket luan corruption anh huong len nhung chi so nay."
        )
    still_passing = [name for name, check in corrupted_checks.items() if check.get("success") is True]
    if still_passing:
        still_passing_text = ", ".join(f"`{n}`" for n in still_passing)
        lines.append(
            f"- Cac quality check **van dat** sau corruption: {still_passing_text}. Nghia la quality "
            "check khong bat duoc moi dang loi du lieu - vi du nhieu trong summary va title bi cat "
            "chi lo ra qua metric cua agent."
        )
    lines += [
        "- Crossref la nguon song nen so lieu giua cac nhom se khac nhau. Chi so sanh trong cung "
        "bai lam, tren cung snapshot raw va cung test set.",
        "",
    ]
    write_text(report_path, "\n".join(lines) + "\n")
