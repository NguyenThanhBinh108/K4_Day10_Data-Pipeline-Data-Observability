from __future__ import annotations

from typing import Any

import pandas as pd

from pathlib import Path

from core.utils import ensure_parent, first_sentence, write_json

MIN_QUESTIONS = 20
MAX_QUESTIONS = 32
MIN_NEWEST = 2

QUESTION_TYPES = ["summary", "authors", "date", "categories"]

_QUESTION_TEMPLATES = {
    "summary": "Give a one-sentence summary of the paper '{title}'.",
    "authors": "Who authored the paper '{title}'?",
    "date": "When was the paper '{title}' published?",
    "categories": "What categories does the paper '{title}' belong to?",
}

_GROUND_TRUTH_FIELDS = {
    "summary": "summary",
    "authors": "authors_joined",
    "date": "published",
    "categories": "categories_joined",
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
    """TODO(student): tao bo evaluation set tu cleaned dataframe.

    Pseudo-code:
    1. Kiem tra so luong document toi thieu.
    2. Chon mot so paper dai dien (cam bao >= 2 paper moi nhat).
    3. Tao nhieu loai cau hoi: summary, authors, date, categories.
    4. Moi row chua: id, question_type, question, ground_truth, ground_truth_doc_ids.
    5. Ghi file JSON vao output_path.
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
