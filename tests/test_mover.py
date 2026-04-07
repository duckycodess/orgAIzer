"""
tests/test_mover.py — Unit tests for core/mover.py.
"""

import pytest
from pathlib import Path

from core.mover import resolve_duplicate_name, safe_move, undo_move


class TestResolveDuplicateName:
    def test_no_conflict(self, tmp_dir: Path):
        assert resolve_duplicate_name(str(tmp_dir), "file.pdf") == "file.pdf"

    def test_one_conflict(self, tmp_dir: Path):
        (tmp_dir / "file.pdf").write_text("x")
        assert resolve_duplicate_name(str(tmp_dir), "file.pdf") == "file_1.pdf"

    def test_two_conflicts(self, tmp_dir: Path):
        (tmp_dir / "file.pdf").write_text("x")
        (tmp_dir / "file_1.pdf").write_text("x")
        assert resolve_duplicate_name(str(tmp_dir), "file.pdf") == "file_2.pdf"

    def test_no_extension(self, tmp_dir: Path):
        (tmp_dir / "notes").write_text("x")
        assert resolve_duplicate_name(str(tmp_dir), "notes") == "notes_1"


class TestSafeMove:
    def test_basic_move(self, tmp_dir: Path):
        src = tmp_dir / "src" / "report.pdf"
        src.parent.mkdir()
        src.write_text("content")
        dst_dir = tmp_dir / "dst"

        result = safe_move(str(src), str(dst_dir))

        assert Path(result).exists()
        assert Path(result).name == "report.pdf"
        assert not src.exists()

    def test_creates_dest_dir(self, tmp_dir: Path):
        src = tmp_dir / "file.txt"
        src.write_text("hello")
        dest_dir = tmp_dir / "deep" / "nested"

        safe_move(str(src), str(dest_dir))
        assert dest_dir.exists()

    def test_duplicate_resolution(self, tmp_dir: Path):
        src_a = tmp_dir / "report.pdf"
        src_b = tmp_dir / "src2" / "report.pdf"
        src_a.write_text("first")
        src_b.parent.mkdir()
        src_b.write_text("second")

        dst_dir = tmp_dir / "dst"
        safe_move(str(src_a), str(dst_dir))
        result = safe_move(str(src_b), str(dst_dir))

        assert Path(result).name == "report_1.pdf"

    def test_missing_source_raises(self, tmp_dir: Path):
        with pytest.raises(FileNotFoundError):
            safe_move(str(tmp_dir / "nonexistent.pdf"), str(tmp_dir / "dst"))


class TestUndoMove:
    def test_successful_undo(self, tmp_dir: Path):
        original = tmp_dir / "original" / "file.pdf"
        original.parent.mkdir()
        original.write_text("data")

        dst_dir = tmp_dir / "dst"
        dest = safe_move(str(original), str(dst_dir))

        assert not original.exists()
        assert undo_move(dest, str(original))
        assert original.exists()
        assert not Path(dest).exists()

    def test_undo_missing_file(self, tmp_dir: Path):
        assert not undo_move(str(tmp_dir / "missing.pdf"), str(tmp_dir / "orig.pdf"))

    def test_undo_blocked_by_existing_original(self, tmp_dir: Path):
        """If original path is already occupied, undo should refuse."""
        original = tmp_dir / "file.pdf"
        dest = tmp_dir / "dst" / "file.pdf"
        dest.parent.mkdir()
        dest.write_text("moved")
        original.write_text("already here")   # original slot is taken

        assert not undo_move(str(dest), str(original))
