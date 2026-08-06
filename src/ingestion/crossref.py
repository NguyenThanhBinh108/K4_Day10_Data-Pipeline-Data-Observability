"""Crossref ingestion - Contract A.

Owner: R1 (Nguyen Thanh Binh).

Lay metadata bai bao tu Crossref REST API, luu raw response truoc khi parse,
parse thanh `PaperRecord` co schema on dinh, roi luu snapshot raw records.

Snapshot `data/raw/crossref_records.json` la **diem khoi phuc** cua ca bai lab:
repair o pha 2 doc lai dung file nay chu khong goi lai API.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import date
from pathlib import Path
from typing import Any
import html
import os
import re
import time

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json

CROSSREF_API_URL = "https://api.crossref.org/works"

# Chi giu record du dieu kien lam document RAG. Nguong nay lap lai o cleaning va quality check.
MIN_SUMMARY_CHARS = 80

# Retry cho cac loi tam thoi cua Crossref. 429 = rate limit, 5xx = loi phia server.
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
REQUEST_TIMEOUT = 30

# Crossref uu tien request co mailto (polite pool). Dat CROSSREF_MAILTO trong .env de duoc uu tien.
_TAG_RE = re.compile(r"<[^>]+>")
_LEADING_LABEL_RE = re.compile(r"^(abstract|summary)\s*[:.\-]?\s*", re.IGNORECASE)


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _user_agent() -> str:
    base = "Day10DataLab/1.0 (https://github.com/NguyenThanhBinh108)"
    mailto = os.getenv("CROSSREF_MAILTO", "").strip()
    return f"{base} mailto:{mailto}" if mailto else base


def _clean_text(value: Any) -> str:
    """Bo tag JATS/HTML, giai ma entity, gop whitespace."""
    if not value:
        return ""
    text = html.unescape(str(value))
    text = _TAG_RE.sub(" ", text)
    # Mot so abstract con entity long trong tag da bo, unescape them mot lan.
    text = html.unescape(text)
    return normalize_whitespace(text)


def _clean_abstract(value: Any) -> str:
    """Abstract cua Crossref la JATS XML va thuong mo dau bang <jats:title>Abstract</jats:title>."""
    return _LEADING_LABEL_RE.sub("", _clean_text(value))


def _first_string(value: Any) -> str:
    if isinstance(value, list):
        return _clean_text(value[0]) if value else ""
    return _clean_text(value)


def _date_from_parts(node: Any) -> str:
    """Crossref tra ngay dang {"date-parts": [[2026, 3, 14]]}, co the thieu thang/ngay."""
    if not isinstance(node, dict):
        return ""
    parts = node.get("date-parts") or []
    if not parts or not isinstance(parts[0], list):
        return ""
    values = [int(part) for part in parts[0] if isinstance(part, int)]
    if not values:
        return ""
    year = values[0]
    month = values[1] if len(values) > 1 else 1
    day = values[2] if len(values) > 2 else 1
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _effective_published(issued: str, created: str) -> str:
    """Ngay cong bo hieu luc = min(issued, created).

    Crossref `issued` la ngay xuat ban DANH NGHIA do nha xuat ban khai, va rat hay
    nam o TUONG LAI (so tap chi sap phat hanh). Lay truc tiep lam moc freshness thi
    `age_days` ra so AM va toan bo phan freshness monitoring mat y nghia.

    `created` la thoi diem ban ghi thuc su duoc nap vao Crossref - luon o qua khu.
    Lay min cua hai gia tri cho ra ngay som nhat ma paper thuc su ton tai.
    """
    candidates = [value for value in (issued, created) if value]
    return min(candidates) if candidates else ""


def _parse_authors(node: Any) -> list[str]:
    authors: list[str] = []
    for entry in node or []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or f"{entry.get('given', '')} {entry.get('family', '')}"
        name = normalize_whitespace(str(name))
        if name:
            authors.append(name)
    return authors


def _parse_categories(node: Any) -> list[str]:
    categories: list[str] = []
    for entry in node or []:
        value = normalize_whitespace(str(entry))
        if value:
            categories.append(value)
    return categories


def _parse_pdf_url(node: Any) -> str:
    for link in node or []:
        if isinstance(link, dict) and link.get("content-type") == "application/pdf":
            return str(link.get("URL") or "")
    return ""


def parse_crossref_payload(payload: dict, max_age_days: int | None = None) -> list[PaperRecord]:
    """Parse Crossref payload thanh list PaperRecord theo Contract A.

    Bo record thieu DOI, thieu title, abstract qua ngan hoac khong parse duoc ngay xuat ban -
    day la nhung record khong the lam document RAG tu te.

    `max_age_days` ap lai cua so tuoi tren ngay HIEU LUC. Can buoc nay vi filter
    `from-pub-date` cua Crossref ap tren `issued`, con ta dung min(issued, created);
    mot so ban ghi lot qua filter nguon nhung ngay hieu luc lai nam ngoai cua so.
    Khong ap lai thi baseline se co dong stale ngay tu dau va tin hieu freshness
    khong con phan biet duoc baseline voi corrupted.
    """
    items = (payload or {}).get("message", {}).get("items", [])
    today = date.today()
    records: list[PaperRecord] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        paper_id = normalize_whitespace(str(item.get("DOI") or "")).lower()
        title = _first_string(item.get("title"))
        summary = _clean_abstract(item.get("abstract"))
        published = _effective_published(
            _date_from_parts(item.get("issued")), _date_from_parts(item.get("created"))
        )

        if not paper_id or not title or len(summary) < MIN_SUMMARY_CHARS or not published:
            continue

        if max_age_days is not None:
            age_days = (today - date.fromisoformat(published)).days
            if age_days > max_age_days:
                continue

        categories = _parse_categories(item.get("subject"))
        records.append(
            PaperRecord(
                paper_id=paper_id,
                title=title,
                summary=summary,
                authors=_parse_authors(item.get("author")),
                categories=categories,
                primary_category=categories[0] if categories else "uncategorized",
                published=published,
                updated=_date_from_parts(item.get("deposited")) or _date_from_parts(item.get("created")),
                abs_url=str(item.get("URL") or ""),
                pdf_url=_parse_pdf_url(item.get("link")),
                comment=_first_string(item.get("container-title")) or _clean_text(item.get("type")),
            )
        )

    return records


def _request_with_retry(params: dict[str, Any]) -> dict:
    """Goi Crossref voi exponential backoff cho 429/5xx va loi mang."""
    headers = {"User-Agent": _user_agent(), "Accept": "application/json"}
    last_error = ""

    for attempt in range(MAX_ATTEMPTS):
        try:
            response = requests.get(
                CROSSREF_API_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT
            )
        except requests.RequestException as exc:
            last_error = f"network error: {exc}"
        else:
            if response.status_code == 200:
                return response.json()
            last_error = f"HTTP {response.status_code}"
            if response.status_code not in RETRYABLE_STATUS:
                raise RuntimeError(f"Crossref request failed permanently: {last_error}")
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                time.sleep(min(int(retry_after), 30))
                continue

        if attempt < MAX_ATTEMPTS - 1:
            backoff = 2**attempt
            print(f"[crossref] {last_error} - thu lai sau {backoff}s ({attempt + 1}/{MAX_ATTEMPTS})")
            time.sleep(backoff)

    raise RuntimeError(f"Crossref request failed after {MAX_ATTEMPTS} attempts: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Goi Crossref, luu raw response, parse va luu raw records snapshot."""
    params = {
        "query.bibliographic": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        # Sort theo do lien quan chu KHONG theo ngay: `sort=published` chi lay cac ban ghi
        # co `issued` xa nhat o tuong lai, cho ra corpus khong dinh dang gi toi query.
        # Do tuoi cua corpus da duoc dam bao boi filter `from-pub-date` trong settings.
        "sort": "relevance",
        "order": "desc",
        "select": ",".join(
            [
                "DOI",
                "title",
                "abstract",
                "author",
                "subject",
                "created",
                "issued",
                "deposited",
                "URL",
                "link",
                "type",
                "container-title",
            ]
        ),
    }

    print(f"[crossref] GET {CROSSREF_API_URL} rows={settings.max_results} filter={settings.source_filter}")
    payload = _request_with_retry(params)

    # Luu raw response TRUOC khi parse: day la bang chung lineage, khong bao gio bi ghi de boi parser.
    write_json(settings.paths.raw_api_response, payload)

    records = parse_crossref_payload(payload, max_age_days=settings.freshness_threshold_days)
    received = len(payload.get("message", {}).get("items", []))
    total = (payload or {}).get("message", {}).get("total-results")
    print(
        f"[crossref] nhan {received} item, giu {len(records)} record hop le "
        f"(total-results={total}, cua so tuoi <= {settings.freshness_threshold_days} ngay)"
    )

    if not records:
        raise RuntimeError(
            "Crossref khong tra ve record nao hop le. Kiem tra source_query/source_filter trong core/config.py."
        )

    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    return records


def _record_from_dict(item: dict[str, Any]) -> PaperRecord:
    """Map dict -> PaperRecord, bo qua field thua va dien mac dinh cho field thieu."""
    values: dict[str, Any] = {}
    for field in fields(PaperRecord):
        raw = item.get(field.name)
        if field.name in {"authors", "categories"}:
            values[field.name] = list(raw) if isinstance(raw, list) else []
        else:
            values[field.name] = "" if raw is None else str(raw)
    return PaperRecord(**values)


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Doc JSON snapshot va map thanh PaperRecord. Dung cho ca baseline lan repair."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Khong tim thay raw records tai {path}. Chay lai phase1 hoac dat REFRESH_SOURCE=1."
        )
    payload = read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"Raw records phai la JSON array, nhan duoc {type(payload).__name__}: {path}")
    return [_record_from_dict(item) for item in payload if isinstance(item, dict)]
