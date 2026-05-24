# OrgAIzer Evaluation Results

## §3 Dataset Table

| Subject    | Total Files | Train (70%) | Test (30%) |
|------------|-------------|-------------|------------|
| ARTS       | 24          | 16          | 8          |
| CS138      | 15          | 11          | 4          |
| CS140      | 15          | 11          | 4          |
| CS145      | 17          | 11          | 6          |
| CS174      | 15          | 11          | 4          |
| CS180      | 15          | 11          | 4          |
| CS32       | 25          | 17          | 8          |
| CS33       | 24          | 16          | 8          |
| NOT_SCHOOL | 23          | 17          | 6          |
| SPEECH     | 17          | 11          | 6          |
| STS        | 22          | 16          | 6          |
| **Total**  | **212**     | **148**     | **64**     |

Split: stratified 70/30, seed=42.

---

## §3 Data Split Table

| Split     | Count | %    |
|-----------|-------|------|
| Train     | 148   | 69.8% |
| Test      | 64    | 30.2% |
| **Total** | **212** | 100% |

---

## §5 SchoolDetector Metrics

| Class        | Precision | Recall | F1     | Support |
|--------------|-----------|--------|--------|---------|
| Not-School   | 1.0000    | 0.4000 | 0.5714 | 5       |
| School       | 0.9483    | 1.0000 | 0.9735 | 55      |
| **Accuracy** |           |        | **0.9500** | 60  |
| Macro avg    | 0.9741    | 0.7000 | 0.7724 | 60      |
| Weighted avg | 0.9526    | 0.9500 | 0.9399 | 60      |

Confusion matrix: `cm_school_detector_test_School.png`

---

## §5 SubjectPredictor Metrics

| Subject      | Precision | Recall | F1     | Support |
|--------------|-----------|--------|--------|---------|
| ARTS         | 0.4545    | 0.8333 | 0.5882 | 6       |
| CS138        | 1.0000    | 0.7500 | 0.8571 | 4       |
| CS140        | 1.0000    | 1.0000 | 1.0000 | 4       |
| CS145        | 1.0000    | 1.0000 | 1.0000 | 6       |
| CS174        | 1.0000    | 1.0000 | 1.0000 | 4       |
| CS180        | 1.0000    | 1.0000 | 1.0000 | 4       |
| CS32         | 1.0000    | 1.0000 | 1.0000 | 8       |
| CS33         | 1.0000    | 0.8750 | 0.9333 | 8       |
| SPEECH       | 1.0000    | 0.6667 | 0.8000 | 6       |
| STS          | 0.7500    | 0.6000 | 0.6667 | 5       |
| **Accuracy** |           |        | **0.8727** | 55  |
| Macro avg    | 0.9205    | 0.8725 | 0.8845 | 55      |
| Weighted avg | 0.9178    | 0.8727 | 0.8829 | 55      |

Confusion matrix: `cm_subject_predictor_test_School.png`

---

## §5 Latency

Full pipeline: text extraction + SchoolDetector + SubjectPredictor.

| File Type | Avg (ms) | Min (ms) | Max (ms) | n  |
|-----------|----------|----------|----------|----|
| PDF       | 343.3    | 40.3     | 881.7    | 57 |
| DOCX      | 42.7     | 2.2      | 67.6     | 3  |

> PDF latency is dominated by text extraction (pdfplumber). Variance is high due to varying PDF size and complexity.

---

## §5 Discussion

**SchoolDetector** achieves 95.0% overall accuracy with perfect precision on Not-School (1.000) but low recall (0.400) — it misses 3 of 5 not-school files, classifying them as school. This is expected: the keyword rules are aggressive and fire on generic terms (e.g., "notes", "document"). School recall is perfect (1.000), meaning no school files are ever missed. For a file organizer, this tradeoff is acceptable — false positives (non-school files routed to Pending) are recoverable, while false negatives (school files ignored) are not.

**SubjectPredictor** achieves 87.3% accuracy on school files. CS140, CS145, CS174, CS180, and CS32 achieve perfect F1, reflecting distinctive filenames and course codes. **ARTS** has the lowest precision (0.455) — other subjects' files are predicted as ARTS when the model is uncertain, consistent with ARTS being the alphabetical fallback. **STS** (F1=0.667) and **SPEECH** (F1=0.800) show moderate performance; both have fewer distinctive keywords and smaller training sets relative to CS32/CS33.

**Latency** is acceptable for background processing. PDF extraction averages 343 ms due to pdfplumber parsing overhead; DOCX is much faster at 43 ms. Since classification runs asynchronously after download completion, end-user experience is unaffected.
