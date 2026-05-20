"""
tests/test_classifiers.py -- Unit tests for the school detector and subject predictor.
"""

from pathlib import Path
from typing import List

from classifiers.school_detector import SchoolDetector
from classifiers.subject_predictor import SubjectPredictor
from core.extractor import FileFeatures, extract_folder_features


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


class TestFolderFeatureExtraction:
    def test_folder_name_used_as_stem(self, tmp_path: Path):
        folder = tmp_path / "speech_project"
        folder.mkdir()
        features = extract_folder_features(str(folder))
        assert features.filename == "speech_project"
        assert features.stem == "speech_project"
        assert features.ext == ""

    def test_contained_filenames_in_members(self, tmp_path: Path):
        folder = tmp_path / "sts_project"
        folder.mkdir()
        (folder / "sts_notes.txt").write_text("science technology society")
        (folder / "reaction_paper.docx").write_bytes(b"")

        features = extract_folder_features(str(folder))
        assert "sts_notes.txt" in features.zip_members
        assert "reaction_paper.docx" in features.zip_members

    def test_text_extracted_from_txt_files(self, tmp_path: Path):
        folder = tmp_path / "arts_folder"
        folder.mkdir()
        (folder / "arts_notes.txt").write_text("art history color theory portfolio")

        features = extract_folder_features(str(folder))
        assert "art history" in features.text

    def test_all_text_includes_folder_name_and_members(self, tmp_path: Path):
        folder = tmp_path / "speech_hw"
        folder.mkdir()
        (folder / "debate_script.txt").write_text("oral communication delivery")

        features = extract_folder_features(str(folder))
        all_text = features.all_text.lower()
        assert "speech" in all_text           # from folder stem
        assert "debate script" in all_text    # from zip_members via all_text

    def test_empty_folder_does_not_crash(self, tmp_path: Path):
        folder = tmp_path / "empty"
        folder.mkdir()
        features = extract_folder_features(str(folder))
        assert features.filename == "empty"
        assert features.size_bytes == 0
        assert features.zip_members == []

    def test_folder_classified_by_subject_predictor(self, tmp_path: Path):
        folder = tmp_path / "STS_module3"
        folder.mkdir()
        (folder / "reading.txt").write_text("science technology society ethics")

        pred = SubjectPredictor()
        pred.set_known_subjects(["Speech", "STS", "Arts"])
        features = extract_folder_features(str(folder))
        subject, conf, _ = pred.predict(features)
        assert subject == "STS"
