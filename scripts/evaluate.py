"""
scripts/evaluate.py -- Evaluate trained models against a labeled folder.

Usage:
    python scripts/evaluate.py --split ~/val_School
    python scripts/evaluate.py --split ~/test_School
    python scripts/evaluate.py --split ~/test_School --save-cm

Each subfolder in the split is treated as a subject label.
NOT_SCHOOL (case-insensitive) is treated as label_school=0.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from classifiers.school_detector import SchoolDetector
from classifiers.subject_predictor import SubjectPredictor
from core.extractor import FileFeatures, extract_features
from storage.db import get_models_dir, get_connection, init_schema
from storage.repository import SubjectFolderRepo

SUPPORTED = {".pdf", ".docx", ".pptx", ".txt"}


def load_models() -> tuple[SchoolDetector, SubjectPredictor]:
    model_dir = get_models_dir()
    school_det = SchoolDetector()
    school_det.load_model(model_dir / "school_detector.pkl")

    subject_pred = SubjectPredictor()
    subject_model = model_dir / "subject_predictor.pkl"
    legacy = model_dir / "course_predictor.pkl"
    subject_pred.load_model(subject_model if subject_model.exists() else legacy)

    conn = get_connection()
    init_schema(conn)
    known = SubjectFolderRepo(conn).get_subject_names()
    conn.close()
    subject_pred.set_known_subjects(known)
    return school_det, subject_pred


def load_split(split_dir: Path) -> list[dict]:
    samples = []
    for subject_dir in sorted(split_dir.iterdir()):
        if not subject_dir.is_dir():
            continue
        subject = subject_dir.name
        is_not_school = subject.upper() == "NOT_SCHOOL"
        for f in sorted(subject_dir.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in SUPPORTED:
                continue
            samples.append({
                "path": str(f),
                "true_school": 0 if is_not_school else 1,
                "true_subject": None if is_not_school else subject,
            })
    return samples


def evaluate(split_dir: Path, save_cm: bool = False) -> None:
    print(f"\nLoading models…")
    school_det, subject_pred = load_models()

    print(f"Loading split from {split_dir}…")
    samples = load_split(split_dir)
    print(f"  {len(samples)} files found\n")

    if not samples:
        print("No supported files found.")
        return

    y_true_school, y_pred_school = [], []
    y_true_subj, y_pred_subj = [], []
    latency_by_ext: dict[str, list[float]] = {}

    for s in samples:
        t0 = time.perf_counter()
        try:
            features = extract_features(s["path"])
        except Exception as e:
            print(f"  SKIP {Path(s['path']).name}: {e}")
            continue
        elapsed_ms = (time.perf_counter() - t0) * 1000

        ext = Path(s["path"]).suffix.lower()
        latency_by_ext.setdefault(ext, []).append(elapsed_ms)

        is_school, school_conf, _ = school_det.predict(features)
        pred_school = 1 if is_school else 0
        y_true_school.append(s["true_school"])
        y_pred_school.append(pred_school)

        if s["true_subject"] is not None:
            pred_subj, _, _ = subject_pred.predict(features)
            y_true_subj.append(s["true_subject"])
            y_pred_subj.append(pred_subj)

    # ── School Detector ──────────────────────────────────────────────────
    from sklearn.metrics import classification_report, confusion_matrix, ConfusionMatrixDisplay

    print("=" * 60)
    print("SCHOOL DETECTOR")
    print("=" * 60)
    print(classification_report(
        y_true_school, y_pred_school,
        target_names=["Not-School", "School"], digits=4,
    ))

    if save_cm:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(5, 4))
        cm = confusion_matrix(y_true_school, y_pred_school)
        ConfusionMatrixDisplay(cm, display_labels=["Not-School", "School"]).plot(
            ax=ax, colorbar=False, cmap="Blues"
        )
        ax.set_title("School Detector – Confusion Matrix")
        plt.tight_layout()
        out = Path(f"cm_school_detector_{split_dir.name}.png")
        plt.savefig(out, dpi=150)
        plt.close()
        print(f"  Saved {out}")

    # ── Subject Predictor ────────────────────────────────────────────────
    if y_true_subj:
        print("=" * 60)
        print("SUBJECT PREDICTOR")
        print("=" * 60)
        labels = sorted(set(y_true_subj) | set(y_pred_subj))
        print(classification_report(y_true_subj, y_pred_subj, labels=labels, digits=4))

        if save_cm:
            fig, ax = plt.subplots(figsize=(8, 7))
            cm2 = confusion_matrix(y_true_subj, y_pred_subj, labels=labels)
            ConfusionMatrixDisplay(cm2, display_labels=labels).plot(
                ax=ax, colorbar=False, cmap="Blues", xticks_rotation=45
            )
            ax.set_title("Subject Predictor – Confusion Matrix")
            plt.tight_layout()
            out2 = Path(f"cm_subject_predictor_{split_dir.name}.png")
            plt.savefig(out2, dpi=150)
            plt.close()
            print(f"  Saved {out2}")

    # ── Latency ──────────────────────────────────────────────────────────
    print("=" * 60)
    print("LATENCY (feature extraction + classify)")
    print("=" * 60)
    for ext in sorted(latency_by_ext):
        times = latency_by_ext[ext]
        print(f"  {ext:6s}  avg={sum(times)/len(times):.1f}ms  "
              f"min={min(times):.1f}ms  max={max(times):.1f}ms  n={len(times)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", required=True, help="Path to val_School or test_School")
    parser.add_argument("--save-cm", action="store_true", help="Save confusion matrix images")
    args = parser.parse_args()

    evaluate(Path(args.split).expanduser(), save_cm=args.save_cm)


if __name__ == "__main__":
    main()
