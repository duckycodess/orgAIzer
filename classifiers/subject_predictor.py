"""
classifiers/subject_predictor.py -- Predict which subject folder fits a file.

Strategy:
  1. Exact subject/code match in filename or content.
  2. Token overlap against known subject names.
  3. Character-level TF-IDF similarity fallback.
  4. Logistic Regression overlay once enough user-confirmed samples exist.

The predictor keeps the repo's original strength on course-code style subjects
such as "CS180", but also handles descriptive names like "Discrete Math".
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.extractor import FileFeatures

MIN_SAMPLES_FOR_LR = 15
COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,4})\s?(\d{3,4})\b", re.IGNORECASE)


def _normalize_compact(text: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", text.upper())


def _normalize_tokens(text: str) -> list[str]:
    return [tok for tok in re.split(r"[^A-Z0-9]+", text.upper()) if tok]


def _extract_course_codes(text: str) -> list[str]:
    matches = COURSE_CODE_RE.findall(text)
    return [f"{dept.upper()}{num}" for dept, num in matches]


class SubjectPredictor:
    """Predict the most likely subject folder for a school-related file."""

    def __init__(self) -> None:
        self._known_subjects: list[str] = []
        self._pipeline = None
        self._tfidf_matrix = None
        self._tfidf_vectorizer = None

    def set_known_subjects(self, subjects: list[str]) -> None:
        self._known_subjects = [s.strip() for s in subjects if s.strip()]
        self._rebuild_name_index()

    def set_known_courses(self, courses: list[str]) -> None:
        self.set_known_subjects(courses)

    def _rebuild_name_index(self) -> None:
        if not self._known_subjects:
            self._tfidf_vectorizer = None
            self._tfidf_matrix = None
            return
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore

            vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
            matrix = vectorizer.fit_transform([s.upper() for s in self._known_subjects])
            self._tfidf_vectorizer = vectorizer
            self._tfidf_matrix = matrix
        except Exception:
            self._tfidf_vectorizer = None
            self._tfidf_matrix = None

    def predict(self, features: "FileFeatures") -> tuple[str, float, str]:
        if not self._known_subjects:
            return "Unknown", 0.0, "No subject folders configured"

        text = features.all_text
        compact_text = _normalize_compact(text)
        token_set = set(_normalize_tokens(text))

        rule_match = self._rule_predict(compact_text, token_set, text)
        if rule_match is not None:
            subject, conf, reason = rule_match
        else:
            cosine_result = self._cosine_predict(text)
            if cosine_result:
                subject, sim = cosine_result
                conf = 0.50 + sim * 0.40
                reason = f"Name similarity to {subject} ({sim:.0%})"
            else:
                subject = self._known_subjects[0]
                conf = 0.30
                reason = "No strong subject signal; defaulting to first known subject"

        if self._pipeline is not None:
            try:
                probs = self._pipeline.predict_proba([text])[0]
                classes = self._pipeline.classes_
                best_idx = int(probs.argmax())
                lr_subject = str(classes[best_idx])
                lr_prob = float(probs[best_idx])
                if lr_prob > conf:
                    subject = lr_subject
                    conf = lr_prob
                    reason = f"Model confidence {lr_prob:.0%} for {lr_subject}"
            except Exception:
                pass

        return subject, min(conf, 0.98), reason

    def _rule_predict(
        self,
        compact_text: str,
        token_set: set[str],
        raw_text: str,
    ) -> tuple[str, float, str] | None:
        codes_in_text = _extract_course_codes(raw_text)
        subject_meta = []
        for subject in self._known_subjects:
            subject_compact = _normalize_compact(subject)
            subject_tokens = [tok for tok in _normalize_tokens(subject) if len(tok) > 1]
            subject_meta.append((subject, subject_compact, subject_tokens))

        for code in codes_in_text:
            for subject, subject_compact, _ in subject_meta:
                if code == subject_compact:
                    return subject, 0.96, f"Matched subject code {code}"
                if code and code in subject_compact:
                    return subject, 0.90, f"Matched subject code fragment {code}"

        for subject, subject_compact, subject_tokens in subject_meta:
            if subject_compact and subject_compact in compact_text:
                return subject, 0.93, f"Matched subject name {subject}"
            if len(subject_tokens) >= 2 and all(tok in token_set for tok in subject_tokens):
                return subject, 0.88, f"Matched subject keywords for {subject}"

        best_subject = None
        best_overlap = 0.0
        for subject, _, subject_tokens in subject_meta:
            if not subject_tokens:
                continue
            overlap = len(set(subject_tokens) & token_set) / len(set(subject_tokens))
            if overlap > best_overlap:
                best_overlap = overlap
                best_subject = subject

        if best_subject is not None and best_overlap >= 0.5:
            conf = 0.58 + best_overlap * 0.22
            return best_subject, conf, f"Subject keyword overlap with {best_subject}"

        return None

    def _cosine_predict(self, text: str) -> tuple[str, float] | None:
        if self._tfidf_vectorizer is None or self._tfidf_matrix is None:
            return None
        try:
            from sklearn.metrics.pairwise import cosine_similarity  # type: ignore

            vec = self._tfidf_vectorizer.transform([text.upper()])
            sims = cosine_similarity(vec, self._tfidf_matrix)[0]
            best_idx = int(sims.argmax())
            best_sim = float(sims[best_idx])
            if best_sim < 0.01:
                return None
            return self._known_subjects[best_idx], best_sim
        except Exception:
            return None

    def retrain(self, samples: list[dict]) -> None:
        import json

        school_samples = [
            s for s in samples
            if int(s.get("label_school", 0)) == 1 and (s.get("label_subject") or s.get("label_course"))
        ]
        if len(school_samples) < MIN_SAMPLES_FOR_LR:
            return

        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
        from sklearn.linear_model import LogisticRegression  # type: ignore
        from sklearn.pipeline import Pipeline  # type: ignore

        texts, labels = [], []
        for sample in school_samples:
            raw = sample.get("text_features", "")
            try:
                text = json.loads(raw) if isinstance(raw, str) else str(raw)
            except Exception:
                text = str(raw)
            texts.append(str(text))
            labels.append(sample.get("label_subject") or sample.get("label_course"))

        if len(set(labels)) < 2:
            return

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
