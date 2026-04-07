"""
classifiers/course_predictor.py -- Stage 2: predict which course folder.

Strategy:
  1. Regex-first: if the filename contains an exact course code (CS180, MATH101...),
     assign confidence 0.95. This is the most reliable cold-start signal.
  2. TF-IDF cosine similarity against known course names and accumulated
     text tokens from past moves (built from training_samples).
  3. LR overlay: once enough per-course samples exist, blend with a
     trained multinomial LR.

Confidence:
  - Exact regex match -> 0.95  (+ reason: "Matched course code CS180 in filename")
  - Cosine similarity -> scaled to [0.50, 0.90] range
  - LR prob           -> raw probability from predict_proba
  - Final             -> max(regex, cosine, lr_prob)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.extractor import FileFeatures

MIN_SAMPLES_FOR_LR = 15

COURSE_CODE_RE = re.compile(r'\b([A-Z]{2,4})\s?(\d{3,4})\b', re.IGNORECASE)


def _extract_course_codes(text: str) -> list[str]:
    """Return all course codes found in `text`, normalized (e.g. 'CS180')."""
    matches = COURSE_CODE_RE.findall(text)
    return [f"{dept.upper()}{num}" for dept, num in matches]


class CoursePredictor:
    """
    Predicts the most likely course folder for a school-related file.

    Known courses are loaded from the CourseFolderRepo at startup and
    whenever the user rescans their School root.
    """

    def __init__(self) -> None:
        self._known_courses: list[str] = []   # e.g. ["CS145", "CS180", "MATH101"]
        self._pipeline = None                  # sklearn Pipeline for LR overlay
        self._tfidf_matrix = None              # precomputed course name vectors
        self._tfidf_vectorizer = None

    def set_known_courses(self, courses: list[str]) -> None:
        """Update the list of known course names from the DB / folder scan."""
        self._known_courses = [c.upper() for c in courses]
        # Rebuild the TF-IDF index over course names for cosine fallback.
        self._rebuild_name_index()

    def _rebuild_name_index(self) -> None:
        """Build a TF-IDF matrix over known course names for cosine similarity lookup."""
        if not self._known_courses:
            self._tfidf_vectorizer = None
            self._tfidf_matrix = None
            return
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
            import numpy as np  # type: ignore
            # Represent each course as a bag of its name's characters/tokens.
            # This helps fuzzy-match "cs 180" -> "CS180".
            vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
            matrix = vectorizer.fit_transform(self._known_courses)
            self._tfidf_vectorizer = vectorizer
            self._tfidf_matrix = matrix
        except Exception:
            self._tfidf_vectorizer = None
            self._tfidf_matrix = None

    def predict(self, features: "FileFeatures") -> tuple[str, float, str]:
        """
        Returns (course_name, confidence, reason).
        Returns ("Unknown", 0.0, reason) if no course can be predicted.
        """
        if not self._known_courses:
            return "Unknown", 0.0, "No course folders configured"

        text = features.all_text
        all_text_upper = text.upper()

        # --- Stage A: Exact regex match ---
        codes_in_text = _extract_course_codes(text)
        for code in codes_in_text:
            if code in self._known_courses:
                return code, 0.95, f"Matched course code {code} in filename"
        # Partial match: code prefix matches a known course
        for code in codes_in_text:
            for known in self._known_courses:
                if code in known or known in code:
                    return known, 0.88, f"Partial course code match: {code} ~ {known}"

        # --- Stage B: Cosine similarity over course names ---
        cosine_result = self._cosine_predict(text)
        if cosine_result:
            course, sim = cosine_result
            conf = 0.50 + sim * 0.40   # scale [0, 1] -> [0.50, 0.90]
            reason = f"Name similarity to {course} ({sim:.0%})"
        else:
            course = self._known_courses[0]
            conf = 0.30
            reason = "No strong course signal; defaulting to first known course"

        # --- Stage C: LR overlay ---
        if self._pipeline is not None:
            try:
                probs = self._pipeline.predict_proba([text])[0]
                classes = self._pipeline.classes_
                best_idx = int(probs.argmax())
                lr_course = classes[best_idx]
                lr_prob = float(probs[best_idx])
                if lr_prob > conf:
                    course = lr_course
                    conf = lr_prob
                    reason = f"Model confidence {lr_prob:.0%} for {lr_course}"
            except Exception:
                pass

        return course, min(conf, 0.98), reason

    def _cosine_predict(self, text: str) -> tuple[str, float] | None:
        """Return (best_course_name, similarity_score) or None."""
        if self._tfidf_vectorizer is None or self._tfidf_matrix is None:
            return None
        try:
            import numpy as np  # type: ignore
            from sklearn.metrics.pairwise import cosine_similarity  # type: ignore
            vec = self._tfidf_vectorizer.transform([text.upper()])
            sims = cosine_similarity(vec, self._tfidf_matrix)[0]
            best_idx = int(sims.argmax())
            best_sim = float(sims[best_idx])
            if best_sim < 0.01:
                return None
            return self._known_courses[best_idx], best_sim
        except Exception:
            return None

    def retrain(self, samples: list[dict]) -> None:
        """Retrain the LR overlay on school-labeled samples that have a course label."""
        import json
        school_samples = [
            s for s in samples
            if int(s.get("label_school", 0)) == 1 and s.get("label_course")
        ]
        if len(school_samples) < MIN_SAMPLES_FOR_LR:
            return

        from sklearn.pipeline import Pipeline  # type: ignore
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
        from sklearn.linear_model import LogisticRegression  # type: ignore

        texts, labels = [], []
        for s in school_samples:
            raw = s.get("text_features", "")
            try:
                t = json.loads(raw) if isinstance(raw, str) else str(raw)
            except Exception:
                t = str(raw)
            texts.append(str(t))
            labels.append(s["label_course"])

        if len(set(labels)) < 2:
            return  # can't train a multi-class model with one class

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                max_features=1000,
                ngram_range=(1, 2),
                sublinear_tf=True,
            )),
            ("lr", LogisticRegression(
                C=1.0,
                max_iter=300,
                class_weight="balanced",
                solver="lbfgs",
                multi_class="multinomial",
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
            self._pipeline = None
