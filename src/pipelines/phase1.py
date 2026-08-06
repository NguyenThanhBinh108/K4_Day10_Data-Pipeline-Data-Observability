from __future__ import annotations

from datetime import UTC, datetime

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.demo import run_agent_demo
from retrieval.index import LocalEmbeddingIndex


def _snapshot_written_at(path) -> str:
    """Thoi diem raw snapshot duoc ghi ra dia.

    Bao cao phai ghi dung luc DU LIEU duoc lay, khong phai luc chay report. Neu dung
    now_utc() thi moi lan chay lai bao cao se khai mot moc thoi gian moi trong khi
    snapshot van la snapshot cu - bao cao khong con khop artifact.
    """
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()


def _judge_mode(answers: list[dict]) -> str:
    """Judge that su da chay bang LLM hay bang heuristic du phong.

    KHONG suy tu 'co API key nao do khong': settings co the co key cua provider khac
    voi LLM_PROVIDER dang chon, luc do build_llm van fail va judge van rot ve heuristic.
    Doc thang tu ket qua la cach duy nhat dung.

    Quan trong voi bao cao: judge_accuracy va mean_judge_score KHONG tai hien duoc
    giua hai che do, nen phai ghi ro che do nao da sinh ra so lieu.
    """
    if not answers:
        return "khong co ket qua"
    fallback = sum(1 for a in answers if "Fallback heuristic" in a.get("judge", {}).get("reasoning", ""))
    if fallback == len(answers):
        return "heuristic fallback (LLM judge khong dung duoc)"
    if fallback:
        return f"hon hop: {len(answers) - fallback}/{len(answers)} cau dung LLM judge"
    return "LLM judge"


def _validate_test_set_against(clean_df, settings) -> list[str]:
    """Test set bi dong bang tu CP2, con clean data co the doi neu refetch source.

    Neu mot ground_truth_doc_ids khong con trong clean data thi cau hoi do khong the
    retrieval trung duoc nua, va metric tut xuong vi ly do khong lien quan gi toi
    corruption. Phai canh bao thay vi de no am tham lam sai ket luan.
    """
    if not settings.paths.eval_testset.exists():
        return []
    known = set(clean_df["paper_id"].astype(str))
    missing = sorted(
        {doc_id for item in read_json(settings.paths.eval_testset) for doc_id in item["ground_truth_doc_ids"]}
        - known
    )
    if missing:
        print(
            f"[phase1] CANH BAO: {len(missing)} ground_truth_doc_ids trong test set khong con "
            f"trong clean data: {', '.join(missing[:5])}"
            + (" ..." if len(missing) > 5 else "")
        )
        print("[phase1] retrieval khong the trung nhung cau do. Dat REFRESH_TEST_SET=1 de sinh lai,")
        print("[phase1] nhung phai chay lai CA baseline va corruption flow de so sanh con y nghia.")
    return missing


def main() -> None:
    """Run the baseline pipeline end-to-end."""
    settings = load_settings()
    print("[phase1] start baseline pipeline")

    if settings.refresh_source or not settings.paths.raw_records_json.exists():
        records = fetch_source_records(settings)
        source_mode = "refetched"
    else:
        records = load_raw_records(settings.paths.raw_records_json)
        source_mode = "reused snapshot"
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

    orphan_doc_ids = _validate_test_set_against(clean_df, settings)

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
        "fetched_at": _snapshot_written_at(settings.paths.raw_records_json),
        "source_mode": source_mode,
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
        "judge_mode": _judge_mode(evaluation.answers),
    }
    if orphan_doc_ids:
        source_summary["test_set_orphan_doc_ids"] = len(orphan_doc_ids)
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
