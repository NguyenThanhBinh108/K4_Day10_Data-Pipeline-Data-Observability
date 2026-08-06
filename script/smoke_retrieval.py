from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.config import load_settings  # noqa: E402


def main() -> None:
    settings = load_settings(PROJECT_DIR)
    clean_path = settings.paths.clean_csv
    if not clean_path.exists():
        print(f"Clean CSV not found: {clean_path}")
        print("Wait for R1 to generate data/clean/papers_clean.csv, then run this script again.")
        return

    df = pd.read_csv(clean_path).fillna("")
    if df.empty:
        print(f"Clean CSV is empty: {clean_path}")
        return

    from retrieval.index import LocalEmbeddingIndex

    with tempfile.TemporaryDirectory(prefix="day10_smoke_retrieval_", ignore_cleanup_errors=True) as temp_dir:
        temp_root = Path(temp_dir)
        temp_paths = replace(
            settings.paths,
            chroma_dir=temp_root / "chroma",
            embeddings_json=temp_root / "smoke_embeddings.json",
        )
        smoke_settings = replace(settings, paths=temp_paths)
        index = LocalEmbeddingIndex.build(
            df=df,
            settings=smoke_settings,
            embeddings_output_path=temp_paths.embeddings_json,
        )

        first_row = df.iloc[0]
        title = str(first_row["title"])
        query = title or str(first_row["text_for_embedding"])[:120]

        print("Semantic search")
        results = index.search(query, top_k=1)
        if results:
            result = results[0]
            print(f"- paper_id: {result.paper_id}")
            print(f"- title: {result.title}")
            print(f"- score: {result.score:.4f}")
        else:
            print("- no semantic result")

        print("\nExact lookup")
        exact = index.lookup(title)
        if exact:
            print(f"- paper_id: {exact['paper_id']}")
            print(f"- title: {exact['title']}")
        else:
            print("- no exact lookup result")


if __name__ == "__main__":
    main()
