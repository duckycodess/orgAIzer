"""
scripts/seed_data.py -- Bootstrap training data from the user's School folder.

The refocused app treats each top-level folder in the School root as a subject:
  School/CS180/quiz1.pdf               -> subject=CS180
  School/Discrete Math/week2/notes.pdf -> subject=Discrete Math

Nested folders are still useful during seeding because their names are added to
the text features, but the label is always the top-level subject folder.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from storage.db import get_connection, get_db_path, init_schema
from storage.repository import SettingsRepo, TrainingSampleRepo

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".pptx", ".zip"}


def _build_text_tokens(subject_name: str, file_path: Path, subject_root: Path) -> str:
    relative_parent = file_path.parent.relative_to(subject_root)
    parent_tokens = " ".join(relative_parent.parts)
    stem_tokens = file_path.stem.replace("_", " ").replace("-", " ")
    return " ".join(token for token in [stem_tokens, parent_tokens, subject_name] if token)


def seed(school_root: str, conn, dry_run: bool = False) -> int:
    repo = TrainingSampleRepo(conn)
    root = Path(school_root)
    if not root.exists():
        print(f"ERROR: school root does not exist: {school_root}")
        return 0

    inserted = 0
    skipped = 0
    samples_preview: list[dict] = []

    for subject_dir in sorted(root.iterdir()):
        if not subject_dir.is_dir():
            continue
        subject_name = subject_dir.name

        for file_path in sorted(subject_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                skipped += 1
                continue

            text_tokens = _build_text_tokens(subject_name, file_path, subject_dir)
            sample = {
                "filename": file_path.name,
                "text_features": json.dumps(text_tokens),
                "extension": file_path.suffix.lower(),
                "file_size": 0,
                "label_school": 1,
                "label_subject": subject_name,
                "source": "bootstrap",
            }

            if not dry_run:
                repo.insert(
                    filename=sample["filename"],
                    text_features=sample["text_features"],
                    extension=sample["extension"],
                    file_size=sample["file_size"],
                    label_school=1,
                    label_subject=subject_name,
                    label_category=None,
                    source="bootstrap",
                )

            samples_preview.append(sample)
            inserted += 1

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Seed complete.")
    print(f"  Inserted: {inserted} samples")
    print(f"  Skipped (unsupported ext): {skipped}")
    print()

    if samples_preview:
        print("First 10 samples (sanity check):")
        print(f"{'Filename':<40} {'Subject'}")
        print("-" * 60)
        for sample in samples_preview[:10]:
            print(f"{sample['filename']:<40} {sample['label_subject']}")

    subject_counts = Counter(sample["label_subject"] for sample in samples_preview)
    print("\nPer-subject counts:")
    for subject, count in sorted(subject_counts.items()):
        print(f"  {subject}: {count}")

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

    school_root = args.school_root or SettingsRepo(conn).get("school_root", "")
    if not school_root:
        print("ERROR: No school root configured. Pass --school-root or set it in the app first.")
        sys.exit(1)

    seed(school_root, conn, dry_run=args.dry_run)
    conn.close()


if __name__ == "__main__":
    main()
