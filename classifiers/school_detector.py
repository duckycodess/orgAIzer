"""
classifiers/school_detector.py -- Stage 1: school-related vs not school-related.

Strategy (hybrid):
  1. Keyword rules give a fast, reliable cold-start baseline.
  2. A TF-IDF + Logistic Regression model overlays the keyword score once
     enough training samples exist (>= MIN_SAMPLES_FOR_LR).

Confidence:
  - Strong keyword hit -> 0.90
  - Weak keyword hint  -> 0.65
  - No keyword signal  -> 0.20 (possibly overridden by LR if available)
  - If LR is available: final_conf = max(keyword_conf, lr_prob)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.extractor import FileFeatures

# Require at least this many samples before trusting the LR model.
MIN_SAMPLES_FOR_LR = 10

# Regex that matches common course code patterns: CS180, MATH101, ENG202, etc.
COURSE_CODE_RE = re.compile(r'\b[A-Z]{2,4}\s?\d{3,4}\b', re.IGNORECASE)

# Strong school keywords (high weight)
STRONG_KEYWORDS = {
    "syllabus", "assignment", "homework", "hw", "midterm", "finals", "final exam",
    "lecture", "lab report", "laboratory", "problem set", "pset", "worksheet",
    "quiz", "exam", "project", "rubric", "grading", "course", "module",
    "chapter", "textbook", "reading", "discussion", "recitation",
}

# Weaker hints (lower weight; presence alone doesn't confirm school)
WEAK_KEYWORDS = {
    "notes", "slides", "pdf", "exercise", "tutorial", "study", "review",
    "handout", "paper", "report", "submission",
}


def _keyword_score(text: str) -> tuple[float, str]:
    """
    Return (confidence, reason) based on keyword/regex matching.

    The `text` argument should be features.all_text (stem + content + zip members).
    """
    text_lower = text.lower()

    # Course code regex is the strongest single signal.
    if COURSE_CODE_RE.search(text):
        return 0.90, f"Found course code pattern in filename/content"

    # Count strong keyword hits.
    strong_hits = [kw for kw in STRONG_KEYWORDS if kw in text_lower]
    if len(strong_hits) >= 2:
        return 0.90, f"Found school keywords: {', '.join(strong_hits[:3])}"
    if len(strong_hits) == 1:
        return 0.72, f"Found school keyword: {strong_hits[0]}"

    # Count weak keyword hits.
    weak_hits = [kw for kw in WEAK_KEYWORDS if kw in text_lower]
    if len(weak_hits) >= 2:
        return 0.55, f"Found possible school hints: {', '.join(weak_hits[:3])}"

    return 0.20, "No clear school signals found"


class SchoolDetector:
    """
    Classifies a file as school-related (True) or not (False),
    along with a confidence score and a human-readable reason.
    """

    def __init__(self) -> None:
        self._pipeline = None  # sklearn Pipeline (TF-IDF + LR), loaded lazily

    def predict(self, features: "FileFeatures") -> tuple[bool, float, str]:
        """
        Returns (is_school, confidence, reason).
        Confidence >= 0.55 is treated as school-related.
        """
        text = features.all_text
        keyword_conf, reason = _keyword_score(text)

        lr_prob = 0.0
        if self._pipeline is not None:
            try:
                probs = self._pipeline.predict_proba([text])[0]
                # Class order: [0=not_school, 1=school]
                lr_prob = float(probs[1])
            except Exception:
                lr_prob = 0.0

        final_conf = max(keyword_conf, lr_prob)

        # Update reason if LR is more confident than keywords
        if lr_prob > keyword_conf:
            reason = f"Model confidence {lr_prob:.0%} (keywords: {keyword_conf:.0%})"

        is_school = final_conf >= 0.55
        return is_school, final_conf, reason

    def retrain(self, samples: list[dict]) -> None:
        """
        Fit (or refit) the LR model on labeled training samples.
        samples: list of dicts with 'text_features' (str) and 'label_school' (int).
        No-op if fewer than MIN_SAMPLES_FOR_LR samples.
        """
        if len(samples) < MIN_SAMPLES_FOR_LR:
            return

        import json
        from sklearn.pipeline import Pipeline  # type: ignore
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
        from sklearn.linear_model import LogisticRegression  # type: ignore

        texts = []
        labels = []
        for s in samples:
            raw = s.get("text_features", "")
            try:
                t = json.loads(raw) if isinstance(raw, str) else str(raw)
            except Exception:
                t = str(raw)
            texts.append(str(t))
            labels.append(int(s["label_school"]))

        # Need at least one of each class to train.
        if len(set(labels)) < 2:
            return

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                max_features=500,
                ngram_range=(1, 2),
                sublinear_tf=True,
            )),
            ("lr", LogisticRegression(
                C=1.0,
                max_iter=200,
                class_weight="balanced",
                solver="lbfgs",
            )),
        ])
        pipeline.fit(texts, labels)
        self._pipeline = pipeline

    def save_model(self, path: Path) -> None:
        if self._pipeline is None:
            return
        import joblib  # type: ignore
        joblib.dump(self._pipeline, str(path))

    def load_model(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            import joblib  # type: ignore
            self._pipeline = joblib.load(str(path))
        except Exception:
            self._pipeline = None  # corrupt model — fall back to keywords
