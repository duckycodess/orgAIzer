# OrgAIzer Evaluation Results

## §3 Dataset Table

| Subject | # Training Samples | # Files in Folder |
|---------|--------------------|-------------------|
| ARTS    | 5                  | 10                |
| CS138   | 15                 | 15                |
| CS140   | 15                 | 15                |
| CS145   | 1                  | 17                |
| CS174   | 0                  | 13                |
| CS180   | 4                  | 9                 |
| CS32    | 25                 | 25                |
| CS33    | 32                 | 24                |
| SPEECH  | 17                 | 17                |
| STS     | 8                  | 9                 |
| Not-School | 26              | —                 |
| **Total** | **148**          | **154**           |

> CS145 has 1 sample; CS174 has 0 — effectively untrained classes.

---

## §3 Data Split Table

| Split      | Count | %     |
|------------|-------|-------|
| Train      | 102   | 68.9% |
| Validation | 23    | 15.5% |
| Test       | 23    | 15.5% |
| **Total**  | **148** | 100% |

Stratified split (seed=42), maintaining class proportions per subject.

---

## §5 SchoolDetector Metrics

| Class        | Precision | Recall | F1    | Support |
|--------------|-----------|--------|-------|---------|
| Not-School   | 0.000     | 0.000  | 0.000 | 4       |
| School       | 0.826     | 1.000  | 0.905 | 19      |
| **Accuracy** |           |        | **0.826** | 23  |
| Macro avg    | 0.413     | 0.500  | 0.452 | 23      |
| Weighted avg | 0.682     | 0.826  | 0.747 | 23      |

Confusion matrix image: `cm_school_detector.png`

---

## §5 SubjectPredictor Metrics

| Subject      | Precision | Recall | F1    | Support |
|--------------|-----------|--------|-------|---------|
| ARTS         | 0.333     | 1.000  | 0.500 | 1       |
| CS138        | 1.000     | 1.000  | 1.000 | 2       |
| CS140        | 1.000     | 1.000  | 1.000 | 2       |
| CS180        | 1.000     | 1.000  | 1.000 | 1       |
| CS32         | 1.000     | 1.000  | 1.000 | 4       |
| CS33         | 1.000     | 1.000  | 1.000 | 5       |
| SPEECH       | 0.000     | 0.000  | 0.000 | 3       |
| STS          | 0.000     | 0.000  | 0.000 | 1       |
| **Accuracy** |           |        | **0.789** | 19  |
| Macro avg    | 0.667     | 0.750  | 0.688 | 19      |
| Weighted avg | 0.754     | 0.789  | 0.763 | 19      |

Confusion matrix image: `cm_subject_predictor.png`

---

## §5 Latency

Full pipeline: text extraction + SchoolDetector + SubjectPredictor.

| File Type | Avg (ms) | Min (ms) | Max (ms) | n |
|-----------|----------|----------|----------|---|
| PDF       | 99.3     | 60.7     | 194.9    | 8 |
| DOCX      | 80.2     | 7.1      | 197.2    | 4 |

---

## §5 Discussion

SchoolDetector achieves 82.6% overall accuracy but **fails entirely on Not-School** (F1=0.000) — the keyword rules are too aggressive, flagging all 4 not-school test samples as school. Root cause: only 26 not-school training samples, insufficient to let the LR overlay override the keyword stage.

SubjectPredictor scores 78.9% accuracy on school files. CS32, CS33, CS138, CS140, and CS180 achieve perfect F1 — these subjects have sufficient samples (4–32) and distinctive filenames/content. **SPEECH (F1=0.000) and STS (F1=0.000) fail** completely; their test samples were misclassified as ARTS, consistent with the ARTS default-fallback bias and low per-class sample counts (STS test n=1, SPEECH test n=3).

ARTS has only 5 training samples yet the model defaults to it when no strong signal is found, inflating its apparent recall while harming SPEECH and STS precision.

**To improve:** add 10–15 more samples each for SPEECH, STS, and ARTS, then retrain. The LR pipeline already uses `class_weight="balanced"` — fixing the data imbalance is sufficient.
