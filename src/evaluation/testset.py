from __future__ import annotations

from typing import Any

import pandas as pd

from pathlib import Path

from core.utils import ensure_parent, first_sentence, write_json

MIN_QUESTIONS = 20
MAX_QUESTIONS = 32
MIN_NEWEST = 2

# KHONG them "categories" vao day — xem Contract C trong DATA_CONTRACT.md.
# Crossref tra `subject` rong 23/23 ban ghi nen `categories_joined` = "uncategorized"
# o MOI paper. Cau hoi loai nay se co ground_truth giong het nhau, va vi qa.py tra
# thang metadata["categories_joined"] nen token_f1 = 1.0 BAT KE retrieval tra ve paper
# nao. Do la diem cho khong: baseline bi thoi phong va corruption khong the lam nhom
# cau hoi do giam, che mat impact that.
QUESTION_TYPES = ["summary", "authors", "date"]

_QUESTION_TEMPLATES = {
    "summary": "Give a one-sentence summary of the paper '{title}'.",
    "authors": "Who authored the paper '{title}'?",
    "date": "When was the paper '{title}' published?",
}

_GROUND_TRUTH_FIELDS = {
    "summary": "summary",
    "authors": "authors_joined",
    "date": "published",
}


def _required_columns(df: pd.DataFrame) -> None:
    required = ["paper_id", "title", "summary", "authors_joined", "categories_joined", "published"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Clean dataframe missing required columns for test set: {missing}")


def _sort_newest_first(df: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(df["published"], utc=True, errors="coerce")
    sorted_df = df.copy()
    sorted_df["_published_dt"] = dates
    result = sorted_df.sort_values("_published_dt", ascending=False, na_position="last")
    return result.drop(columns=["_published_dt"]).reset_index(drop=True)


def _has_ground_truth(paper: dict[str, Any], question_type: str) -> bool:
    field = _GROUND_TRUTH_FIELDS[question_type]
    return bool(paper.get(field))


def _build_question(paper: dict[str, Any], question_type: str, index: int) -> dict[str, Any]:
    title = paper["title"]
    question = _QUESTION_TEMPLATES[question_type].format(title=title)

    if question_type == "summary":
        ground_truth = first_sentence(paper["summary"]) or paper["summary"]
    else:
        ground_truth = paper[_GROUND_TRUTH_FIELDS[question_type]]

    return {
        "id": f"eval_{question_type}_{index:02d}",
        "question_type": question_type,
        "question": question,
        "ground_truth": ground_truth,
        "ground_truth_doc_ids": [paper["paper_id"]],
    }


def _target_question_count(num_papers: int) -> int:
    if num_papers >= MIN_QUESTIONS:
        return min(num_papers, MAX_QUESTIONS)
    return MIN_QUESTIONS


def _validate_doc_ids(questions: list[dict[str, Any]], valid_ids: set[str]) -> None:
    for item in questions:
        for doc_id in item["ground_truth_doc_ids"]:
            if doc_id not in valid_ids:
                raise KeyError(f"Ground truth doc id not present in clean dataset: {doc_id}")


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Tao evaluation set tu cleaned dataframe theo Contract C.

    Duyet paper theo thu tu moi nhat truoc va xoay vong question_type, nen moi paper
    deu co it nhat mot cau hoi va cac paper moi nhat luon nam trong test set — dieu kien
    de corruption `drop_latest_records` do duoc impact len retrieval.

    Moi row: id, question_type, question, ground_truth, ground_truth_doc_ids.
    Cau hoi luon boc title trong nhay don de qa.py lookup exact duoc.

    Test set sinh MOT lan roi khoa: baseline, corrupted va repaired deu danh gia tren
    dung file nay, neu khong bang so sanh ba trang thai mat y nghia.
    """
    _required_columns(df)

    if len(df) < MIN_NEWEST + 1:
        raise ValueError(f"Too few papers to build a meaningful test set: {len(df)}.")

    ordered = _sort_newest_first(df)
    papers = ordered.to_dict(orient="records")
    valid_ids = set(df["paper_id"].astype(str))
    target = _target_question_count(len(papers))

    # Generate one question per paper, rotating question types so the corpus
    # covers summary/authors/date/categories. The newest papers (head of the
    # newest-first order) are always included, which lets the corruption flow
    # (drops latest records) show retrieval impact.
    questions: list[dict[str, Any]] = []
    extra_passes = 0
    while len(questions) < target and extra_passes < 2:
        paper_index = 0
        while paper_index < len(papers) and len(questions) < target:
            paper = papers[paper_index]
            offset = extra_passes * len(QUESTION_TYPES)
            question_type = QUESTION_TYPES[(paper_index + offset) % len(QUESTION_TYPES)]
            if _has_ground_truth(paper, question_type):
                questions.append(_build_question(paper, question_type, len(questions)))
            paper_index += 1
        extra_passes += 1

    if len(questions) < MIN_QUESTIONS:
        raise RuntimeError(
            f"Could not build at least {MIN_QUESTIONS} questions from the clean dataset "
            f"(only {len(questions)} available)."
        )

    _validate_doc_ids(questions, valid_ids)

    if output_path is not None:
        output = output_path if isinstance(output_path, Path) else Path(output_path)
        ensure_parent(output)
        write_json(output, questions)
    return questions
