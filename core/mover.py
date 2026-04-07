"""
core/mover.py — Safe file move operations with duplicate-name resolution and undo.

Rules:
- Never silently overwrite an existing file.
- If a naming conflict exists, append _1, _2, ... until the name is free.
- Log the original and destination paths BEFORE moving.
- Undo moves the file back to its original path (if possible).
"""

import os
import shutil
from pathlib import Path


def resolve_duplicate_name(dest_dir: str, filename: str) -> str:
    """
    Return a safe filename that does not collide with anything in dest_dir.

    If `filename` is free, it is returned unchanged.
    Otherwise, the stem gets _1, _2, ... appended until a free name is found.

    Example:
        resolve_duplicate_name("/dst", "report.pdf")
        → "report.pdf"         (if free)
        → "report_1.pdf"       (if report.pdf already exists)
        → "report_2.pdf"       (if report_1.pdf also exists)
    """
    dest_path = Path(dest_dir) / filename
    if not dest_path.exists():
        return filename

    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1
    while True:
        candidate = f"{stem}_{counter}{suffix}"
        if not (Path(dest_dir) / candidate).exists():
            return candidate
        counter += 1


def safe_move(src_path: str, dest_dir: str) -> str:
    """
    Move `src_path` into `dest_dir`, creating dest_dir if needed.
    Resolves duplicate filenames automatically.

    Returns the final destination path (as a string).

    Raises:
        FileNotFoundError — if src_path does not exist.
        OSError — if the move fails for any filesystem reason.
    """
    src = Path(src_path)
    if not src.exists():
        raise FileNotFoundError(f"Source file not found: {src_path}")

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    safe_name = resolve_duplicate_name(dest_dir, src.name)
    final_dest = dest / safe_name

    shutil.move(str(src), str(final_dest))
    return str(final_dest)


def undo_move(dest_path: str, original_path: str) -> bool:
    """
    Move a file back from dest_path to original_path (undo a previous safe_move).

    Returns True on success, False if the file is no longer at dest_path
    or if the original location is already occupied.
    """
    dest = Path(dest_path)
    original = Path(original_path)

    if not dest.exists():
        return False

    # If the original location is now occupied by something else, don't overwrite it.
    if original.exists():
        return False

    # Ensure the original directory still exists (it should, but be safe).
    original.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.move(str(dest), str(original))
        return True
    except OSError:
        return False
