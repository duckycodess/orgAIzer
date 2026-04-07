"""
tests/test_classifiers.py -- Unit tests for all three classifiers.

Tests focus on the keyword/rule layer (cold start behavior)
since that is what drives demo reliability.
"""

from dataclasses import dataclass
from typing import List

import pytest

from classifiers.school_detector import SchoolDetector
from classifiers.course_predictor import CoursePredictor
from classifiers.category_predictor import CategoryPredictor
from core.extractor import FileFeatures


def make_features(
    filename: str = "file.pdf",
    text: str = "",
    zip_members: List[str] | None = None,
) -> FileFeatures:
    p = f"C:/Downloads/{filename}"
    stem = filename.rsplit(".", 1)[0]
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    return FileFeatures(
        path=p,
        filename=filename,
        stem=stem,
        ext=ext.lower(),
        size_bytes=1000,
        text=text,
        zip_members=zip_members or [],
    )


# ---------------------------------------------------------------------------
# SchoolDetector
# ---------------------------------------------------------------------------

class TestSchoolDetector:
    def setup_method(self):
        self.det = SchoolDetector()

    def test_course_code_in_filename(self):
        f = make_features("CS180_lab3.pdf")
        is_school, conf, reason = self.det.predict(f)
        assert is_school
        assert conf >= 0.85

    def test_homework_keyword(self):
        f = make_features("homework2.pdf", text="this is homework assignment")
        is_school, conf, _ = self.det.predict(f)
        assert is_school

    def test_non_school_file(self):
        f = make_features("invoice_2026.pdf", text="payment due amount total receipt")
        is_school, conf, _ = self.det.predict(f)
        assert not is_school

    def test_generic_filename_low_confidence(self):
        f = make_features("document.pdf", text="")
        _, conf, _ = self.det.predict(f)
        assert conf < 0.55

    def test_syllabus_keyword(self):
        f = make_features("syllabus.pdf")
        is_school, conf, _ = self.det.predict(f)
        assert is_school


# ---------------------------------------------------------------------------
# CoursePredictor
# ---------------------------------------------------------------------------

class TestCoursePredictor:
    def setup_method(self):
        self.pred = CoursePredictor()
        self.pred.set_known_courses(["CS145", "CS180", "MATH101", "ENG202"])

    def test_exact_code_in_filename(self):
        f = make_features("CS180_midterm.pdf")
        course, conf, reason = self.pred.predict(f)
        assert course == "CS180"
        assert conf >= 0.90
        assert "CS180" in reason

    def test_different_course_code(self):
        f = make_features("MATH101_homework.pdf")
        course, conf, _ = self.pred.predict(f)
        assert course == "MATH101"

    def test_code_in_text(self):
        f = make_features("homework.pdf", text="CS145 Data Structures assignment")
        course, conf, _ = self.pred.predict(f)
        assert course == "CS145"

    def test_unknown_course_returns_low_confidence(self):
        f = make_features("generic_notes.pdf", text="introduction to something")
        course, conf, _ = self.pred.predict(f)
        # Should return something but with low confidence
        assert conf < 0.85

    def test_no_courses_configured(self):
        pred = CoursePredictor()  # no courses set
        f = make_features("CS180_lab.pdf")
        course, conf, _ = pred.predict(f)
        assert course == "Unknown"
        assert conf == 0.0


# ---------------------------------------------------------------------------
# CategoryPredictor
# ---------------------------------------------------------------------------

class TestCategoryPredictor:
    def setup_method(self):
        self.pred = CategoryPredictor()

    def test_lab_pattern(self):
        f = make_features("cs180_lab3.pdf")
        cat, conf, reason = self.pred.predict(f)
        assert cat == "Labs"
        assert conf >= 0.85

    def test_homework_pattern(self):
        f = make_features("hw2_solution.pdf")
        cat, conf, _ = self.pred.predict(f)
        assert cat == "Assignments"

    def test_lecture_slides(self):
        f = make_features("lec05_trees.pdf")
        cat, conf, _ = self.pred.predict(f)
        assert cat == "Lectures"

    def test_assignment_keyword_in_text(self):
        f = make_features("file.pdf", text="This is a graded assignment submission")
        cat, conf, _ = self.pred.predict(f)
        assert cat == "Assignments"

    def test_reference_keyword(self):
        f = make_features("textbook_chapter3.pdf")
        cat, conf, _ = self.pred.predict(f)
        assert cat == "References"

    def test_exercise_keyword(self):
        f = make_features("exercise_1.pdf")
        cat, conf, _ = self.pred.predict(f)
        assert cat == "Exercises"

    def test_fallback_to_others(self):
        f = make_features("random_document.pdf", text="")
        cat, conf, _ = self.pred.predict(f)
        assert cat == "Others"
        assert conf < 0.60

    def test_zip_member_names_as_signal(self):
        f = make_features("project.zip", zip_members=["hw3_main.py", "hw3_helper.py"])
        cat, conf, _ = self.pred.predict(f)
        assert cat == "Assignments"
