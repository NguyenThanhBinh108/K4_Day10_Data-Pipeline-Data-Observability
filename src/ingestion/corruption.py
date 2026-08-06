"""Corruption co kiem soat — Contract E.

Owner: R1 (Nguyen Thanh Binh).

Mo phong 6 dang loi du lieu thuong gap trong production, moi dang deu:
- co chu dich (nham vao mot quality dimension cu the),
- co log (paper_id + tham so + before/after count),
- do duoc tac dong (lam lech embedding chu khong chi lech metadata).

Ba rule bat buoc:
1. `df.copy()` ngay dau — baseline dataframe phai nguyen ven.
2. Rebuild `text_for_embedding` bang dung template cua Contract B. Quen buoc nay thi
   embedding van sach, metric khong doi, va ca bai lab khong chung minh duoc gi.
3. Giu nguyen schema Contract B — corrupted dataframe cung di qua LocalEmbeddingIndex.build.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from core.utils import now_utc, write_json
from ingestion.cleaning import build_text_for_embedding, enforce_clean_dtypes, parse_iso_date

# Chon record bi hong bang thuat toan phan tang tat dinh (khong random), xem `_spread_ids`.
SELECTION_STRATEGY = "stratified-by-published-desc"

DROP_LATEST_COUNT = 3
BLANK_SUMMARY_RATIO = 0.20
NOISE_RATIO = 0.25
TRUNCATE_TITLE_RATIO = 0.20
TRUNCATE_TITLE_KEEP = 12
STALE_RATIO = 0.25
STALE_SHIFT_DAYS = 800
DUPLICATE_COUNT = 3

NOISE_TEXT = " lorem ipsum ### %%% dolor sit amet @@@ consectetur ??? adipiscing $$$"


def _spread_ids(df: pd.DataFrame, count: int, offset: int = 0) -> list[str]:
    """Chon `count` paper_id trai deu tren thu tu published giam dan.

    Khong dung random: bo test set bat buoc chua paper moi nhat va cu nhat (Contract C),
    nen neu chon ngau nhien thi co the truot het cac paper duoc hoi va corruption se
    khong lam metric thay doi. Chon phan tang dam bao moi corruption cham ca dau moi,
    dau cu lan giua dai — tuc chac chan giao voi test set.

    `offset` lech nhau giua cac kich ban de chung khong don het vao cung mot nhom dong.
    """
    ids = list(df.sort_values("published", ascending=False)["paper_id"])
    total = len(ids)
    if total == 0 or count <= 0:
        return []

    count = min(count, total)
    step = total / count
    picked: list[str] = []
    taken: set[int] = set()
    for position in range(count):
        index = (int(position * step) + offset) % total
        while index in taken:
            index = (index + 1) % total
        taken.add(index)
        picked.append(ids[index])
    return sorted(picked)


def _spread_ratio(df: pd.DataFrame, ratio: float, offset: int = 0) -> list[str]:
    """Chon theo ty le, luon lay it nhat 1 dong neu dataframe khong rong."""
    if df.empty:
        return []
    return _spread_ids(df, max(1, round(len(df) * ratio)), offset)


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path: Path) -> pd.DataFrame:
    """Tao corrupted dataset tu clean dataset va ghi corruption log."""
    corrupted = df.copy(deep=True)
    rows_before = len(corrupted)
    operations: list[dict[str, Any]] = []

    # 1. Drop cac ban ghi moi nhat — mo phong pipeline ingest bi ngat, khong lay duoc du lieu moi.
    latest_ids = list(
        corrupted.sort_values("published", ascending=False)["paper_id"].head(DROP_LATEST_COUNT)
    )
    corrupted = corrupted[~corrupted["paper_id"].isin(latest_ids)].reset_index(drop=True)
    operations.append(
        {
            "type": "drop_latest_records",
            "count": len(latest_ids),
            "paper_ids": latest_ids,
            "params": {"n": DROP_LATEST_COUNT},
            "expected_signal": "freshness stale + retrieval miss cac cau hoi ve paper moi",
        }
    )

    # 2. Summary rong — mo phong upstream doi schema hoac field abstract bi null.
    blank_ids = _spread_ratio(corrupted, BLANK_SUMMARY_RATIO, offset=0)
    corrupted.loc[corrupted["paper_id"].isin(blank_ids), "summary"] = ""
    operations.append(
        {
            "type": "blank_summary",
            "count": len(blank_ids),
            "paper_ids": blank_ids,
            "params": {"ratio": BLANK_SUMMARY_RATIO},
            "expected_signal": "quality check summary_min_length fail",
        }
    )

    # 3. Noise trong summary — mo phong loi encoding/scraping lam ban text.
    noise_pool = corrupted[~corrupted["paper_id"].isin(blank_ids)]
    noise_ids = _spread_ratio(noise_pool, NOISE_RATIO, offset=1)
    noise_mask = corrupted["paper_id"].isin(noise_ids)
    corrupted.loc[noise_mask, "summary"] = corrupted.loc[noise_mask, "summary"] + NOISE_TEXT
    operations.append(
        {
            "type": "inject_noise",
            "count": len(noise_ids),
            "paper_ids": noise_ids,
            "params": {"ratio": NOISE_RATIO, "noise": NOISE_TEXT.strip()},
            "expected_signal": "embedding lech, token_f1 giam; quality co the van pass",
        }
    )

    # 4. Title bi cat — mo phong truncation khi ghi qua cot VARCHAR ngan.
    truncate_ids = _spread_ratio(corrupted, TRUNCATE_TITLE_RATIO, offset=2)
    truncate_mask = corrupted["paper_id"].isin(truncate_ids)
    corrupted.loc[truncate_mask, "title"] = corrupted.loc[truncate_mask, "title"].str[:TRUNCATE_TITLE_KEEP]
    operations.append(
        {
            "type": "truncate_title",
            "count": len(truncate_ids),
            "paper_ids": truncate_ids,
            "params": {"ratio": TRUNCATE_TITLE_RATIO, "keep_chars": TRUNCATE_TITLE_KEEP},
            "expected_signal": "exact lookup theo title trong qa.py hong",
        }
    )

    # 5. Ngay xuat ban bi day lui — mo phong sai timezone/backfill sai lam data trong nhu da cu.
    stale_ids = _spread_ratio(corrupted, STALE_RATIO, offset=3)
    for paper_id in stale_ids:
        mask = corrupted["paper_id"] == paper_id
        published = parse_iso_date(corrupted.loc[mask, "published"].iloc[0])
        if published is None:
            continue
        corrupted.loc[mask, "published"] = (published - timedelta(days=STALE_SHIFT_DAYS)).isoformat()
        corrupted.loc[mask, "age_days"] = corrupted.loc[mask, "age_days"] + STALE_SHIFT_DAYS
    operations.append(
        {
            "type": "stale_dates",
            "count": len(stale_ids),
            "paper_ids": stale_ids,
            "params": {"ratio": STALE_RATIO, "shift_days": STALE_SHIFT_DAYS},
            "expected_signal": "freshness_age_days fail, is_fresh=false",
        }
    )

    # 6. Dong trung lap — mo phong job ingest chay hai lan, khong idempotent.
    duplicate_ids = _spread_ids(corrupted, DUPLICATE_COUNT, offset=4)
    duplicates = corrupted[corrupted["paper_id"].isin(duplicate_ids)].copy()
    corrupted = pd.concat([corrupted, duplicates], ignore_index=True)
    operations.append(
        {
            "type": "duplicate_rows",
            "count": len(duplicates),
            "paper_ids": duplicate_ids,
            "params": {"n": DUPLICATE_COUNT},
            "expected_signal": "quality check paper_id_unique fail",
        }
    )

    # Rebuild cac cot dan xuat: neu bo qua buoc nay thi corruption chi nam o metadata,
    # embedding van sach va metric se khong thay doi.
    corrupted["summary_chars"] = corrupted["summary"].fillna("").astype(str).str.len()
    corrupted["text_for_embedding"] = corrupted.apply(build_text_for_embedding, axis=1)
    corrupted = enforce_clean_dtypes(corrupted)

    log = {
        "generated_at": now_utc().isoformat(),
        "selection_strategy": SELECTION_STRATEGY,
        "rows_before": rows_before,
        "rows_after": len(corrupted),
        "unique_paper_ids_after": int(corrupted["paper_id"].nunique()),
        "operations": operations,
    }
    write_json(Path(output_log_path), log)

    affected = sum(operation["count"] for operation in operations)
    print(
        f"[corruption] {rows_before} -> {len(corrupted)} dong, "
        f"{len(operations)} kich ban, {affected} luot tac dong -> {output_log_path}"
    )
    return corrupted
