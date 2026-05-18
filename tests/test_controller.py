"""
tests/test_controller.py -- Tests for Controller.handle_mark_as_school()
"""

import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from app.controller import Controller


@pytest.fixture
def temp_models_dir():
    """Temporary directory for classifier models (empty, so classifiers use defaults)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_school_root():
    """Temporary directory for school root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def _create_controller_with_test_db(db_conn, temp_models_dir):
    """Create a Controller instance with test DB connection and models dir."""
    with mock.patch("app.controller.get_connection", return_value=db_conn):
        with mock.patch("app.controller.get_models_dir", return_value=temp_models_dir):
            controller = Controller()
    return controller


def test_mark_as_school_moves_file(db_conn, temp_models_dir, temp_school_root):
    """File exists → moved, training sample inserted, event updated."""
    controller = _create_controller_with_test_db(db_conn, temp_models_dir)
    controller._settings.school_root = temp_school_root

    # Create a test file
    test_file = Path(temp_school_root) / "test_download.pdf"
    test_file.write_text("course code: CS101")

    # Insert a not_school event with original_path pointing to the test file
    event_id = controller._event_repo.insert(
        filename="test_download.pdf",
        original_path=str(test_file),
        stage="not_school",
        school_confidence=0.1,
        subject_predicted=None,
        feature_text="course code: CS101",
        file_size=100,
    )

    # Call handle_mark_as_school
    dest_path = controller.handle_mark_as_school(event_id, "Computer Science")

    # Verify:
    # 1. File was moved
    assert dest_path is not None
    assert Path(dest_path).exists()
    assert not test_file.exists()

    # 2. Event was updated
    event = controller._event_repo.get_by_id(event_id)
    assert event["stage"] == "moved"
    assert event["user_action"] == "corrected_not_school"
    assert event["final_course"] == "Computer Science"
    assert event["destination_path"] == dest_path

    # 3. Training sample was inserted
    samples = controller._sample_repo.get_all()
    assert len(samples) == 1
    sample = samples[0]
    assert sample["label_school"] == 1
    assert sample["label_course"] == "Computer Science"
    assert sample["source"] == "user_mark_school"
    assert json.loads(sample["text_features"]) == "course code: CS101"


def test_mark_as_school_file_missing(db_conn, temp_models_dir, temp_school_root):
    """File missing → training sample still created, stage becomes skipped."""
    controller = _create_controller_with_test_db(db_conn, temp_models_dir)
    controller._settings.school_root = temp_school_root

    missing_file = Path(temp_school_root) / "missing.pdf"

    # Insert event with missing original file
    event_id = controller._event_repo.insert(
        filename="missing.pdf",
        original_path=str(missing_file),
        stage="not_school",
        school_confidence=0.1,
        feature_text="some text",
        file_size=50,
    )

    # Call handle_mark_as_school
    dest_path = controller.handle_mark_as_school(event_id, "Mathematics")

    # Verify:
    # 1. Returns None (move failed)
    assert dest_path is None

    # 2. Event was updated to skipped
    event = controller._event_repo.get_by_id(event_id)
    assert event["stage"] == "skipped"
    assert event["user_action"] == "corrected_not_school"
    assert event["final_course"] == "Mathematics"
    assert "File not found" in event["notes"]

    # 3. Training sample was still inserted
    samples = controller._sample_repo.get_all()
    assert len(samples) == 1
    sample = samples[0]
    assert sample["label_school"] == 1
    assert sample["label_course"] == "Mathematics"


def test_mark_as_school_no_school_root(db_conn, temp_models_dir):
    """No school root configured → training sample created, stage becomes skipped."""
    controller = _create_controller_with_test_db(db_conn, temp_models_dir)
    controller._settings.school_root = ""  # Empty school root

    # Insert event
    event_id = controller._event_repo.insert(
        filename="test.pdf",
        original_path="/tmp/test.pdf",
        stage="not_school",
        school_confidence=0.1,
        feature_text="test content",
        file_size=100,
    )

    dest_path = controller.handle_mark_as_school(event_id, "Physics")

    # Verify:
    # 1. Returns None (no school root)
    assert dest_path is None

    # 2. Event updated to skipped with note
    event = controller._event_repo.get_by_id(event_id)
    assert event["stage"] == "skipped"
    assert event["user_action"] == "corrected_not_school"
    assert "No school root" in event["notes"]

    # 3. Training sample still created
    samples = controller._sample_repo.get_all()
    assert len(samples) == 1
    assert samples[0]["label_school"] == 1


def test_mark_as_school_invalid_subject(db_conn, temp_models_dir):
    """Invalid subject (empty, path sep) → returns None, no DB changes."""
    controller = _create_controller_with_test_db(db_conn, temp_models_dir)
    controller._settings.school_root = "/tmp"

    event_id = controller._event_repo.insert(
        filename="test.pdf",
        original_path="/tmp/test.pdf",
        stage="not_school",
        school_confidence=0.1,
    )

    # Try with invalid subjects
    result = controller.handle_mark_as_school(event_id, "")
    assert result is None

    result = controller.handle_mark_as_school(event_id, "../etc/passwd")
    assert result is None

    result = controller.handle_mark_as_school(event_id, "folder/subdir")
    assert result is None

    # Verify no training samples were created
    assert controller._sample_repo.count() == 0

    # Event should still be not_school (unchanged)
    event = controller._event_repo.get_by_id(event_id)
    assert event["stage"] == "not_school"


def test_mark_as_school_wrong_stage(db_conn, temp_models_dir):
    """Event stage is not 'not_school' → guard prevents processing."""
    controller = _create_controller_with_test_db(db_conn, temp_models_dir)
    controller._settings.school_root = "/tmp"

    # Insert event with wrong stage
    event_id = controller._event_repo.insert(
        filename="test.pdf",
        original_path="/tmp/test.pdf",
        stage="pending",
        school_confidence=0.9,
    )

    result = controller.handle_mark_as_school(event_id, "Biology")
    assert result is None

    # Verify no training samples created
    assert controller._sample_repo.count() == 0

    # Event unchanged
    event = controller._event_repo.get_by_id(event_id)
    assert event["stage"] == "pending"


def test_mark_as_school_increments_counters(db_conn, temp_models_dir, temp_school_root):
    """Counters incremented: warmup_labeled_count, correction_counter."""
    controller = _create_controller_with_test_db(db_conn, temp_models_dir)
    controller._settings.school_root = temp_school_root
    initial_warmup = controller._settings.warmup_labeled_count
    initial_corrections = controller._settings.correction_counter

    # Create and move a file
    test_file = Path(temp_school_root) / "file.pdf"
    test_file.write_text("test")

    event_id = controller._event_repo.insert(
        filename="file.pdf",
        original_path=str(test_file),
        stage="not_school",
        school_confidence=0.1,
        feature_text="test",
    )

    controller.handle_mark_as_school(event_id, "History")

    # Verify counters incremented
    assert controller._settings.warmup_labeled_count == initial_warmup + 1
    assert controller._settings.correction_counter == initial_corrections + 1


def test_mark_as_school_subject_folder_registered(
    db_conn, temp_models_dir, temp_school_root
):
    """Subject folder created and registered even when file move succeeds."""
    controller = _create_controller_with_test_db(db_conn, temp_models_dir)
    controller._settings.school_root = temp_school_root

    # Create test file
    test_file = Path(temp_school_root) / "file.pdf"
    test_file.write_text("test")

    event_id = controller._event_repo.insert(
        filename="file.pdf",
        original_path=str(test_file),
        stage="not_school",
        school_confidence=0.1,
    )

    controller.handle_mark_as_school(event_id, "Chemistry")

    # Verify subject folder was registered
    subjects = controller.get_subject_names()
    assert "Chemistry" in subjects


def test_mark_as_school_missing_event(db_conn, temp_models_dir):
    """Event does not exist → returns None."""
    controller = _create_controller_with_test_db(db_conn, temp_models_dir)
    result = controller.handle_mark_as_school(99999, "Math")
    assert result is None


def test_mark_as_school_normalizes_subject(db_conn, temp_models_dir, temp_school_root):
    """Subject name normalized (whitespace collapsed)."""
    controller = _create_controller_with_test_db(db_conn, temp_models_dir)
    controller._settings.school_root = temp_school_root

    test_file = Path(temp_school_root) / "file.pdf"
    test_file.write_text("test")

    event_id = controller._event_repo.insert(
        filename="file.pdf",
        original_path=str(test_file),
        stage="not_school",
        school_confidence=0.1,
    )

    # Subject with extra whitespace
    controller.handle_mark_as_school(event_id, "  English   Language  ")

    # Event should have normalized subject
    event = controller._event_repo.get_by_id(event_id)
    assert event["final_course"] == "English Language"
