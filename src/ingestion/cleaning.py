"""Cleaning & data modeling — Contract B.

Owner: R1 (Nguyen Thanh Binh).

Bien list[PaperRecord] thanh DataFrame san sang embed. Ham `build_clean_dataframe`
duoc goi HAI lan trong bai lab — mot lan cho baseline, mot lan cho repaired — nen
no phai thuan: cung input cho ra cung output, khong doc/ghi file, khong phu thuoc state ngoai.

9 cot khoa duoi day duoc `retrieval/index.py::_build_documents` doc theo ten cung;
gia tri cua chung di thang vao metadata ChromaDB nen chi duoc la str/int/float/bool.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from core.utils import normalize_whitespace
from ingestion.crossref import PaperRecord

MIN_SUMMARY_CHARS = 80

# 9 cot bi ep boi retrieval/index.py — thieu mot cot la KeyError khi build index.
INDEX_REQUIRED_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors_joined",
    "categories_joined",
    "published",
    "abs_url",
    "pdf_url",
    "text_for_embedding",
]

# Thu tu cot cuoi cung cua clean dataset.
CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "authors_joined",
    "categories",
    "categories_joined",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "comment",
    "summary_chars",
    "age_days",
    "text_for_embedding",
]


def build_text_for_embedding(row: Any) -> str:
    """Template `text_for_embedding` — nguon su that duy nhat cua Contract B.

    Corruption cung goi ham nay de rebuild sau khi lam hong du lieu, nen template
    khong bao gio lech giua baseline va corrupted.

    Gop du 5 field co chu dich: corrupt bat ky field nao cung lam embedding lech,
    nho vay moi do duoc impact. Neu chi embed summary thi corrupt title/date se
    khong lam metric thay doi va ca bai lab mat y nghia.
    """
    return (
        f"Title: {row['title']}\n"
        f"Authors: {row['authors_joined']}\n"
        f"Categories: {row['categories_joined']}\n"
        f"Published: {row['published']}\n"
        f"Summary: {row['summary']}"
    )


def compute_age_days(published: str, run_date: datetime | date) -> int:
    """So ngay tu ngay xuat ban den thoi diem chay. Dung cho quality va freshness."""
    reference = run_date.date() if isinstance(run_date, datetime) else run_date
    parsed = parse_iso_date(published)
    if parsed is None:
        return -1
    return (reference - parsed).days


def parse_iso_date(value: Any) -> date | None:
    """Parse chuoi `YYYY-MM-DD`. Tra None neu khong parse duoc, khong nem exception."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _join(values: Any, fallback: str) -> str:
    if isinstance(values, list):
        parts = [normalize_whitespace(str(item)) for item in values]
        joined = ", ".join(part for part in parts if part)
    else:
        joined = normalize_whitespace(str(values or ""))
    return joined or fallback


def enforce_clean_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Ep dtype truoc khi tra ve.

    ChromaDB chi nhan str/int/float/bool trong metadata. Mot NaN, None, Timestamp
    hoac numpy.int64 lot vao 9 cot khoa se lam `collection.add` bao loi.
    Day la nguyen nhan loi so 1 cua bai lab nay.
    """
    for column in INDEX_REQUIRED_COLUMNS:
        df[column] = df[column].fillna("").astype(str)
    df["summary_chars"] = df["summary_chars"].fillna(0).astype(int)
    df["age_days"] = df["age_days"].fillna(-1).astype(int)
    for column in ("primary_category", "updated", "comment"):
        df[column] = df[column].fillna("").astype(str)
    return df


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records thanh dataframe san sang embed.

    Moi rule loai bo deu dem duoc va luu vao `df.attrs["cleaning_stats"]` —
    khong lam mat record am tham, vi CP1 yeu cau truy vet duoc ly do tung record bi loai.
    """
    stats = {
        "records_in": len(records),
        "dropped_no_id": 0,
        "dropped_no_title": 0,
        "dropped_short_summary": 0,
        "dropped_bad_date": 0,
        "dropped_duplicate": 0,
    }

    rows: list[dict[str, Any]] = []
    for record in records:
        paper_id = normalize_whitespace(record.paper_id).lower()
        if not paper_id:
            stats["dropped_no_id"] += 1
            continue

        title = normalize_whitespace(record.title)
        if not title:
            stats["dropped_no_title"] += 1
            continue

        summary = normalize_whitespace(record.summary)
        if len(summary) < MIN_SUMMARY_CHARS:
            stats["dropped_short_summary"] += 1
            continue

        published_date = parse_iso_date(record.published)
        if published_date is None:
            stats["dropped_bad_date"] += 1
            continue

        authors = [normalize_whitespace(name) for name in record.authors if normalize_whitespace(name)]
        categories = [normalize_whitespace(item) for item in record.categories if normalize_whitespace(item)]

        rows.append(
            {
                "paper_id": paper_id,
                "title": title,
                "summary": summary,
                "authors": authors,
                "authors_joined": _join(authors, "Unknown"),
                "categories": categories,
                "categories_joined": _join(categories, "uncategorized"),
                "primary_category": categories[0] if categories else "uncategorized",
                "published": published_date.isoformat(),
                "updated": (parse_iso_date(record.updated) or published_date).isoformat(),
                "abs_url": normalize_whitespace(record.abs_url),
                "pdf_url": normalize_whitespace(record.pdf_url),
                "comment": normalize_whitespace(record.comment),
                "summary_chars": len(summary),
                "age_days": compute_age_days(published_date.isoformat(), run_date),
            }
        )

    if not rows:
        raise ValueError(
            "Khong con record nao sau cleaning. Kiem tra raw records va cac rule loai bo trong cleaning.py."
        )

    df = pd.DataFrame(rows)

    before_dedupe = len(df)
    df = df.drop_duplicates(subset="paper_id", keep="first")
    stats["dropped_duplicate"] = before_dedupe - len(df)

    df = df.sort_values("published", ascending=False).reset_index(drop=True)
    df["text_for_embedding"] = df.apply(build_text_for_embedding, axis=1)
    df = df[CLEAN_COLUMNS]
    df = enforce_clean_dtypes(df)

    stats["records_out"] = len(df)
    df.attrs["cleaning_stats"] = stats

    dropped = sum(value for key, value in stats.items() if key.startswith("dropped_"))
    print(
        f"[cleaning] {stats['records_in']} raw -> {stats['records_out']} clean "
        f"(loai {dropped}: no_id={stats['dropped_no_id']}, no_title={stats['dropped_no_title']}, "
        f"short_summary={stats['dropped_short_summary']}, bad_date={stats['dropped_bad_date']}, "
        f"duplicate={stats['dropped_duplicate']})"
    )
    return df
