"""
tests/test_repository.py -- Unit tests for storage/repository.py.
"""

import json
import sqlite3

import pytest

from storage.repository import (
    FileEventRepo,
    SettingsRepo,
    SubjectFolderRepo,
    TrainingSampleRepo,
)


class TestSettingsRepo:
    def test_get_default(self, db_conn: sqlite3.Connection):
        repo = SettingsRepo(db_conn)
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


class TestFileEventRepo:
    def test_insert_and_get_all(self, db_conn: sqlite3.Connection):
        repo = FileEventRepo(db_conn)
        event_id = repo.insert(
            filename="cs180_lab.pdf",
            original_path=r"C:\Users\test\Downloads\cs180_lab.pdf",
            stage="pending",
            school_confidence=0.9,
            subject_predicted="CS180",
            subject_confidence=0.95,
        )
        assert isinstance(event_id, int)
        rows = repo.get_all()
        assert len(rows) == 1
        assert rows[0]["filename"] == "cs180_lab.pdf"
        assert rows[0]["course_predicted"] == "CS180"

    def test_update(self, db_conn: sqlite3.Connection):
        repo = FileEventRepo(db_conn)
        event_id = repo.insert(
            filename="file.pdf",
            original_path=r"C:\Downloads\file.pdf",
            stage="pending",
        )
        repo.update(event_id, stage="moved", user_action="accepted")
        row = repo.get_by_id(event_id)
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
            label_subject="CS180",
            label_category=None,
            source="user_accept",
        )
        assert repo.count() == 1
        assert repo.count_school() == 1

    def test_count_for_subject(self, db_conn: sqlite3.Connection):
        repo = TrainingSampleRepo(db_conn)
        repo.insert("a.pdf", "{}", ".pdf", 100, 1, label_subject="CS180")
        repo.insert("b.pdf", "{}", ".pdf", 100, 1, label_subject="CS145")
        assert repo.count_for_subject("CS180") == 1
        assert repo.count_for_subject("CS145") == 1
        assert repo.count_for_subject("CS999") == 0


class TestSubjectFolderRepo:
    def test_upsert_and_get_all(self, db_conn: sqlite3.Connection):
        repo = SubjectFolderRepo(db_conn)
        repo.upsert("CS180", r"C:\School\CS180", ["Week 1"])
        rows = repo.get_all()
        assert len(rows) == 1
        assert rows[0]["course_name"] == "CS180"
        assert rows[0]["subfolders"] == ["Week 1"]

    def test_upsert_updates_existing(self, db_conn: sqlite3.Connection):
        repo = SubjectFolderRepo(db_conn)
        repo.upsert("CS180", r"C:\School\CS180", ["Week 1"])
        repo.upsert("CS180", r"C:\School\CS180", ["Week 1", "Week 2"])
        rows = repo.get_all()
        assert len(rows) == 1
        assert rows[0]["subfolders"] == ["Week 1", "Week 2"]

    def test_get_subject_names(self, db_conn: sqlite3.Connection):
        repo = SubjectFolderRepo(db_conn)
        repo.upsert("CS145", r"C:\School\CS145", [])
        repo.upsert("CS180", r"C:\School\CS180", [])
        names = repo.get_subject_names()
        assert names == ["CS145", "CS180"]

    def test_clear(self, db_conn: sqlite3.Connection):
        repo = SubjectFolderRepo(db_conn)
        repo.upsert("CS180", r"C:\School\CS180", [])
        repo.clear()
        assert repo.get_all() == []
