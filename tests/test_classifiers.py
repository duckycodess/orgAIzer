"""
tests/test_classifiers.py -- Unit tests for the school detector and subject predictor.
"""

from typing import List

from classifiers.school_detector import SchoolDetector
from classifiers.subject_predictor import SubjectPredictor
from core.extractor import FileFeatures


def make_features(
    filename: str = "file.pdf",
    text: str = "",
    zip_members: List[str] | None = None,
) -> FileFeatures:
    path = f"C:/Downloads/{filename}"
    stem = filename.rsplit(".", 1)[0]
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    return FileFeatures(
        path=path,
        filename=filename,
        stem=stem,
        ext=ext.lower(),
        size_bytes=1000,
        text=text,
        zip_members=zip_members or [],
    )


class TestSchoolDetector:
    def setup_method(self):
        self.det = SchoolDetector()

    def test_course_code_in_filename(self):
        features = make_features("CS180_lab3.pdf")
        is_school, conf, _ = self.det.predict(features)
        assert is_school
        assert conf >= 0.85

    def test_homework_keyword(self):
        features = make_features("homework2.pdf", text="this is homework assignment")
        is_school, _, _ = self.det.predict(features)
        assert is_school

    def test_non_school_file(self):
        features = make_features("invoice_2026.pdf", text="payment due amount total receipt")
        is_school, _, _ = self.det.predict(features)
        assert not is_school

    def test_generic_filename_low_confidence(self):
        features = make_features("document.pdf", text="")
        _, conf, _ = self.det.predict(features)
        assert conf < 0.55


class TestSubjectPredictor:
    def setup_method(self):
        self.pred = SubjectPredictor()
        self.pred.set_known_subjects([
            "CS145",
            "CS180",
            "Discrete Math",
            "Operating Systems",
        ])

    def test_exact_code_in_filename(self):
        features = make_features("CS180_midterm.pdf")
        subject, conf, reason = self.pred.predict(features)
        assert subject == "CS180"
        assert conf >= 0.90
        assert "CS180" in reason

    def test_subject_name_in_text(self):
        features = make_features("notes.pdf", text="Operating Systems lecture on processes")
        subject, conf, _ = self.pred.predict(features)
        assert subject == "Operating Systems"
        assert conf >= 0.80

    def test_subject_token_overlap(self):
        features = make_features("worksheet.pdf", text="Discrete Math induction worksheet")
        subject, conf, _ = self.pred.predict(features)
        assert subject == "Discrete Math"
        assert conf >= 0.70

    def test_zip_member_names_as_signal(self):
        features = make_features(
            "project.zip",
            zip_members=["cs145_graph.py", "graph_notes.txt"],
        )
        subject, conf, _ = self.pred.predict(features)
        assert subject == "CS145"
        assert conf >= 0.70

    def test_no_subjects_configured(self):
        pred = SubjectPredictor()
        features = make_features("CS180_lab.pdf")
        subject, conf, _ = pred.predict(features)
        assert subject == "Unknown"
        assert conf == 0.0
