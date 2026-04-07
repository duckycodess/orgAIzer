# OrgAIzer — AI School File Sorter

A desktop app for students that watches your Downloads folder, classifies new files as school-related or not, and moves them to the right course folder automatically.

**Team:** Aaron Baclor, Tristan Noval, Jarelle Ricaforte, Gabrielle Sacramento  
**Course:** CS 180 — AI for Everyday Life

---

## Quick Start

### 1. Install Python 3.10+

Make sure Python 3.10 or newer is installed. Check with:
```
python --version
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the app

```bash
python main.py
```

### 4. First-time setup

1. Open the **Settings** tab.
2. Set your **School root folder** (e.g. `C:\Users\You\Documents\School`).
3. Click **Rescan Course Folders** — this discovers your existing course folders (CS180, CS145, etc.).
4. Optionally set a **Dev/test watch folder** for safe testing without touching real Downloads.
5. Click **Save Settings**.

### 5. Seed training data (recommended before demo)

Run the bootstrap script to pre-train the AI on your existing School folder structure:

```bash
python scripts/seed_data.py --school-root "C:\Users\You\Documents\School"
```

Then click **Refresh Model** in the Settings tab.

---

## How It Works

### Pipeline (3 stages)

```
New file in Downloads
  → Stability check (wait for download to finish)
  → Feature extraction (filename, text content, ZIP members)
  → Stage 1: School-related? (keyword rules + Logistic Regression)
  → Stage 2: Which course? (course code regex + TF-IDF similarity)
  → Stage 3: Which category? (keyword rules + Logistic Regression)
  → High confidence (≥ 85%): auto-move
  → Medium/Low confidence: show pending card → user decides
```

### Confidence Thresholds

| Level | Score | Behavior |
|-------|-------|----------|
| High | ≥ 85% | Auto-move (only after warm-up exits) |
| Medium | 55–84% | Show recommendation, ask user |
| Low | < 55% | Ask user |

Thresholds are configurable in the Settings tab.

### Warm-up Mode

The app starts in **warm-up mode** — it always asks the user for the first 25 confirmed school files (or until you manually disable it in Settings). This prevents bad auto-moves before the AI has learned from your corrections.

### Category Labels (fixed in v1)

- Lectures
- Labs
- Exercises
- Assignments
- References
- Others

### Supported File Types

- `.pdf` — text extracted via pdfplumber / PyMuPDF
- `.docx` — text extracted via python-docx
- `.pptx` — text extracted via python-pptx
- `.txt` — read directly
- `.zip` — member filenames inspected (no extraction)

---

## Project Structure

```
orgAIzer/
├── main.py                   # Entry point
├── requirements.txt
├── app/
│   ├── controller.py         # Central orchestrator
│   └── settings.py           # Typed settings object
├── core/
│   ├── watcher.py            # File system watcher (watchdog)
│   ├── stability.py          # Wait for download to finish
│   ├── extractor.py          # Feature extraction
│   └── mover.py              # Safe move + undo
├── classifiers/
│   ├── school_detector.py    # Stage 1: school vs not-school
│   ├── course_predictor.py   # Stage 2: course prediction
│   └── category_predictor.py # Stage 3: category prediction
├── storage/
│   ├── db.py                 # SQLite setup
│   └── repository.py         # CRUD operations
├── scripts/
│   └── seed_data.py          # Bootstrap training data
├── ui/
│   ├── main_window.py
│   ├── history_widget.py
│   ├── pending_widget.py
│   └── settings_widget.py
└── tests/
    ├── test_classifiers.py
    ├── test_mover.py
    └── test_repository.py
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

All 44 tests should pass.

---

## AI / Model Details

- **Model:** TF-IDF vectorizer + Logistic Regression (scikit-learn)
- **Why LR?** Works well on small datasets (200–500 samples), fast to retrain (<0.5s), produces calibrated probabilities, easy to explain in class.
- **Cold start:** Keyword rules provide reliable predictions from day 1, before any training data exists.
- **Retraining:** Happens automatically in the background after every 5 user corrections. Also triggerable manually via "Refresh Model" in Settings.
- **Data:** All training data is local to your machine (stored in `%APPDATA%\OrgAIzer\`). No data leaves your computer.

---

## Database Location

```
%APPDATA%\OrgAIzer\orgaizer.db
```

All events, corrections, and settings are stored here in SQLite.

## Trained Models Location

```
%APPDATA%\OrgAIzer\models\
```
