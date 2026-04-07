"""
classifiers/category_predictor.py -- Stage 3: predict category subfolder.

Fixed labels (v1): Lectures | Labs | Exercises | Assignments | References | Others

Strategy:
  1. Keyword rule table -- most reliable for demos (cold-start strength 0.90).
  2. LR overlay once >= MIN_SAMPLES_FOR_LR samples exist.
  3. Final confidence = max(keyword_conf, lr_prob).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.extractor import FileFeatures

MIN_SAMPLES_FOR_LR = 10

# Fixed category labels -- never extend this in v1.
CATEGORIES = ["Lectures", "Labs", "Exercises", "Assignments", "References", "Others"]

# Keyword -> category mapping.
# Earlier entries win on first match, so order matters.
# Each entry: (category, strong_keywords, weak_keywords)
RULES: list[tuple[str, list[str], list[str]]] = [
    (
        "Assignments",
        ["assignment", "homework", "hw", "problem set", "pset", "deliverable",
         "submission", "project report", "lab report"],
        ["submit", "due", "deadline"],
    ),
    (
        "Labs",
        ["lab", "laboratory", "lab exercise", "lab activity", "labwork"],
        ["experiment", "hands-on", "practical"],
    ),
    (
        "Exercises",
        ["exercise", "drill", "practice problem", "worksheet", "activity"],
        ["practice", "drill"],
    ),
    (
        "Lectures",
        ["lecture", "lec", "lesson", "slides", "powerpoint", "ppt",
         "class notes", "note", "module", "week"],
        ["chapter", "topic", "session"],
    ),
    (
        "References",
        ["reference", "textbook", "reading", "appendix", "bibliography",
         "manual", "guide", "handbook", "cheat sheet", "formula sheet"],
        ["book", "resource", "material"],
    ),
]

# Number pattern hints: "lab 3", "hw 2", "exercise 1" etc.
_LAB_NUM_RE = re.compile(r'\blab\s*\d', re.IGNORECASE)
_HW_NUM_RE  = re.compile(r'\b(hw|homework|assignment|pset)\s*\d', re.IGNORECASE)
_LEC_NUM_RE = re.compile(r'\b(lec|lecture)\s*\d', re.IGNORECASE)
_EX_NUM_RE  = re.compile(r'\b(ex|exercise)\s*\d', re.IGNORECASE)


def _keyword_predict(text: str) -> tuple[str, float, str]:
    """
    Apply rule table to `text`.
    Returns (category, confidence, reason).
    """
    text_lower = text.lower()

    # Quick regex shortcuts -- very high confidence
    if _LAB_NUM_RE.search(text):
        return "Labs", 0.92, "Found numbered lab pattern in filename"
    if _HW_NUM_RE.search(text):
        return "Assignments", 0.92, "Found numbered assignment/HW pattern"
    if _LEC_NUM_RE.search(text):
        return "Lectures", 0.92, "Found numbered lecture pattern"
    if _EX_NUM_RE.search(text):
        return "Exercises", 0.92, "Found numbered exercise pattern"

    # Rule table scan
    for category, strong, weak in RULES:
        strong_hits = [kw for kw in strong if kw in text_lower]
        if strong_hits:
            conf = min(0.88 + 0.02 * len(strong_hits), 0.95)
            return category, conf, f"Found keyword '{strong_hits[0]}' -> {category}"
        weak_hits = [kw for kw in weak if kw in text_lower]
        if len(weak_hits) >= 2:
            return category, 0.60, f"Weak hints suggest {category}: {', '.join(weak_hits[:2])}"

    return "Others", 0.40, "No category keyword found; defaulting to Others"


class CategoryPredictor:
    """
    Predicts the category subfolder for a school-related file.
    Uses fixed labels: Lectures, Labs, Exercises, Assignments, References, Others.
    """

    def __init__(self) -> None:
        self._pipeline = None  # sklearn Pipeline

    def predict(self, features: "FileFeatures") -> tuple[str, float, str]:
        """Returns (category, confidence, reason)."""
        text = features.all_text
        kw_category, kw_conf, kw_reason = _keyword_predict(text)

        lr_category = kw_category
        lr_prob = 0.0
        if self._pipeline is not None:
            try:
                probs = self._pipeline.predict_proba([text])[0]
                classes = self._pipeline.classes_
                best_idx = int(probs.argmax())
                lr_category = classes[best_idx]
                lr_prob = float(probs[best_idx])
            except Exception:
                pass

        if lr_prob > kw_conf:
            return lr_category, lr_prob, f"Model confidence {lr_prob:.0%} for {lr_category}"

        return kw_category, kw_conf, kw_reason

    def retrain(self, samples: list[dict]) -> None:
        """Retrain on school-labeled samples that have a category label."""
        import json
        school_samples = [
            s for s in samples
            if int(s.get("label_school", 0)) == 1 and s.get("label_category")
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
            labels.append(s["label_category"])

        if len(set(labels)) < 2:
            return

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                max_features=800,
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
