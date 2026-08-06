from __future__ import annotations

import hashlib

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def _baseline_fingerprint(settings: Settings) -> dict[str, str]:
    """Hash cac artifact baseline de chung minh flow nay khong ghi de len chung.

    Cong nghiem thu CP5 doi 'baseline khong bi ghi de'. Khang dinh suong thi khong
    kiem chung duoc, nen ta bam truoc va sau roi doi chieu.
    """
    targets = {
        "clean_csv": settings.paths.clean_csv,
        "embeddings_json": settings.paths.embeddings_json,
        "baseline_metrics": settings.paths.baseline_metrics,
        "baseline_answers": settings.paths.baseline_answers,
        "eval_testset": settings.paths.eval_testset,
        "baseline_quality": settings.paths.quality_dir / "baseline_quality.json",
        "freshness_report": settings.paths.freshness_report,
    }
    return {
        name: hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        for name, path in targets.items()
        if path.exists()
    }


def main() -> None:
    """Run corruption, repaired evaluation, and comparison report."""
    settings = load_settings()
    print("[corruption] start corruption flow")

    if not settings.paths.clean_csv.exists():
        raise FileNotFoundError(f"Missing baseline clean dataset: {settings.paths.clean_csv}")
    if not settings.paths.baseline_metrics.exists():
        raise FileNotFoundError(f"Missing baseline metrics: {settings.paths.baseline_metrics}")
    if not settings.paths.eval_testset.exists():
        raise FileNotFoundError(f"Missing locked test set: {settings.paths.eval_testset}")

    fingerprint_before = _baseline_fingerprint(settings)

    clean_df = pd.read_csv(settings.paths.clean_csv).fillna("")
    baseline_metrics = read_json(settings.paths.baseline_metrics)

    # Doc quality/freshness cua baseline de bao cao so sanh co du ba cot co so lieu that
    # (yeu cau cua checkpoint C4), thay vi tro nguoc ve phase1_report.md.
    baseline_quality_path = settings.paths.quality_dir / "baseline_quality.json"
    baseline_quality = read_json(baseline_quality_path) if baseline_quality_path.exists() else {}
    baseline_freshness = (
        read_json(settings.paths.freshness_report) if settings.paths.freshness_report.exists() else {}
    )

    corrupted_df = corrupt_clean_dataframe(clean_df, settings.paths.corruption_log)
    write_csv(corrupted_df, settings.paths.corrupted_clean_csv)
    write_json(settings.paths.corrupted_clean_json, corrupted_df.to_dict(orient="records"))
    print(f"[corruption] saved corrupted dataset: {settings.paths.corrupted_clean_csv}")

    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df,
        settings,
        embeddings_output_path=settings.paths.corrupted_embeddings_json,
    )
    corrupted_eval = evaluate_pipeline(
        settings=settings,
        index=corrupted_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.corrupted_metrics,
        answers_output_path=settings.paths.corrupted_answers,
    )
    print(f"[corruption] corrupted metrics: {corrupted_eval.summary}")

    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted_quality")
    corrupted_freshness_path = settings.paths.quality_dir / "freshness_report_corrupted.json"
    corrupted_freshness = build_freshness_report(corrupted_df, settings, corrupted_freshness_path)

    records = load_raw_records(settings.paths.raw_records_json)
    repaired_df = build_clean_dataframe(records, now_utc())
    write_csv(repaired_df, settings.paths.repaired_clean_csv)
    write_json(settings.paths.repaired_clean_json, repaired_df.to_dict(orient="records"))
    print(f"[corruption] saved repaired dataset: {settings.paths.repaired_clean_csv}")

    repaired_index = LocalEmbeddingIndex.build(
        repaired_df,
        settings,
        embeddings_output_path=settings.paths.repaired_embeddings_json,
    )
    repaired_eval = evaluate_pipeline(
        settings=settings,
        index=repaired_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.repaired_metrics,
        answers_output_path=settings.paths.repaired_answers,
    )
    print(f"[corruption] repaired metrics: {repaired_eval.summary}")

    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired_quality")
    repaired_freshness_path = settings.paths.quality_dir / "freshness_report_repaired.json"
    repaired_freshness = build_freshness_report(repaired_df, settings, repaired_freshness_path)

    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_eval.summary,
        repaired_metrics=repaired_eval.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
        baseline_quality=baseline_quality,
        baseline_freshness=baseline_freshness,
    )
    print(f"[corruption] wrote report: {settings.paths.comparison_report}")

    changed = [
        name
        for name, digest in _baseline_fingerprint(settings).items()
        if fingerprint_before.get(name) != digest
    ]
    if changed:
        raise RuntimeError(
            "Corruption flow da ghi de artifact baseline: "
            + ", ".join(changed)
            + ". Baseline phai nguyen ven thi bang so sanh ba trang thai moi co y nghia."
        )
    print(f"[corruption] baseline nguyen ven: {len(fingerprint_before)} artifact khong doi")
    print("[corruption] done")
