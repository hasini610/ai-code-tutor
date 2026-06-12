"""
Import and clean Kaggle LeetCode problems from leetcode_problems.csv.

Writes processed_problems.json with the top 50 Easy and top 50 Medium problems
(ranked by frequency), including placeholder test cases.
"""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
INPUT_CSV = PROJECT_ROOT / "leetcode_problems.csv"
OUTPUT_JSON = PROJECT_ROOT / "processed_problems.json"

PROBLEMS_PER_DIFFICULTY = 50
TARGET_DIFFICULTIES = ("Easy", "Medium")

# Common HTML / markdown artifacts in Kaggle exports
_HTML_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_EXCESS_WHITESPACE_RE = re.compile(r"[ \t]+\n")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def clean_description(text: object) -> str:
    """Strip HTML, markdown noise, and normalize whitespace."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""

    raw = str(text).strip()
    if not raw:
        return ""

    cleaned = unescape(raw)
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    cleaned = _MD_IMAGE_RE.sub("", cleaned)
    cleaned = _MD_LINK_RE.sub(r"\1", cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _EXCESS_WHITESPACE_RE.sub("\n", cleaned)
    cleaned = _MULTI_NEWLINE_RE.sub("\n\n", cleaned)
    return cleaned.strip()


def normalize_difficulty(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    label = str(value).strip().capitalize()
    if label in TARGET_DIFFICULTIES or label == "Hard":
        return label
    return None


def parse_frequency(value: object) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    try:
        return float(str(value).replace("%", "").strip())
    except ValueError:
        return 0.0


def pick_top_problems(df: pd.DataFrame, difficulty: str, limit: int) -> pd.DataFrame:
    subset = df[df["difficulty"] == difficulty].copy()
    subset = subset.sort_values(
        by=["frequency", "acceptance_rate", "id"],
        ascending=[False, False, True],
    )
    return subset.head(limit)


def row_to_problem(row: pd.Series) -> dict:
    problem_id = int(row["id"]) if pd.notna(row.get("id")) else None
    return {
        "id": problem_id,
        "title": str(row["title"]).strip() if pd.notna(row.get("title")) else "",
        "description": clean_description(row.get("description")),
        "difficulty": str(row["difficulty"]),
        "test_cases": [{"input": "", "expected_output": ""}],
    }


def load_and_prepare(csv_path: Path) -> pd.DataFrame:
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"Expected CSV at {csv_path}. Place leetcode_problems.csv in the project root."
        )

    df = pd.read_csv(csv_path, dtype=str, keep_default_na=True)
    df["id"] = pd.to_numeric(df.get("id"), errors="coerce")
    df["title"] = df.get("title", "").astype(str).str.strip()
    df["description"] = df.get("description", "")
    if "difficulty" not in df.columns:
        raise ValueError("CSV is missing required column: difficulty")
    df["difficulty"] = df["difficulty"].apply(normalize_difficulty)
    df["frequency"] = df["frequency"].map(parse_frequency) if "frequency" in df.columns else 0.0
    df["acceptance_rate"] = (
        df["acceptance_rate"].map(parse_frequency) if "acceptance_rate" in df.columns else 0.0
    )

    df = df.dropna(subset=["difficulty", "title"])
    df = df[df["title"].str.len() > 0]
    df = df[df["description"].astype(str).str.len() > 0]
    return df


def build_output(df: pd.DataFrame) -> dict:
    problems: list[dict] = []
    counts: dict[str, int] = {}

    for difficulty in TARGET_DIFFICULTIES:
        top = pick_top_problems(df, difficulty, PROBLEMS_PER_DIFFICULTY)
        counts[difficulty] = len(top)
        for _, row in top.iterrows():
            problems.append(row_to_problem(row))

    return {
        "source": INPUT_CSV.name,
        "total_problems": len(problems),
        "counts_by_difficulty": counts,
        "problems": problems,
    }


def main() -> None:
    df = load_and_prepare(INPUT_CSV)
    payload = build_output(df)

    with OUTPUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"Wrote {payload['total_problems']} problems to {OUTPUT_JSON}")
    for difficulty, count in payload["counts_by_difficulty"].items():
        print(f"  {difficulty}: {count}")


if __name__ == "__main__":
    main()
