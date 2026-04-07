"""
scripts/seed_data.py -- Bootstrap training data from the user's School folder.

Walks the School root directory and treats the existing folder structure as
labeled ground truth:
  School/CS180/Labs/cs180_lab1.pdf  ->  school=1, course=CS180, category=Labs

This is the cold-start solution. Run once before the first demo to give
the ML models enough examples to produce meaningful probabilities.

Usage:
    python scripts/seed_data.py [--school-root PATH] [--db PATH] [--dry-run]

Output:
    Prints a summary of inserted samples and a sanity-check of the first 10.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Ensure the project root is on sys.path when running as a script.
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.db import get_connection, get_db_path, init_schema
from storage.repository import TrainingSampleRepo
from app.settings import CATEGORY_LABELS

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".pptx", ".zip"}

# Category folder names we recognize (case-insensitive partial match).
CATEGORY_ALIASES: dict[str, str] = {
    "lecture": "Lectures",
    "lectures": "Lectures",
    "lab": "Labs",
    "labs": "Labs",
    "exercise": "Exercises",
    "exercises": "Exercises",
    "assignment": "Assignments",
    "assignments": "Assignments",
    "homework": "Assignments",
    "hw": "Assignments",
    "reference": "References",
    "references": "References",
    "reading": "References",
    "others": "Others",
    "misc": "Others",
    "miscellaneous": "Others",
}


def normalize_category(folder_name: str) -> str:
    """Map a folder name to one of the fixed category labels."""
    key = folder_name.strip().lower()
    return CATEGORY_ALIASES.get(key, "Others")


def seed(school_root: str, conn, dry_run: bool = False) -> int:
    """
    Walk school_root and insert one training sample per supported file.
    Returns the number of samples inserted.
    """
    repo = TrainingSampleRepo(conn)
    root = Path(school_root)
    if not root.exists():
        print(f"ERROR: school root does not exist: {school_root}")
        return 0

    inserted = 0
    skipped = 0
    samples_preview: list[dict] = []

    # Walk: School/<COURSE>/<CATEGORY>/<file>
    for course_dir in sorted(root.iterdir()):
        if not course_dir.is_dir():
            continue
        course_name = course_dir.name  # e.g. "CS180"

        for cat_dir in sorted(course_dir.iterdir()):
            if not cat_dir.is_dir():
                continue
            category = normalize_category(cat_dir.name)  # e.g. "Labs"

            for file_path in sorted(cat_dir.iterdir()):
                if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    skipped += 1
                    continue

                stem = file_path.stem
                text_tokens = stem.replace("_", " ").replace("-", " ") + " " + cat_dir.name + " " + course_name

                sample = {
                    "filename": file_path.name,
                    "text_features": json.dumps(text_tokens),
                    "extension": file_path.suffix.lower(),
                    "file_size": 0,  # don't stat files for speed
                    "label_school": 1,
                    "label_course": course_name,
                    "label_category": category,
                    "source": "bootstrap",
                }

                if not dry_run:
                    repo.insert(
                        filename=sample["filename"],
                        text_features=sample["text_features"],
                        extension=sample["extension"],
                        file_size=sample["file_size"],
                        label_school=1,
                        label_course=course_name,
                        label_category=category,
                        source="bootstrap",
                    )

                samples_preview.append(sample)
                inserted += 1

    # Print sanity check
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Seed complete.")
    print(f"  Inserted: {inserted} samples")
    print(f"  Skipped (unsupported ext): {skipped}")
    print()

    if samples_preview:
        print("First 10 samples (sanity check):")
        print(f"{'Filename':<40} {'Course':<12} {'Category'}")
        print("-" * 75)
        for s in samples_preview[:10]:
            print(f"{s['filename']:<40} {s['label_course']:<12} {s['label_category']}")

    # Per-course and per-category summary
    from collections import Counter
    course_counts = Counter(s["label_course"] for s in samples_preview)
    cat_counts = Counter(s["label_category"] for s in samples_preview)
    print("\nPer-course counts:")
    for c, n in sorted(course_counts.items()):
        print(f"  {c}: {n}")
    print("\nPer-category counts:")
    for c, n in sorted(cat_counts.items()):
        print(f"  {c}: {n}")

    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed training data from School folder")
    parser.add_argument(
        "--school-root",
        default=None,
        help="Path to the School root directory (default: reads from DB settings)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to the SQLite database (default: system default)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be inserted without writing to the DB",
    )
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else get_db_path()
    conn = get_connection(db_path)
    init_schema(conn)

    from storage.repository import SettingsRepo
    school_root = args.school_root
    if not school_root:
        repo = SettingsRepo(conn)
        school_root = repo.get("school_root", "")

    if not school_root:
        print("ERROR: No school root configured. Pass --school-root or set it in the app first.")
        sys.exit(1)

    seed(school_root, conn, dry_run=args.dry_run)
    conn.close()


if __name__ == "__main__":
    main()
