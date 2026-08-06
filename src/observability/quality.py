from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import now_utc, write_json


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run the fixed Contract D data quality checks and write a JSON report."""
    total_rows = int(len(df))
    threshold_days = int(settings.freshness_threshold_days)

    paper_id = _string_column(df, "paper_id")
    title = _string_column(df, "title")
    summary = _string_column(df, "summary")
    age_days = _numeric_column(df, "age_days")
    duplicate_paper_ids = int(total_rows - paper_id.nunique())

    checks = [
        _check(
            name="row_count_min",
            dimension="Completeness",
            expected=">= 10",
            observed=total_rows,
            success=total_rows >= 10,
        ),
        _check(
            name="paper_id_not_null",
            dimension="Completeness",
            expected="== 0",
            observed=int(paper_id.eq("").sum()),
            success=int(paper_id.eq("").sum()) == 0,
        ),
        _check(
            name="paper_id_unique",
            dimension="Uniqueness",
            expected="== 0",
            observed=duplicate_paper_ids,
            success=duplicate_paper_ids == 0,
        ),
        _check(
            name="title_not_empty",
            dimension="Completeness",
            expected="== 0",
            observed=int(title.eq("").sum()),
            success=int(title.eq("").sum()) == 0,
        ),
        _check(
            name="summary_min_length",
            dimension="Validity",
            expected="== 0",
            observed=int(summary.str.len().lt(80).sum()),
            success=int(summary.str.len().lt(80).sum()) == 0,
        ),
        _check(
            name="freshness_age_days",
            dimension="Timeliness",
            expected="== 0",
            observed=int(age_days.gt(threshold_days).sum()),
            success=int(age_days.gt(threshold_days).sum()) == 0,
        ),
    ]

    success_count = sum(1 for item in checks if item["success"])
    report = {
        "report_name": report_name,
        "generated_at": now_utc().isoformat(),
        "total_rows": total_rows,
        "checks": checks,
        "success_count": success_count,
        "failed_count": len(checks) - success_count,
        "success": success_count == len(checks),
    }
    write_json(settings.paths.quality_dir / f"{report_name}.json", report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Build and write the Contract D freshness report for any pipeline state."""
    total_rows = int(len(df))
    threshold_days = int(settings.freshness_threshold_days)
    age_days = _numeric_column(df, "age_days")
    published = pd.to_datetime(_string_column(df, "published"), errors="coerce")

    stale_rows = int(age_days.gt(threshold_days).sum())
    max_age_days = int(age_days.max()) if total_rows and not age_days.empty else 0
    latest_published = published.max()
    oldest_published = published.min()

    report = {
        "generated_at": now_utc().isoformat(),
        "threshold_days": threshold_days,
        "latest_published": _date_or_empty(latest_published),
        "oldest_published": _date_or_empty(oldest_published),
        "max_age_days": max_age_days,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "is_fresh": stale_rows == 0,
    }
    write_json(Path(report_path), report)
    return report


def _string_column(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series([""] * len(df), index=df.index, dtype="string")
    return df[column].fillna("").astype(str).str.strip()


def _numeric_column(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series([0] * len(df), index=df.index, dtype="int64")
    return pd.to_numeric(df[column], errors="coerce").fillna(0).astype(int)


def _check(name: str, dimension: str, expected: str, observed: int, success: bool) -> dict[str, Any]:
    return {
        "name": name,
        "dimension": dimension,
        "expected": expected,
        "observed": int(observed),
        "success": bool(success),
    }


def _date_or_empty(value: pd.Timestamp) -> str:
    if pd.isna(value):
        return ""
    return value.date().isoformat()
