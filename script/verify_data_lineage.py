"""Bang chung lineage cho khoi data - deliverable CP2 va CP6 cua R1.

Chay doc lap, KHONG ghi gi vao data/, khong can chromadb hay LLM.

Tra loi ba cau hoi ma bao cao phai chung minh bang so lieu:
  1. Mot paper_id di xuyen suot raw response -> raw records -> clean -> index metadata?
  2. Corruption co lam dung nhung gi corruption_log khai bao?
  3. Repair tu raw co khoi phuc chinh xac baseline, hay chi che ket qua loi?

Cach dung:
    python script/verify_data_lineage.py                 # tu chon paper_id bi drop
    python script/verify_data_lineage.py 10.2118/234689-pa

Exit code 0 = moi bat bien deu dung. Khac 0 = co bat bien bi vi pham.
"""

from __future__ import annotations

import sys

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import load_raw_records

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> bool:
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f" - {detail}" if detail else ""))
    if not condition:
        failures.append(label)
    return condition


def load_clean(path) -> pd.DataFrame:
    df = pd.read_csv(path).fillna("")
    df["age_days"] = df["age_days"].astype(int)
    df["summary_chars"] = df["summary_chars"].astype(int)
    return df


def section(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def trace_one_paper(settings: Settings, paper_id: str, clean: pd.DataFrame) -> None:
    """Buoc 1 - mot paper_id phai xuat hien nguyen ven o ca 4 tang."""
    section(f"1. LINEAGE cua paper_id: {paper_id}")

    payload = read_json(settings.paths.raw_api_response)
    items = payload.get("message", {}).get("items", [])
    raw_item = next((i for i in items if str(i.get("DOI", "")).lower() == paper_id), None)
    check("co trong raw API response", raw_item is not None, f"{len(items)} item")

    records = load_raw_records(settings.paths.raw_records_json)
    record = next((r for r in records if r.paper_id == paper_id), None)
    check("co trong raw records snapshot", record is not None, f"{len(records)} record")

    row = clean[clean["paper_id"] == paper_id]
    check("co trong clean dataset", len(row) == 1, f"{len(clean)} dong")

    manifest = read_json(settings.paths.embeddings_json)
    documents = manifest.get("documents", [])
    document = next((d for d in documents if d["paper_id"] == paper_id), None)
    check("co trong embedding manifest", document is not None, f"{len(documents)} document")

    if record is None or len(row) != 1 or document is None:
        return

    row = row.iloc[0]
    print()
    print(f"  raw.title    : {record.title[:78]}")
    print(f"  clean.title  : {row['title'][:78]}")
    print(f"  index.title  : {document['metadata']['title'][:78]}")
    print(f"  raw.published: {record.published}   clean.published: {row['published']}   age_days: {row['age_days']}")
    print(f"  raw.authors  : {', '.join(record.authors)[:78]}")
    print(f"  clean.authors: {row['authors_joined'][:78]}")

    check("title giu nguyen qua 3 tang", record.title == row["title"] == document["metadata"]["title"])
    check("published giu nguyen qua 3 tang", record.published == row["published"] == document["metadata"]["published"])
    check("content cua index == text_for_embedding", document["content"] == row["text_for_embedding"])


def verify_corruption(settings: Settings, clean: pd.DataFrame) -> None:
    """Buoc 2 - corrupted dataset phai lech dung nhu corruption_log khai bao."""
    section("2. CORRUPTION co dung nhu log khai bao khong")

    corrupted = load_clean(settings.paths.corrupted_clean_csv)
    log = read_json(settings.paths.corruption_log)
    operations = {op["type"]: op for op in log["operations"]}

    check("baseline khong bi mutate", clean["paper_id"].is_unique, f"{len(clean)} dong, {clean['paper_id'].nunique()} paper_id")

    dropped = operations["drop_latest_records"]["paper_ids"]
    check(
        "drop_latest_records: cac paper_id da bien mat",
        not any(pid in set(corrupted["paper_id"]) for pid in dropped),
        f"{len(dropped)} paper_id",
    )

    blanked = operations["blank_summary"]["paper_ids"]
    blank_rows = corrupted[corrupted["paper_id"].isin(blanked)]
    check(
        "blank_summary: summary rong dung so dong",
        bool((blank_rows["summary"] == "").all()) and len(blank_rows) >= len(blanked),
        f"{len(blank_rows)} dong",
    )

    noised = operations["inject_noise"]["paper_ids"]
    noise_marker = operations["inject_noise"]["params"]["noise"].split()[0]
    noise_rows = corrupted[corrupted["paper_id"].isin(noised)]
    check(
        "inject_noise: summary chua noise marker",
        bool(noise_rows["summary"].str.contains(noise_marker, regex=False).all()),
        f"marker '{noise_marker}'",
    )

    truncated = operations["truncate_title"]["paper_ids"]
    keep = operations["truncate_title"]["params"]["keep_chars"]
    trunc_rows = corrupted[corrupted["paper_id"].isin(truncated)]
    check(
        "truncate_title: title bi cat con dung do dai",
        bool((trunc_rows["title"].str.len() <= keep).all()),
        f"<= {keep} ky tu",
    )

    staled = operations["stale_dates"]["paper_ids"]
    shift = operations["stale_dates"]["params"]["shift_days"]
    for paper_id in staled:
        before = clean[clean["paper_id"] == paper_id]
        after = corrupted[corrupted["paper_id"] == paper_id]
        if len(before) == 1 and len(after) >= 1:
            check(
                f"stale_dates: {paper_id} gia them {shift} ngay",
                int(after["age_days"].iloc[0]) - int(before["age_days"].iloc[0]) == shift,
                f"{before['age_days'].iloc[0]} -> {after['age_days'].iloc[0]}",
            )

    duplicated = operations["duplicate_rows"]["paper_ids"]
    check(
        "duplicate_rows: paper_id khong con unique",
        len(corrupted) - corrupted["paper_id"].nunique() == len(duplicated),
        f"{len(corrupted)} dong / {corrupted['paper_id'].nunique()} paper_id",
    )

    # Buoc de nhat bi quen: neu text_for_embedding khong duoc build lai thi embedding
    # van sach, metric khong doi, va ca bai lab khong chung minh duoc gi.
    rebuilt = corrupted[corrupted["paper_id"].isin(blanked + noised + truncated)]
    stale_ok = all(
        f"Summary: {row['summary']}" in row["text_for_embedding"] and row["title"] in row["text_for_embedding"]
        for _, row in rebuilt.iterrows()
    )
    check("text_for_embedding da duoc rebuild theo du lieu hong", stale_ok, f"{len(rebuilt)} dong")


def verify_repair(settings: Settings, clean: pd.DataFrame) -> None:
    """Buoc 3 - repair phai chay lai cleaning tu raw, khong phai copy baseline."""
    section("3. REPAIR tu raw co khoi phuc dung baseline khong")

    repaired = build_clean_dataframe(load_raw_records(settings.paths.raw_records_json), now_utc())

    check("cung so dong", len(repaired) == len(clean), f"{len(repaired)} vs {len(clean)}")
    check("cung tap paper_id", set(repaired["paper_id"]) == set(clean["paper_id"]))

    log = read_json(settings.paths.corruption_log)
    dropped = next(op for op in log["operations"] if op["type"] == "drop_latest_records")["paper_ids"]
    check(
        "cac paper_id bi drop luc corrupt da tro lai",
        all(pid in set(repaired["paper_id"]) for pid in dropped),
        ", ".join(dropped),
    )

    merged = clean.merge(repaired, on="paper_id", suffixes=("_base", "_rep"))
    for column in ("title", "summary", "published", "authors_joined", "text_for_embedding"):
        check(
            f"{column} trung khop tung ban ghi",
            bool((merged[f"{column}_base"] == merged[f"{column}_rep"]).all()),
            f"{len(merged)} ban ghi",
        )


def main() -> int:
    settings = load_settings()
    clean = load_clean(settings.paths.clean_csv)

    if len(sys.argv) > 1:
        paper_id = sys.argv[1].strip().lower()
    else:
        # Mac dinh chon mot paper bi corruption xoa han: chung minh duoc ca lineage lan repair.
        log = read_json(settings.paths.corruption_log)
        dropped = next(op for op in log["operations"] if op["type"] == "drop_latest_records")["paper_ids"]
        paper_id = dropped[0]

    print("=" * 78)
    print("VERIFY DATA LINEAGE - R1 (ingestion / cleaning / corruption)")
    print("=" * 78)

    trace_one_paper(settings, paper_id, clean)
    verify_corruption(settings, clean)
    verify_repair(settings, clean)

    section("KET LUAN")
    if failures:
        print(f"  {len(failures)} bat bien bi vi pham:")
        for item in failures:
            print(f"    - {item}")
        return 1
    print("  Tat ca bat bien deu dung. Lineage raw -> clean -> index nguyen ven,")
    print("  corruption dung nhu log, va repair khoi phuc chinh xac baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
