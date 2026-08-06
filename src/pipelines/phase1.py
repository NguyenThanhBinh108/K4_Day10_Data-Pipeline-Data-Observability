from __future__ import annotations

from core.config import load_settings
from core.utils import now_utc, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.demo import run_agent_demo
from retrieval.index import LocalEmbeddingIndex


def main() -> None:
    """Run the baseline pipeline end-to-end."""
    settings = load_settings()
    print("[phase1] start baseline pipeline")

    if settings.refresh_source or not settings.paths.raw_records_json.exists():
        records = fetch_source_records(settings)
    else:
        records = load_raw_records(settings.paths.raw_records_json)
        print(f"[phase1] loaded raw snapshot: {len(records)} records")

    clean_df = build_clean_dataframe(records, now_utc())
    write_csv(clean_df, settings.paths.clean_csv)
    write_json(settings.paths.clean_json, clean_df.to_dict(orient="records"))
    print(f"[phase1] saved clean dataset: {settings.paths.clean_csv}")

    index = LocalEmbeddingIndex.build(
        clean_df,
        settings,
        embeddings_output_path=settings.paths.embeddings_json,
    )
    print(f"[phase1] built index: {index.collection_name} ({len(index.documents)} docs)")

    if settings.refresh_test_set or not settings.paths.eval_testset.exists():
        test_set = build_test_set(clean_df, settings.paths.eval_testset)
        print(f"[phase1] built test set: {len(test_set)} questions")
    else:
        print(f"[phase1] using existing test set: {settings.paths.eval_testset}")

    evaluation = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )
    print(f"[phase1] baseline metrics: {evaluation.summary}")

    quality = run_data_quality_checks(clean_df, settings, "baseline_quality")
    freshness = build_freshness_report(clean_df, settings, settings.paths.freshness_report)

    source_summary = {
        "source": settings.source_api,
        "query": settings.source_query,
        "filter": settings.source_filter,
        "fetched_at": now_utc().isoformat(),
        "raw_records": len(records),
        "clean_rows": len(clean_df),
        "dropped": sum(
            value for key, value in clean_df.attrs.get("cleaning_stats", {}).items() if key.startswith("dropped_")
        ),
        "embedding_model": settings.embedding_model,
        "collection": index.collection_name,
        "top_k": settings.top_k,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.model_name,
    }
    generate_phase1_report(
        settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=evaluation.summary,
        quality=quality,
        freshness=freshness,
    )
    print(f"[phase1] wrote report: {settings.paths.baseline_report}")

    run_agent_demo(settings, index)
    print("[phase1] done")
