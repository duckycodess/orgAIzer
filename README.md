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

### 1. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

If your system says `ensurepip` is missing, install the OS package for `venv`
first, then rerun the command.

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run tests

```bash
python -m pytest tests/ -v
```

### 4. Run the app

```bash
python main.py
```

### 5. Configure folders

1. Open the **Settings** tab.
2. Set your **School root folder**.
3. Click **Rescan Subject Folders** so the app learns the available subjects.
4. Optionally set a **Dev/test watch folder** for safe testing.
5. Save settings.

If you are using WSL, remember to use Linux-style paths such as
`/mnt/c/Users/...` instead of Windows-style `C:\Users\...`.

## Important Folder Roles

Before training, make sure the team understands the difference between these 3
folders:

1. `train_School`
This is the labeled source folder used for bootstrapping. Files here are
already sorted into the correct subject folders.

2. `watch folder`
This is the incoming unsorted folder the app monitors. During testing, use a
safe dev folder. In real use, this can be Downloads.

3. `School root folder`
This is the real destination. Sorted files are moved to
`SchoolRoot/<Subject>/`.

Recommended workflow:

- use `train_School` for seeding
- use a separate test folder for the watch folder
- use `School` as the real destination root

## Training Data Bootstrap

If you already organize files inside subject folders, seed the database first:

```bash
python scripts/seed_data.py --school-root "/path/to/train_School" --dry-run
python scripts/seed_data.py --school-root "/path/to/train_School"
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

Notes:

- supported seed file types are `.pdf`, `.docx`, `.txt`, `.pptx`, and `.zip`
- the seed script stores training samples in SQLite, but it does not train the
  saved model files by itself
- after seeding, open the app and click **Refresh Model**
- avoid reseeding the exact same files repeatedly unless you intentionally want
  duplicate training samples

## First Training Run

This is the safest step-by-step flow for a new teammate:

1. Prepare `train_School`.
Put already-correct school files into top-level subject folders such as
`CS145`, `CS153`, `CS180`, `Arts1`, or `Arkiyo`.

2. Seed the database.
Run the dry run first, then the real seed command.

3. Start the app.

4. In **Settings**, set:
- **School root folder** to the real destination folder
- **Dev/test watch folder** to a safe test folder
- **Downloads folder** to the real Downloads path if needed later

5. Click these in order:
- **Rescan Subject Folders**
- **Save Settings**
- **Refresh Model**

6. Confirm that retraining finished.
You should see `Model updated!` in the Settings tab and retrain logs in the
terminal.

7. Drop test files into the watch folder one at a time.

8. Use Pending Decisions to teach the app:
- **Accept** if the predicted subject is correct
- **Change** if it is a school file but the subject is wrong
- **Skip** only if it is not a school file

9. After every few corrections, click **Refresh Model** again.
Background retraining also triggers automatically after every 5 accepted or
corrected decisions.

10. Keep training until you have enough labeled examples.
The default warm-up target is at least 25 confirmed school files overall and at
least 5 confirmed files for a subject before auto-move becomes trustworthy.

## Daily Use

Once the model is reasonably trained:

1. Leave the app running.
2. Let it watch the configured folder.
3. New files will either:
- auto-move into `SchoolRoot/<Subject>/` if confidence is high and warm-up is off
- appear in **Pending Decisions** if the app wants confirmation
- be logged as not-school if they do not look school-related

If the subject does not exist yet, the **Change** dialog can create a brand-new
subject by typing its name directly.

## How To Know The Model Is Trained

The easiest checks are:

1. The app says `Model updated!` after **Refresh Model**.
2. The models folder contains saved pickles.

Example check:

```bash
find "$HOME/OrgAIzer/models" -maxdepth 1 -type f | sort
```

Typical files:

- `subject_predictor.pkl`
- `course_predictor.pkl` for compatibility
- `school_detector.pkl` if there are enough both school and not-school examples

Important:

- if `school_detector.pkl` is missing, that usually means the app has not seen
  enough negative not-school examples yet
- `subject_predictor.pkl` is the main file that confirms subject training worked

## Training Tips

- Keep subject folder names consistent. Do not mix `CS180`, `cs180`, and
  `CS 180`.
- Use `Change`, not `Skip`, when a school file is predicted with the wrong
  subject.
- Add some not-school examples too, so the school detector can learn both
  classes.
- PDFs, DOCX, PPTX, TXT, and ZIP files are stronger training examples than
  image files because the app does not currently use OCR.
- Use a separate dev watch folder until the team trusts the behavior.

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
- The default auto-move threshold is `0.85`.

## Project Structure

```text
orgAIzer/
├── main.py
├── pretrained/
│   ├── orgaizer.db
│   ├── school_detector.pkl
│   └── subject_predictor.pkl
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

## Using a Pre-Trained Model

The `pretrained/` folder in this repo contains the trained model files so you can skip seeding and training entirely.

### 1. Clone the repo and set up the venv

```bash
git clone <repo-url>
cd orgAIzer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Copy the pretrained files into place

```bash
mkdir -p ~/OrgAIzer/models
cp pretrained/orgaizer.db ~/OrgAIzer/orgaizer.db
cp pretrained/school_detector.pkl ~/OrgAIzer/models/school_detector.pkl
cp pretrained/subject_predictor.pkl ~/OrgAIzer/models/subject_predictor.pkl
```

### 3. Run the app

```bash
python main.py
```

The model is already trained — no need to seed or click Refresh Model.

---

## Notes

- All data stays local.
- The SQLite schema still uses some legacy `course_*` column names internally for backward compatibility.
- The user-facing product should now be treated as a subject sorter, not a course/category sorter.
