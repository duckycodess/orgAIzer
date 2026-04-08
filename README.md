# OrgAIzer -- AI School Subject Sorter

OrgAIzer is a desktop app for students that watches a download folder, decides whether a file is school-related, predicts its subject, and moves it into the matching subject folder.

This repo originally experimented with a deeper `course/category` layout. The current version is intentionally simpler: it focuses on school files and sorts by subject only, which matches the team's latest scope and typical student workflow better.

**Team:** Aaron Baclor, Tristan Noval, Jarelle Ricaforte, Gabrielle Sacramento  
**Course:** CS 180 -- AI for Everyday Life

## Project Context

The project requirements ask for:

- a functional AI-powered app for an everyday problem
- clear UX with actionable output
- a personalization layer backed by local storage
- a user feedback loop for corrections and retraining

Your proposal frames the core problem as semantic file organization for students and knowledge workers. This refactor stays aligned with that idea, but narrows the destination label to the thing students care about most during the semester: the subject.

## Current Workflow

1. A file appears in the watched folder.
2. The app waits for the download to finish.
3. It extracts filename/content features.
4. `SchoolDetector` estimates whether the file is school-related.
5. `SubjectPredictor` predicts the best subject folder.
6. High-confidence predictions are auto-moved to `SchoolRoot/<Subject>/`.
7. Lower-confidence predictions appear in Pending Decisions for user review.
8. Accepted/corrected decisions are stored locally and used for retraining.

In Pending Decisions, the `Change` dialog can now either pick an existing subject
or create a brand-new one by typing its name directly.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the app

```bash
python main.py
```

### 3. Configure folders

1. Open the **Settings** tab.
2. Set your **School root folder**.
3. Click **Rescan Subject Folders** so the app learns the available subjects.
4. Optionally set a **Dev/test watch folder** for safe testing.
5. Save settings.

## Training Data Bootstrap

If you already organize files inside subject folders, seed the database first:

```bash
python scripts/seed_data.py --school-root "C:\Users\You\Documents\School"
```

The script treats each top-level folder under the school root as a subject. Nested folders are allowed, but the label stays the top-level subject name.

Examples:

```text
School/
  CS180/
    cs180_lab3.pdf
  Discrete Math/
    week2/
      induction_notes.pdf
```

## Models

- `SchoolDetector`
  - keyword rules for cold start
  - TF-IDF + Logistic Regression once enough labeled data exists
- `SubjectPredictor`
  - subject/code matching
  - token overlap and TF-IDF name similarity
  - Logistic Regression overlay after enough user-confirmed samples

## Warm-up And Feedback

- Warm-up starts enabled so the app asks for confirmation before it fully trusts auto-moves.
- Every accepted/corrected decision becomes a new local training sample.
- Background retraining is triggered after every 5 new corrections.

## Project Structure

```text
orgAIzer/
├── main.py
├── app/
│   ├── controller.py
│   └── settings.py
├── classifiers/
│   ├── school_detector.py
│   ├── subject_predictor.py
│   └── course_predictor.py      # compatibility wrapper
├── core/
│   ├── extractor.py
│   ├── mover.py
│   ├── stability.py
│   └── watcher.py
├── scripts/
│   └── seed_data.py
├── storage/
│   ├── db.py
│   └── repository.py
├── tests/
│   ├── test_classifiers.py
│   ├── test_mover.py
│   └── test_repository.py
└── ui/
    ├── history_widget.py
    ├── main_window.py
    ├── pending_widget.py
    └── settings_widget.py
```

## Notes

- All data stays local.
- The SQLite schema still uses some legacy `course_*` column names internally for backward compatibility.
- The user-facing product should now be treated as a subject sorter, not a course/category sorter.
