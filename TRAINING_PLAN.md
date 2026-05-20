# OrgAIzer — Complete Training & Improvement Plan

**Project:** CS 180 Final Project  
**Subjects:** Speech, STS, Arts  
**Demo mode:** Pre-trained model, live file segregation  
**Folder support:** Implemented (see [Implementation Status](#implementation-status))

---

## Table of Contents

- **[Complete Training Walkthrough (Start Here)](#complete-training-walkthrough-start-here)** ← if you just want to train, read this first
1. [Repo State](#1-repo-state)
2. [What the Training Pipeline Already Supports](#2-what-the-training-pipeline-already-supports)
3. [What Needs to Be Trained](#3-what-needs-to-be-trained)
4. [Are 3 Subjects Enough?](#4-are-3-subjects-enough)
5. [How Many Labeled Examples to Collect](#5-how-many-labeled-examples-to-collect)
6. [Training Folder Structure](#6-training-folder-structure)
7. [Bootstrapping the Database](#7-bootstrapping-the-database)
8. [Collecting Not-School Examples](#8-collecting-not-school-examples)
9. [Using the Feedback Loop for Training](#9-using-the-feedback-loop-for-training)
10. [When Retraining Happens](#10-when-retraining-happens)
11. [Verifying the Model Was Trained](#11-verifying-the-model-was-trained)
12. [Evaluating Demo Readiness](#12-evaluating-demo-readiness)
13. [Likely Failure Cases During Presentation](#13-likely-failure-cases-during-presentation)
14. [Final Paper — Methodology Section](#14-final-paper--methodology-section)
15. [Final Presentation Demo Flow](#15-final-presentation-demo-flow)
16. [Definition of Done](#16-definition-of-done)
- [Implementation Status](#implementation-status)
- [Prioritized Checklist](#prioritized-checklist)

---

## Complete Training Walkthrough (Start Here)

This section is the single source of truth for training the model from scratch. Follow every step in order. Do not skip steps — each one depends on the previous.

**Estimated time:** 1–2 hours including file preparation.  
**Who should do this:** One person on the team, on the machine that will run the demo.

---

### Prerequisites

Before you start, make sure you have:

- [ ] Python virtual environment set up: `python3 -m venv .venv && source .venv/bin/activate`
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Tests passing: `python -m pytest tests/ -v` → should say `51 passed`
- [ ] A real School destination folder on your machine (e.g. `~/School` or `C:\Users\You\School`)
- [ ] A separate safe test folder that is NOT your real Downloads (e.g. `~/TestWatch`)

If any prerequisite fails, fix it before continuing. Training on a broken install wastes time.

---

### Phase 1 — Prepare Training Files

**Goal:** Build `train_School/` with 15–20 labeled files per subject.

#### Step 1.1 — Create the folder structure

Create a folder called `train_School` anywhere on your machine. Inside it, create exactly three subfolders with these exact names:

```
train_School/
├── Speech/
├── STS/
└── Arts/
```

> The folder names must exactly match the subject names you will use in the app. Spelling, capitalization, and spacing all matter.

#### Step 1.2 — Collect Speech files (15–20 files)

Copy real school files for your Speech/Oral Communication subject into `train_School/Speech/`.

**Rules:**
- Use `.pdf`, `.docx`, `.pptx`, `.txt`, or `.zip` files only (other formats are ignored by the seed script)
- Include the word **speech** in as many filenames as possible: `speech_hw1.pdf`, `oral_comm_notes.pdf`, `speech_activity2.docx`
- If a file has no subject name in its filename, rename it before putting it in the folder
- Nested subfolders are fine — the label always comes from the top-level folder name

**Example acceptable filenames:**
```
speech_midterm_notes.pdf
debate_script_speech.docx
oral_communication_module2.pdf
public_speaking_hw3.pdf
speech_reflection_paper.docx
```

#### Step 1.3 — Collect STS files (15–20 files)

Copy real STS (Science, Technology, and Society) files into `train_School/STS/`.

**Critical for STS — read this carefully:**

"STS" is only 3 characters. The model's keyword matching is weak for short abbreviations. To train STS well, your files should contain the words **"science technology society"** somewhere in their text content — not just "STS" in the filename.

**Rules:**
- Include "sts" or "science technology" in as many filenames as possible: `sts_reaction_paper.pdf`, `science_technology_society_reading.pdf`
- If you have PDF or DOCX files, the app will extract text from them — files with "science technology and society" written inside will train much better than files that only have "STS" in the filename
- A reaction paper with "This reaction paper for STS discusses the impact of technology on society" inside it is ideal

**Example acceptable filenames:**
```
sts_module3_notes.pdf
science_technology_society_reading.docx
sts_midterm_reviewer.pdf
technology_ethics_essay.docx
sts_reaction_paper2.pdf
```

#### Step 1.4 — Collect Arts files (15–20 files)

Copy real Arts files into `train_School/Arts/`.

**Rules:**
- Include "arts" or "art" in as many filenames as possible: `arts_portfolio.pdf`, `art_history_notes.pdf`
- Arts and Speech can share some vocabulary (both humanities). Make sure Arts files are actually about visual arts, not performing arts, so they don't overlap with Speech

**Example acceptable filenames:**
```
arts_portfolio.pdf
drawing_techniques_worksheet.docx
art_history_module1.pdf
color_theory_notes.pdf
arts_reflection_paper.docx
```

#### Step 1.5 — Verify your folder before continuing

Run this to count your files:

```bash
# Linux / Mac / WSL:
find train_School -type f | sort
```

Expected output: at least 45 lines (15 per subject). If any subject has fewer than 15 files, add more before moving on.

Also check the counts per subject:

```bash
# Count per subject:
find train_School/Speech -type f | wc -l
find train_School/STS -type f | wc -l
find train_School/Arts -type f | wc -l
```

Each should print `15` or higher.

---

### Phase 2 — Seed the Database

**Goal:** Load the labeled filenames into the SQLite training database so the model can learn from them.

#### Step 2.1 — Activate your virtual environment

```bash
source .venv/bin/activate
```

If you see `(.venv)` at the start of your terminal prompt, you're in the right environment.

#### Step 2.2 — Run a dry run first

```bash
python scripts/seed_data.py --school-root "/full/path/to/train_School" --dry-run
```

Replace `/full/path/to/train_School` with the actual absolute path to your folder.

**What to look for in the output:**
- `Inserted: 45` or higher (your total file count)
- `Skipped (unsupported ext): 0` or a small number (images and other unsupported formats are skipped — this is normal)
- The "First 10 samples" table should show filenames mapped to the correct subjects
- The "Per-subject counts" section should show roughly equal counts for Speech, STS, and Arts

If any filename maps to the wrong subject, check that your `train_School/` folder structure is correct.

**Example of good dry-run output:**
```
[DRY RUN] Seed complete.
  Inserted: 52 samples
  Skipped (unsupported ext): 3

First 10 samples (sanity check):
Filename                                 Subject
------------------------------------------------------------
arts_portfolio.pdf                       Arts
arts_reflection_paper.docx               Arts
color_theory_notes.pdf                   Arts
debate_script_speech.docx                Speech
...

Per-subject counts:
  Arts: 17
  Speech: 18
  STS: 17
```

#### Step 2.3 — Run the real seed

Once the dry run looks correct, run without `--dry-run`:

```bash
python scripts/seed_data.py --school-root "/full/path/to/train_School"
```

You should see the same output but without `[DRY RUN]`. The samples are now written to the SQLite database.

> **Warning:** Do not run the seed script twice on the same folder unless you intend to add duplicate training samples. If you need to redo the seed, clear the database first or use a fresh database file.

---

### Phase 3 — Configure the App

**Goal:** Tell the app where your School folder is, what subjects exist, and which folder to watch.

#### Step 3.1 — Start the app

```bash
python main.py
```

The app window opens. You should see tabs: **Pending**, **History**, **Settings**.

#### Step 3.2 — Open the Settings tab

Click the **Settings** tab.

#### Step 3.3 — Set the School root folder

In the **School root folder** field, enter the path to your real School destination folder — the folder where you want sorted files to end up. This is NOT `train_School`. This is your actual `School/` folder.

Example:
- Linux/WSL: `/home/yourname/School`
- Windows: `C:\Users\YourName\School`

> If the folder does not exist yet, create it manually first, and create the three subject subfolders inside it: `School/Speech/`, `School/STS/`, `School/Arts/`.

#### Step 3.4 — Set the Dev/test watch folder

In the **Dev/test watch folder** field, enter the path to a safe test folder — a folder you drop test files into during training. **Do not use your real Downloads folder yet.**

Example:
- Linux/WSL: `/home/yourname/TestWatch`
- Windows: `C:\Users\YourName\TestWatch`

Create this folder if it doesn't exist:

```bash
mkdir -p ~/TestWatch      # Linux/Mac/WSL
```

#### Step 3.5 — Rescan subject folders

Click **Rescan Subject Folders**.

The app will scan your School root and register `Speech`, `STS`, and `Arts` as known subjects. You should see a confirmation message.

#### Step 3.6 — Save settings

Click **Save Settings**.

---

### Phase 4 — Train the Subject Model

**Goal:** Train `subject_predictor.pkl` from the seeded database.

#### Step 4.1 — Click Refresh Model

Still on the Settings tab, click **Refresh Model**.

Wait a few seconds. You should see **"Model updated!"** appear in the Settings tab and retrain log lines in the terminal.

#### Step 4.2 — Confirm the model file was created

```bash
# Linux / WSL:
ls -la "$HOME/OrgAIzer/models/"

# Windows (in terminal):
dir "%APPDATA%\OrgAIzer\models\"
```

You should see:
```
subject_predictor.pkl    ← this is the main model file
course_predictor.pkl     ← compatibility alias, created automatically
```

> `school_detector.pkl` will be missing at this point — that is expected. The school detector needs examples of both school AND not-school files to train. You will add not-school examples in the next phase.

#### Step 4.3 — Quick smoke test

Drop a clearly labeled file into your TestWatch folder. For example, copy `train_School/Speech/speech_hw1.pdf` (or any Speech file) into `~/TestWatch/`.

Watch the app. Within a few seconds, one of two things should happen:
- The file appears in the **Pending Decisions** tab with "Speech" predicted and a confidence score, OR
- The file is auto-moved to `School/Speech/` (if warmup mode is already off)

If nothing happens after 10 seconds, check the terminal for error messages.

---

### Phase 5 — Train the School Detector (Add Not-School Examples)

**Goal:** Teach the model what non-school files look like so it doesn't try to sort them.

The school detector's Logistic Regression model requires at least one example of each class — school AND not-school. Until you add not-school examples, the detector runs on keyword rules only, which is weaker.

#### Step 5.1 — Collect not-school files

Find 10–15 files on your computer that are clearly NOT school-related. Good examples:

- A bank statement PDF
- A shopping receipt
- A resume or CV (yours or a sample)
- A personal document (grocery list, personal notes)
- Any random downloaded file (game guide, software manual, etc.)
- A personal photo (`.jpg` is skipped for content but the filename is still a signal)

Copy them into a temporary folder, e.g. `~/NotSchool/`. Do not put them in `train_School`.

#### Step 5.2 — Drop them into the TestWatch folder one by one

Copy the first not-school file into `~/TestWatch/`. Watch the app. The file should appear in **Pending Decisions** (or possibly in **History** as "not_school" if the keyword detector catches it).

- If it appears in **Pending Decisions** with a subject predicted: click **Skip**
- If it appears in **History** as "not_school": no action needed — it was already logged as not-school, but you should still add a training sample. Go to the History tab, find the file, and use "Mark as Not School" if available, or simply proceed — the detection itself creates a record.

> **The most important thing:** for each not-school file that appears in Pending Decisions, click **Skip**. This creates a `label_school=0` training sample in the database.

Repeat for all 10–15 not-school files. You can copy them one at a time or in small batches (2–3 at a time).

#### Step 5.3 — Refresh the model again

After processing all not-school files, click **Refresh Model** in Settings.

Now check for `school_detector.pkl`:

```bash
ls -la "$HOME/OrgAIzer/models/"
```

You should now see all three files:
```
school_detector.pkl      ← now exists
subject_predictor.pkl
course_predictor.pkl
```

If `school_detector.pkl` is still missing after clicking Refresh Model, you may not have enough not-school samples yet. Check:

```bash
# Open a Python shell in the project directory:
python3 -c "
from storage.db import get_connection, init_schema
conn = get_connection()
row = conn.execute('SELECT COUNT(*) FROM training_samples WHERE label_school = 0').fetchone()
print('Not-school samples:', row[0])
"
```

If the count is below 5, add more not-school files. If it's 5 or more and `school_detector.pkl` still doesn't appear, click Refresh Model one more time.

---

### Phase 6 — Validate and Tune

**Goal:** Check that the model predicts correctly and correct any errors.

#### Step 6.1 — Test with files the model has NOT seen before

Collect 5–10 new files (not from `train_School`) for each subject. These are your held-out test files. Keep a list.

Drop them into `~/TestWatch/` one at a time and record:
- What subject was predicted
- What the confidence score was
- Whether the prediction was correct

#### Step 6.2 — Correct wrong predictions using the feedback loop

For every file the model gets wrong:

- If it appears in **Pending Decisions**:
  - Wrong subject → click **Change**, pick the correct subject
  - Not a school file → click **Skip**
- If it was auto-moved to the wrong folder:
  - Find it in **History**, use the Undo button to move it back, then it will re-appear in Pending Decisions

Each correction becomes a new training sample. Background retraining fires automatically after every 5 corrections.

#### Step 6.3 — Manually retrain after corrections

After correcting several files, click **Refresh Model** to apply all the new samples at once.

#### Step 6.4 — Repeat until accuracy is acceptable

Keep dropping test files, correcting errors, and refreshing the model. Target: **at least 80% of test files predicted correctly** before considering training done.

---

### Phase 7 — Disable Warmup Mode

**Goal:** Allow the model to auto-move files without asking for confirmation.

Warmup mode blocks auto-moves until the model has seen enough confirmed examples. It exits automatically when:
- Total confirmed school files ≥ 25, AND
- Per-subject confirmed files ≥ 5

If you went through all the steps above, you likely already have enough samples. Check warmup status by looking at the Settings tab. If it still says warmup is active, keep accepting/correcting files in Pending Decisions until the thresholds are met.

Once warmup exits, high-confidence files (≥0.85) will auto-move directly to the correct subject folder without appearing in Pending Decisions.

---

### Phase 8 — Final Demo Preparation

**Goal:** Test all planned demo files and confirm everything works end-to-end.

#### Step 8.1 — Prepare exactly the files you will drop during the demo

Pick 5 files you will use in the live demo:
1. A clearly labeled Speech file (e.g. `speech_activity_final.pdf`)
2. A clearly labeled STS file (e.g. `sts_reaction_paper3.pdf`)
3. A clearly labeled Arts file (e.g. `arts_portfolio_final.pdf`)
4. An ambiguous file (e.g. `notes.pdf` — a file with STS content but no obvious keyword in the name)
5. A not-school file (e.g. `invoice.pdf`)

#### Step 8.2 — Test each demo file before the presentation

Clean the TestWatch folder:

```bash
rm -f ~/TestWatch/*     # Linux/Mac/WSL
```

Drop each demo file in one at a time. For each file, write down:
- Predicted subject
- Confidence score
- Was it auto-moved or sent to Pending?

If any demo file predicts incorrectly, either:
a. Correct it via the feedback loop and retrain, OR
b. Swap it for a different file that the model handles correctly

Do NOT use a file in the demo that you know will predict wrong.

#### Step 8.3 — Final model check

```bash
python -m pytest tests/ -v
# Expected: 51 passed
```

```bash
ls -la "$HOME/OrgAIzer/models/"
# Expected: subject_predictor.pkl, course_predictor.pkl, school_detector.pkl
```

#### Step 8.4 — Confirm warmup is off

In Settings, warmup should be inactive. If it is still on, keep confirming files until the threshold is met (25 total school + 5 per subject).

#### Step 8.5 — Clean up before demo day

- Empty the TestWatch folder (no leftover files)
- Clear the School destination folders of any test files you moved there during training
- Re-create empty `School/Speech/`, `School/STS/`, `School/Arts/` folders so the demo starts clean

---

### Training Is Done When

| Check | Command / Action |
|---|---|
| `subject_predictor.pkl` exists | `ls "$HOME/OrgAIzer/models/"` |
| `school_detector.pkl` exists | Same |
| All 5 demo files predict correctly | Manual test (Step 8.2) |
| Warmup mode is off | Settings tab |
| 51 tests pass | `python -m pytest tests/ -v` |
| Watch folder is empty | Check manually |

---

## 1. Repo State

**Architecture complete. No trained models yet.**

The full pipeline is built and running:

```
watch folder → stability check → extractor → SchoolDetector → SubjectPredictor → mover → feedback loop → retrainer
```

Both classifiers operate in **keyword/rule-only cold-start mode** until the database is seeded and "Refresh Model" is clicked. No `.pkl` files exist yet.

Key thresholds:

| Setting | Value | File |
|---|---|---|
| School detector LR activates after | 10 samples (both classes) | `classifiers/school_detector.py:26` |
| Subject predictor LR activates after | 15 school samples | `classifiers/subject_predictor.py:23` |
| Warmup exit: total school confirmed | 25 | `app/settings.py:14` |
| Warmup exit: per-subject confirmed | 5 | `app/settings.py:15` |
| Auto-move confidence threshold | 0.85 | `app/settings.py:32` |
| Background retrain fires after every | 5 corrections | `app/settings.py:19` |

> **Important for Speech/STS/Arts:** These are descriptive subject names, not course codes. The `COURSE_CODE_RE` pattern (`[A-Z]{2,4}\d{3,4}`) will **not** match them. The LR overlay is therefore more critical for this demo than it would be for code-style subjects like "CS180". Training enough examples per subject is essential.

---

## 2. What the Training Pipeline Already Supports

Everything needed for the demo is already implemented.

| Feature | Location | Status |
|---|---|---|
| Seed DB from labeled folder | `scripts/seed_data.py` | Ready |
| Keyword cold-start (no training needed) | `classifiers/school_detector.py:46–70` | Ready |
| TF-IDF + Logistic Regression school detector | `classifiers/school_detector.py:108–151` | Ready |
| Rule-based subject matching | `classifiers/subject_predictor.py:110–150` | Ready |
| TF-IDF + Logistic Regression subject predictor | `classifiers/subject_predictor.py:168–209` | Ready |
| Background retraining (every 5 corrections) | `app/controller.py:251–255` | Ready |
| Manual retrain ("Refresh Model" button) | `app/controller.py:358–371` | Ready |
| Feedback loop (accept/correct/skip → training sample) | `app/controller.py:193–256` | Ready |
| Mark not-school as school correction | `app/controller.py:258–343` | Ready |
| Warmup mode (blocks auto-move until thresholds met) | `app/settings.py:14–16` | Ready |
| **Folder detection and classification** | `core/watcher.py`, `core/extractor.py` | **Newly added** |

---

## 3. What Needs to Be Trained

Two models must be trained before the demo.

### A. `school_detector.pkl`

- **Activates after:** ≥10 total labeled samples with at least 1 school and 1 not-school example
- **Input:** list of dicts with `text_features` (str) and `label_school` (int `0` or `1`)
- **Without it:** classifier uses keyword rules only — reliable for clearly labeled files, weaker on ambiguous ones

### B. `subject_predictor.pkl`

- **Activates after:** ≥15 school samples across ≥2 distinct subjects
- **Input:** same sample list — filters internally to `label_school=1` rows with a subject label
- **Without it:** classifier uses token overlap and cosine similarity — functional but lower confidence

### C. `course_predictor.pkl`

Written automatically alongside B as a compatibility alias (`app/controller.py:85`). No separate action needed.

Both models are trained in one background pass by `trigger_retrain()`. Populate the SQLite `training_samples` table first (via seed script or feedback loop), then click **Refresh Model** in the app.

---

## 4. Are 3 Subjects Enough?

**Yes. 3 subjects is ideal for a class demo.**

**Advantages:**
- Easy to prepare 15–20 labeled examples per class
- Logistic Regression trains well on small balanced datasets
- Predictions are easy to explain to a non-ML audience
- Less demo risk — fewer subjects means fewer ways to mis-predict during a live run

**Tradeoffs to acknowledge:**
- Random baseline is 33% (vs ~10% for 10 subjects). Report this honestly and show the model achieves ≥80% to demonstrate clear improvement.
- "Speech" and "Arts" share humanities vocabulary. Use subject names in filenames and ensure training content is distinctive.
- "STS" is a 3-character acronym. Keyword matching is weaker. Files should contain "science technology society" in their text content, not just the "STS" abbreviation.

**For the paper:** Frame 3 subjects as a deliberate, validated scope. Note that the architecture scales to N subjects without code changes.

---

## 5. How Many Labeled Examples to Collect

### Minimum to activate both LR models

| Label | Minimum | Recommended | Notes |
|---|---|---|---|
| Speech (school) | 5 | 15–20 | Subject predictor needs ≥15 total school |
| STS (school) | 5 | 15–20 | Same |
| Arts (school) | 5 | 15–20 | Same |
| Not-school | 5 | 10–15 | School detector needs both classes |
| **Total** | **20** | **55–75** | |

### Why 15–20 per subject instead of the strict minimum

- Logistic Regression needs enough signal per class to generalize beyond training examples
- 15–20 per subject = 45–60 total school samples, which comfortably exceeds the 25-sample warmup threshold
- More examples means higher confidence predictions during the demo

### Why 10–15 not-school examples

- The school detector's LR will not activate until it sees at least one not-school sample
- Without not-school training data, the model risks classifying everything as school-related
- 10–15 gives the decision boundary enough room to work

---

## 6. Training Folder Structure

Create this structure on the machine that will run the app. Use this as `train_School`.

```
train_School/
├── Speech/
│   ├── speech_activity1.docx
│   ├── speech_hw1.pdf
│   ├── public_speaking_notes.pdf
│   ├── debate_script.docx
│   ├── oral_comm_module2.pdf
│   ├── ... (15–20 files total)
├── STS/
│   ├── sts_reaction_paper.pdf
│   ├── science_technology_society_reading.pdf
│   ├── sts_midterm_notes.docx
│   ├── technology_ethics_essay.pdf
│   ├── ... (15–20 files total)
└── Arts/
    ├── arts_portfolio.pdf
    ├── drawing_techniques.docx
    ├── art_history_notes.pdf
    ├── color_theory_worksheet.pdf
    └── ... (15–20 files total)
```

**Naming rules:**

1. Include the subject name in as many filenames as possible: `speech_hw1.pdf`, `sts_module3.pdf`, `arts_reflection.pdf`
2. For STS specifically: ensure file content mentions "Science Technology and Society" — the 3-letter abbreviation alone is a weak signal
3. Do not mix subject content across files
4. Supported seed extensions: `.pdf`, `.docx`, `.txt`, `.pptx`, `.zip`

**Not-school examples** do not go in `train_School`. Add them through the app's feedback loop (see [Section 8](#8-collecting-not-school-examples)).

---

## 7. Bootstrapping the Database

### Step-by-step for a new teammate

```bash
# 1. Activate virtual environment
source .venv/bin/activate

# 2. Dry run — verify what will be inserted before writing anything
python scripts/seed_data.py --school-root "/path/to/train_School" --dry-run

# 3. Review the output:
#    - "First 10 samples" table: confirm filenames map to correct subjects
#    - "Per-subject counts": confirm ~15–20 per subject

# 4. Run the real seed
python scripts/seed_data.py --school-root "/path/to/train_School"

# 5. Start the app
python main.py

# 6. In Settings, configure:
#    - School root folder  →  your real School destination (e.g. ~/School)
#    - Dev/test watch folder  →  a safe test folder (NOT your real Downloads)
#    Click:  Rescan Subject Folders  →  Save Settings  →  Refresh Model

# 7. Confirm success
#    - Terminal shows retrain log lines
#    - Settings tab shows "Model updated!"
```

### Check that model files were created

```bash
# Linux / WSL:
ls -la "$HOME/OrgAIzer/models/"

# Expected files:
#   subject_predictor.pkl   ← confirms subject training worked
#   course_predictor.pkl    ← compatibility alias, created automatically
#   school_detector.pkl     ← only appears after seeing not-school examples too
```

### What the seed script does and does NOT do

| Does | Does not |
|---|---|
| Reads filenames and path tokens from every supported file under `train_School/` | Read file content (text extraction happens live when a file is dropped) |
| Labels each sample with the top-level folder name as subject | Seed not-school examples (those come from the feedback loop) |
| Writes labeled rows to `training_samples` in SQLite | Train the model — that requires clicking "Refresh Model" afterwards |

---

## 8. Collecting Not-School Examples

The seed script only handles school files. Not-school examples must be added via the app's feedback loop.

### Method: drop and skip

1. Set a dev watch folder (not your real Downloads)
2. Drop in non-school files: `receipt.pdf`, `personal_photo.jpg`, `gaming_guide.pdf`, `bank_statement.pdf`, etc.
3. When they appear in Pending Decisions with a subject predicted, click **Skip**
4. Each Skip creates a `label_school=0` training sample in SQLite

### Good not-school examples for this scope

- Personal documents: resume, grocery list
- Financial: bank statement, invoice, receipt
- Entertainment: movie watchlist, game manual, playlist
- Random downloads: installer `.zip`, desktop wallpaper, meme

Aim for **10–15 not-school samples** before clicking Refresh Model. After reaching this count, `school_detector.pkl` will be created on the next retrain.

---

## 9. Using the Feedback Loop for Training

Every interaction in Pending Decisions creates a training sample automatically.

| Button | Meaning | Training effect |
|---|---|---|
| **Accept** | Subject prediction was correct | `label_school=1`, `label_subject=<predicted>` |
| **Change** | School file but wrong subject | `label_school=1`, `label_subject=<corrected>` |
| **Skip** | Not a school file | `label_school=0`, `label_subject=None` |

Background retraining fires automatically after every 5 corrections. Manual retraining is available any time via **Refresh Model** in Settings.

### Before the demo

- Drop test files into the watch folder and correct any mis-predictions
- Refresh Model after each batch of corrections
- Continue until all 5 demo files predict correctly

### During the demo

- Have 3–5 pre-tested files ready to drop in
- If the model gets one wrong, use **Change** and say: "The model updates from feedback — this correction becomes a training sample immediately."
- This is a feature, not a failure

---

## 10. When Retraining Happens

| Trigger | Location | Notes |
|---|---|---|
| **Manual:** "Refresh Model" button | Settings tab | Available at any time; always safe to click |
| **Automatic:** every 5 corrections | `app/controller.py:251–255` | Controlled by `RETRAIN_EVERY_N = 5` in `app/settings.py:19` |

Both paths run `_RetrainWorker`, a background QThread. It trains fresh instances of both classifiers, saves `.pkl` files, then hot-swaps them into the live classifiers without restarting the app.

### Practical retraining cadence

1. Seed DB → Refresh Model once
2. Drop 5–10 test files → correct mis-predictions → auto-retrain fires
3. Drop 5–10 not-school files → Skip them → Refresh Model
4. Repeat until all demo files predict correctly at ≥0.85 confidence

---

## 11. Verifying the Model Was Trained

### Check 1 — App UI

Settings tab shows **"Model updated!"** after clicking Refresh Model.

### Check 2 — Model files exist

```bash
# Linux / WSL:
ls -la "$HOME/OrgAIzer/models/"
# Expected: subject_predictor.pkl, course_predictor.pkl, school_detector.pkl
```

### Check 3 — Confidence increases

Before LR is active, subject predictor returns `conf ≈ 0.50–0.70` (cosine fallback). After LR activates, clearly labeled files should return `conf ≥ 0.85`.

### Check 4 — Run tests

```bash
python -m pytest tests/ -v
# Expected: 51 passed
```

### Check 5 — Manual smoke test

Drop a file named `speech_sample.pdf` into the watch folder. If the app predicts "Speech" with ≥0.85 confidence, training succeeded.

---

## 12. Evaluating Demo Readiness

### Minimum bar

| Test | Pass condition |
|---|---|
| 3 clearly labeled files per subject (9 total) | All 9 predicted correctly |
| 3 files with ambiguous filenames but clear content | ≥7 of 9 correct |
| 3 not-school files | All 3 logged as not-school, not moved |
| 1 wrong prediction → Change → similar file | Second file predicted correctly |

### Recommended pre-demo eval

Prepare a held-out set of ~15 files (5 per subject) that were **not** in the training seed. Drop each one, record the prediction and confidence, calculate accuracy.

**Target: ≥80% accuracy.** With 15–20 training examples per subject, 85–90% is realistic.

### Test the exact demo files the day before

- Drop each planned demo file into the watch folder
- Record the predicted subject and confidence
- If any demo file mis-predicts, either correct it through the feedback loop or swap it for a file the model handles correctly

---

## 13. Likely Failure Cases During Presentation

| Failure | Likelihood | Mitigation |
|---|---|---|
| "Speech" predicted for Arts file (shared humanities vocabulary) | Medium | Use subject names in filenames; keep training content distinctive |
| "STS" not recognized (file says "reaction paper" with no STS keywords) | High | Train STS files that mention "science technology society" in body text |
| Not-school file predicted as school | Medium | Collect and train on 10+ not-school examples before demo |
| Model in cold-start only — `.pkl` files missing | High if forgotten | Verify model files exist before demo; see Check 2 above |
| Warmup mode blocks auto-move during demo | Medium | Confirm `warmup_active = False` before demo (25+ school samples needed) |
| Dropped folder not processed (old bug, now fixed) | Low | Folder support is implemented and tested |
| Duplicate filename in watch folder confuses audience | Low | Clean the watch folder before each demo test run |

---

## 14. Final Paper — Methodology Section

> Adapt formatting and length to your paper template.

### Model Architecture

OrgAIzer uses two classifiers in a cascade pipeline. The first stage, `SchoolDetector`, determines whether an incoming file is school-related. The second stage, `SubjectPredictor`, identifies the most likely subject folder for files that pass stage one.

Both classifiers use a hybrid strategy: deterministic keyword and rule matching provides a cold-start baseline with no training data required, while a TF-IDF + Logistic Regression overlay activates once sufficient labeled examples accumulate (≥10 for school detection, ≥15 for subject prediction). This design ensures the app is immediately useful on first run while improving continuously from user feedback.

### Feature Extraction

Features are extracted from the file or folder name, extracted text content (first 4,000 characters, supporting PDF, DOCX, PPTX, TXT, and ZIP archives), and — for folders — the names of files contained inside. No OCR or image processing is used. All signals are concatenated into a single text string and vectorized using TF-IDF with unigram and bigram features (500 features for school detection, 1,000 for subject prediction).

### Training Data

Initial training data was bootstrapped from an organized set of labeled school files using `scripts/seed_data.py`. Additional labeled samples were generated through the in-app feedback loop: user decisions (Accept, Change, Skip) on pending predictions are stored as training samples in a local SQLite database. Negative examples were collected by dropping non-school files into the watch folder and marking them via the Skip action.

### Retraining

Models are retrained automatically after every 5 user corrections and can be triggered manually via the Settings panel. Retraining runs in a background thread to keep the UI responsive. Trained model weights are persisted as joblib-serialized scikit-learn Pipeline objects (`subject_predictor.pkl`, `school_detector.pkl`).

### Evaluation

The system was evaluated on a held-out test set of [N] files across 3 subjects (Speech, STS, Arts) plus non-school files. **[Insert actual accuracy numbers from your pre-demo evaluation here.]**

---

## 15. Final Presentation Demo Flow

### Setup (before presenting)

- [ ] Model `.pkl` files confirmed to exist
- [ ] `warmup_active = False` (25+ school samples confirmed)
- [ ] Watch folder is empty
- [ ] All 5 demo files tested and predictions known
- [ ] School root has `Speech/`, `STS/`, `Arts/` folders

### Live demo script (~3 minutes)

**Step 1 — Problem framing (30s)**

Show the problem: "Students download files and they pile up unsorted. OrgAIzer fixes this automatically using a trained model."

**Step 2 — App overview (30s)**

Open the app. Show the Settings tab: school root configured, `Speech/`, `STS/`, `Arts/` exist. Open the History tab to show it's empty.

**Step 3 — Auto-move demo (60s)**

Drop in a clearly labeled file (e.g. `speech_activity2.pdf` — a file the model has been trained to recognize). The app detects it, classifies it, and auto-moves it to `School/Speech/`.

Say: *"High confidence prediction — the model moved this automatically without asking."*

**Step 4 — Pending Decisions and correction (60s)**

Drop in an ambiguous file (e.g. `notes.pdf` with STS content but no obvious keywords). The app places it in Pending Decisions. Open the Pending tab, click Change, select STS, confirm.

Say: *"For lower-confidence predictions, the user reviews. This correction becomes a training sample — the model learns from it."*

**Step 5 — Not-school file (30s)**

Drop in `invoice.pdf`. The app logs it as not-school in the History tab with low confidence.

Say: *"Personal files are identified and left alone."*

**Optional Step 6 — Folder demo (30s)**

Drop in an entire folder named `STS_module3/` containing a few files. The app processes the folder and moves it to `School/STS/`.

Say: *"The app can also handle entire project folders, not just individual files."*

---

## 16. Definition of Done

The model is **ready for demo** when all of the following are true:

- [ ] `subject_predictor.pkl` exists in the models directory
- [ ] `school_detector.pkl` exists in the models directory
- [ ] ≥15 labeled training samples per subject (Speech, STS, Arts) are in the DB
- [ ] ≥10 not-school samples are in the DB
- [ ] `warmup_active = False` (25+ school samples confirmed, 5+ per subject)
- [ ] All planned demo files predict correctly with ≥0.80 confidence
- [ ] `python -m pytest tests/ -v` → 51 passed

---

## Implementation Status

Folder support was implemented and all 51 tests pass. Changes made:

| File | What changed |
|---|---|
| `core/stability.py` | Added `wait_until_stable_dir()` — polls total byte size inside folder |
| `core/extractor.py` | Added `extract_folder_features()` — folder name as stem, contained filenames as `zip_members`, text from first 3 supported files |
| `core/watcher.py` | Removed directory early-return; folders now dispatched through the same pipeline as files |
| `app/controller.py` | `_on_file_detected` branches on `p.is_dir()` to use folder stability check and folder feature extraction |
| `tests/test_mover.py` | 2 new tests: folder move, folder duplicate resolution |
| `tests/test_classifiers.py` | 6 new tests for `extract_folder_features` including end-to-end subject prediction from a folder |

### How folder classification works

When a folder is dropped into the watch folder:
1. Watcher fires `on_created` or `on_moved` with `is_directory=True`
2. Stability check polls the total size of all files inside until stable
3. `extract_folder_features` builds a `FileFeatures` object:
   - `stem` = folder name (e.g. `STS_module3`)
   - `zip_members` = names of all files inside (e.g. `["reading.txt", "notes.pdf"]`)
   - `text` = extracted text from up to 3 supported files inside
4. `all_text` combines stem + text + zip_members — the same property both classifiers already read
5. Same classification pipeline runs: school detector → subject predictor → mover

---

## Prioritized Checklist

### Must do before demo

- [ ] Create `train_School/Speech/`, `train_School/STS/`, `train_School/Arts/` with 15–20 files each
- [ ] Include subject name in most filenames (`speech_hw1.pdf`, `sts_module3.pdf`, `arts_project.pdf`)
- [ ] For STS: ensure files contain "science technology society" in body text, not just "STS"
- [ ] Dry-run seed: `python scripts/seed_data.py --school-root "/path/to/train_School" --dry-run`
- [ ] Real seed: `python scripts/seed_data.py --school-root "/path/to/train_School"`
- [ ] Configure app: school root, dev watch folder, Rescan Subject Folders, Save Settings
- [ ] Click Refresh Model — confirm "Model updated!" appears
- [ ] Confirm `subject_predictor.pkl` exists
- [ ] Drop 10–15 not-school files into watch folder, Skip all of them
- [ ] Refresh Model again — confirm `school_detector.pkl` now exists
- [ ] Test all planned demo files — record predicted subject and confidence for each
- [ ] Confirm `warmup_active = False` before demo
- [ ] Run `python -m pytest tests/ -v` — all 51 pass
- [ ] Clean the watch folder

### Nice to have

- [ ] Write a small eval script that prints per-subject accuracy across a held-out test set
- [ ] Add a 5th demo file specifically showing folder support
- [ ] Tune STS sample count if it performs worse than Speech/Arts

### Risky — probably skip

- Lowering `threshold_high` below 0.80 — increases auto-move rate but risks moving files incorrectly during demo
- Training on image files (`.jpg`, `.png`) — no text extraction, filename-only signal; not reliable enough
- Adding a 4th subject before the demo — reduces per-class training density and increases variance
