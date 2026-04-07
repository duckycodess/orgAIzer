"""
tests/test_repository.py — Unit tests for storage/repository.py.
"""

import json
import sqlite3

import pytest

from storage.repository import (
    CourseFolderRepo,
    FileEventRepo,
    SettingsRepo,
    TrainingSampleRepo,
)


class TestSettingsRepo:
    def test_get_default(self, db_conn: sqlite3.Connection):
        repo = SettingsRepo(db_conn)
        # Default inserted by init_schema
        assert repo.get("warmup_active") == "1"

    def test_set_and_get(self, db_conn: sqlite3.Connection):
        repo = SettingsRepo(db_conn)
        repo.set("my_key", "hello")
        assert repo.get("my_key") == "hello"

    def test_get_float(self, db_conn: sqlite3.Connection):
        repo = SettingsRepo(db_conn)
        assert repo.get_float("threshold_high") == pytest.approx(0.85)

    def test_get_int(self, db_conn: sqlite3.Connection):
        repo = SettingsRepo(db_conn)
        assert repo.get_int("warmup_labeled_count") == 0

    def test_get_bool_true(self, db_conn: sqlite3.Connection):
        repo = SettingsRepo(db_conn)
        assert repo.get_bool("warmup_active") is True

    def test_overwrite(self, db_conn: sqlite3.Connection):
        repo = SettingsRepo(db_conn)
        repo.set("key", "v1")
        repo.set("key", "v2")
        assert repo.get("key") == "v2"


class TestFileEventRepo:
    def test_insert_and_get_all(self, db_conn: sqlite3.Connection):
        repo = FileEventRepo(db_conn)
        eid = repo.insert(
            filename="cs180_lab.pdf",
            original_path=r"C:\Users\test\Downloads\cs180_lab.pdf",
            stage="pending",
            school_confidence=0.9,
            course_predicted="CS180",
            course_confidence=0.95,
            category_predicted="Labs",
            category_confidence=0.90,
        )
        assert isinstance(eid, int)
        rows = repo.get_all()
        assert len(rows) == 1
        assert rows[0]["filename"] == "cs180_lab.pdf"

    def test_update(self, db_conn: sqlite3.Connection):
        repo = FileEventRepo(db_conn)
        eid = repo.insert(
            filename="file.pdf",
            original_path=r"C:\Downloads\file.pdf",
            stage="pending",
        )
        repo.update(eid, stage="moved", user_action="accepted")
        row = repo.get_by_id(eid)
        assert row["stage"] == "moved"
        assert row["user_action"] == "accepted"

    def test_get_pending(self, db_conn: sqlite3.Connection):
        repo = FileEventRepo(db_conn)
        repo.insert("a.pdf", "/dl/a.pdf", stage="pending")
        repo.insert("b.pdf", "/dl/b.pdf", stage="moved")
        pending = repo.get_pending()
        assert len(pending) == 1
        assert pending[0]["filename"] == "a.pdf"


class TestTrainingSampleRepo:
    def test_insert_and_count(self, db_conn: sqlite3.Connection):
        repo = TrainingSampleRepo(db_conn)
        repo.insert(
            filename="cs180_hw1.pdf",
            text_features=json.dumps("CS180 homework assignment"),
            extension=".pdf",
            file_size=50000,
            label_school=1,
            label_course="CS180",
            label_category="Assignments",
            source="user_accept",
        )
        assert repo.count() == 1
        assert repo.count_school() == 1

    def test_count_for_course(self, db_conn: sqlite3.Connection):
        repo = TrainingSampleRepo(db_conn)
        repo.insert("a.pdf", "{}", ".pdf", 100, 1, "CS180", "Labs", "user_accept")
        repo.insert("b.pdf", "{}", ".pdf", 100, 1, "CS145", "Labs", "user_accept")
        assert repo.count_for_course("CS180") == 1
        assert repo.count_for_course("CS145") == 1
        assert repo.count_for_course("CS999") == 0


class TestCourseFolderRepo:
    def test_upsert_and_get_all(self, db_conn: sqlite3.Connection):
        repo = CourseFolderRepo(db_conn)
        repo.upsert("CS180", r"C:\School\CS180", ["Lectures", "Labs"])
        rows = repo.get_all()
        assert len(rows) == 1
        assert rows[0]["course_name"] == "CS180"
        assert rows[0]["subfolders"] == ["Lectures", "Labs"]

    def test_upsert_updates_existing(self, db_conn: sqlite3.Connection):
        repo = CourseFolderRepo(db_conn)
        repo.upsert("CS180", r"C:\School\CS180", ["Lectures"])
        repo.upsert("CS180", r"C:\School\CS180", ["Lectures", "Labs"])
        rows = repo.get_all()
        assert len(rows) == 1
        assert rows[0]["subfolders"] == ["Lectures", "Labs"]

    def test_get_course_names(self, db_conn: sqlite3.Connection):
        repo = CourseFolderRepo(db_conn)
        repo.upsert("CS145", r"C:\School\CS145", [])
        repo.upsert("CS180", r"C:\School\CS180", [])
        names = repo.get_course_names()
        assert names == ["CS145", "CS180"]

    def test_clear(self, db_conn: sqlite3.Connection):
        repo = CourseFolderRepo(db_conn)
        repo.upsert("CS180", r"C:\School\CS180", [])
        repo.clear()
        assert repo.get_all() == []
