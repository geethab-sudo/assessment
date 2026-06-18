# AI Assessment Platform

Web application for generating and delivering technical assessments. Administrators use an LLM (Groq) to create question sets from a language/topic catalog; participants take tests in the browser with optional in-browser Python execution (Pyodide) or a downloadable Jupyter Notebook for topics that require a live runtime environment.

Persistence is **PostgreSQL** (SQLAlchemy 2). The backend applies all schema migrations automatically on startup — no manual migration steps needed.

## Features

- **Admin portal**: Sign in with a configured password; generate assessments (MCQ, coding, subjective); **review and edit generated questions before saving**; browse the **question bank** (stats, filters, sort by failure rate); manage catalog languages/topics; browse all assessments with filter by Assessment ID and language, sort by date; delete assessments; review participant submissions with date display, sort by date, and filter by employee ID or assessment ID.
- **Participant portal**: Open a test with employee ID, name, and assessment ID — no account required for shared assessments.
- **Tier 1 evaluation presets**: One-click **Beginner** / **Intermediate** / **Advanced** Python Tier 1 combos (25 questions: 15 MCQ + 10 coding) with editable per-topic counts and suggested timed duration (60 / 90 / 120 min).
- **Question Bank**: Every generated and confirmed assessment question is automatically stored in a global bank, recording analytical stats (`times_used`, `times_correct`, `times_wrong`).
- **Auto topic allocation**: Select multiple catalog topics with global MCQ/coding counts — the backend splits counts evenly across topics, generates per topic, and tags each question with `topic_name` for correct routing (no manual per-topic grid required).
- **Per-topic question allocation**: Optional admin mode with independent MCQ/coding/subjective counts per topic; one LLM call per topic either way when catalog topics are selected.
- **Notebook-aware routing**: Jupyter download/upload appears only when the assessment **expects notebook coding** (`notebook_expected`), not merely because a jupyter-modality topic is selected (e.g. MCQ-only on a tier-2 topic skips the notebook UI).
- **Pyodide coding questions**: In-browser Python execution with a full code editor. Participants write and run code without leaving the page.
- **Jupyter Notebook mode**: Coding on jupyter-modality topics is delivered as a downloadable `.ipynb` template. Participants solve locally and submit for LLM grading.
- **Mixed assessments**: Pyodide and Jupyter coding in one test; single **Submit answers** for in-browser work plus optional notebook upload in the same flow.
- **Timed assessments**: Optional countdown per participant; auto-submit in-browser answers at expiry; configurable grace period for notebook upload with auto-grade on attach.
- **Per-participant shuffle**: Deterministic question and MCQ option order from `assessment_id + employee_id`; display **Question N of M**; per-question feedback under each card after submit.
- **Clipboard restrictions (participant)**: MCQ code snippets cannot be copied during a test; paste is disabled in coding editors (Pyodide / shell) so answers must be typed. Admin preview pages are unaffected.
- **LLM grading**: Coding, subjective, and notebook answers are scored via Groq with per-question written feedback. **MCQ answers are graded locally** (string match against the stored correct answer) — no LLM call on submit.
- **MCQ code formatting**: Embedded snippets in MCQ stems (inline, fenced, or `code_snippet`) are split into prose + a dark syntax-highlighted block. One-liners are expanded (`if`/`with`/`class`/`def` bodies, semicolon chains). Mixed stems like “class … What is the output of the following code: print(…)” become a question line plus formatted code. Write/implement prompts stay prose-only.
- **Code editor**: Tab indentation, `Ctrl+/` comment toggling, syntax highlighting, and per-question language override.
- **Shell-style coding (venv topic)**: Catalog topics can set `coding_editor_language` to `shell` or `powershell` so coding answers use a Bash/PowerShell editor only (no Pyodide console) — used for **Packaging and virtual environments (venv)** in Python Tier 1.
- **Re-submission guard**: Participants cannot submit the same assessment twice — enforced server-side for both timed and untimed assessments.
- **Session-scoped auth tokens**: Admin and client JWTs are stored in `sessionStorage` (tab-scoped), not `localStorage`, reducing XSS exposure across tabs.
- **Timer stops on submit**: The countdown bar is hidden and the interval cleared as soon as the participant's submission succeeds; auto-expire callbacks no longer fire after that point.
- **Admin question review**: After generation, admins land on a review page to edit question text, MCQ options, correct answer, and code snippets (Tab inserts 4-space indent). Coding questions do not show a code-snippet field. Nothing is written to the DB until **Confirm & save**.
- **Participant feedback report (PDF)**: After submitting in-browser answers, the results section shows a **topic summary table** (topic, questions, score, average %) and a **Download report (PDF)** button. The printable report includes per-question results, feedback, and the same topic rollup. Printing uses a hidden iframe (no pop-up blocker). Covers **MCQ and Pyodide coding only** — Jupyter notebook grading is excluded for now.

## How do we use LLM calls? Is it expensive?

This section is for engineers who care about **token usage and API cost**, not UI details.

### When the LLM is called

| Stage | What happens | LLM calls |
|-------|----------------|-----------|
| **Assessment generation** (admin) | Groq generates the question set from topic/level/counts. May be one call per catalog topic when using per-topic allocation. | **Yes** — proportional to topics × generation retries |
| **Admin review** | Admin edits questions on `/admin/review`; confirm persists to PostgreSQL. | **No** |
| **Participant load** | Questions are read from the DB; shuffle is deterministic (no LLM). | **No** |
| **Submit — MCQ** | Answer compared to stored `correct_answer` (case-insensitive string match). Wrong-answer “feedback” is the stored correct text, not a new model response. | **No** |
| **Submit — coding / subjective** | Each answer is sent to Groq once for score + written feedback. | **Yes** — **one call per coding/subjective question** |
| **Submit — Jupyter notebook** | Each paired markdown/code cell is graded via Groq. | **Yes** — **one call per graded notebook cell** |
| **Download feedback report** | `GET /assessment/{id}/report` joins stored submissions with question metadata; client renders HTML and prints. | **No** |

### Cost intuition (examples)

- **10 MCQ only** → generation LLM cost only; **0** LLM calls on submit.
- **5 MCQ + 3 coding** → **3** LLM calls on submit (coding only).
- **Mixed + notebook** → in-browser coding/subjective calls + one call per notebook coding cell when the `.ipynb` is graded.

### Design choices that keep cost down

1. **MCQ is source-of-truth grading** — The value saved at confirm time (including admin edits on the review page) is what submission uses. We do **not** re-ask the LLM whether “Fish” is correct for an MCQ.
2. **Generation is separate from grading** — Pay for generation once per assessment; grading cost scales with **non-MCQ** answers submitted.
3. **Retries only where JSON breaks** — Question generation may retry on malformed JSON from Groq; grading does not double-call MCQs.

Implementation references: `_is_answer_correct` in `services/assessment_service.py` (MCQ branch), `llm_service.py` (generation + grading).

## Documentation

| Document | Description |
|----------|-------------|
| [docs/assessment-generation.md](docs/assessment-generation.md) | Auto vs per-topic allocation, `routing_flag`, `notebook_expected`, template 404/409 |
| [docs/tier1-presets.md](docs/tier1-presets.md) | Beginner / Intermediate / Advanced Python Tier 1 preset combos |
| [docs/timed-assessments.md](docs/timed-assessments.md) | Duration, grace period, attempts, enforcement |
| [docs/participant-experience.md](docs/participant-experience.md) | Shuffle, labels, submit flows, mixed/jupyter UI |

## Tech stack

| Layer | Stack |
|-------|--------|
| Backend | FastAPI, SQLAlchemy 2, PostgreSQL, PyJWT, bcrypt |
| Frontend | React 18, Vite 6, React Router |
| LLM | Groq (OpenAI-compatible API) |
| In-browser Python | Pyodide |

## Prerequisites

- Python 3.11+ (3.13 tested)
- Node.js 18+
- PostgreSQL (local install or Docker via `docker-compose.yml`)
- [Groq API key](https://console.groq.com/keys)

## Quick start

### 1. Environment

```bash
cp .env.example .env
```

Edit `.env` and set at minimum:

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` | Groq API key |
| `JWT_SECRET` | Long random string for JWT signing |
| `ADMIN_PASSWORD` | Admin portal password — plain text or a bcrypt hash (recommended for production) |
| `DATABASE_URL` | PostgreSQL URL, e.g. `postgresql+psycopg://postgres:postgres@127.0.0.1:5433/assesment` |

**Generating a bcrypt hash for `ADMIN_PASSWORD`** (recommended for production):

```bash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
```

Paste the output (`$2b$12$...`) as the value of `ADMIN_PASSWORD`. Plain-text values continue to work for local development.

### 2. Database (Docker)

```bash
docker compose up -d
```

Default host port is **5433** (see `POSTGRES_PORT` in `.env.example`) to avoid clashing with a local Postgres on 5432.

Tables and all schema columns are created automatically on API startup (`init_db()`). Migrations are idempotent — safe to restart at any time.

### 3. Seed catalog

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/seed_sample_catalog.py
```

Populates Python (Tier 1 + Tier 2), Java, Node.js, and general English CS topics. The script is **idempotent** — safe to re-run.

### 3b. Seed demo students (optional)

```bash
python scripts/seed_demo_students.py
```

Creates a shared **Tier 1 Beginner Python** assessment (`ASM-DEMO0001`) and submissions for three demo participants:

| Employee ID | Name | Profile |
|-------------|------|---------|
| `C001` | María | Strong (~91%) |
| `C002` | Kumar | Regular (~68%; some weak topics) |
| `C003` | Oscar | Struggling (~42%; many weak topics) |

Safe to re-run when moving to a fresh database. Questions are stored in
`scripts/demo_questions_snapshot.json` (real Tier 1 bank content). Re-capture from a
live bank with `python scripts/seed_demo_students.py --refresh-snapshot`. See the script
header for the assessment ID and usage notes.

### 4. Backend

```bash
source .venv/bin/activate
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

- API: http://127.0.0.1:8000  
- Docs: http://127.0.0.1:8000/docs  
- Health: http://127.0.0.1:8000/health  

### 5. Frontend

```bash
cd frontend
npm install
npm run dev
```

- UI: http://localhost:5173 (Vite default)  
- Browser calls `/api/*`, proxied to `http://127.0.0.1:8000` (override with `VITE_PROXY_TARGET` if needed).

### 6. Sign in

1. Open http://localhost:5173/login/admin  
2. Use the password from `ADMIN_PASSWORD` in `.env`

## Participant workflow

### Pyodide-only assessment

1. Open the participant page and enter employee ID, name, and assessment ID.
2. Answer MCQ questions and write/run Python code in the in-browser Pyodide terminal.
3. Click **Submit answers** — all questions are graded immediately and per-question feedback appears under each card.
4. Review the **Topic summary** table in the results section (loaded automatically from the report API).
5. Click **Download report (PDF)** — the browser print dialog opens; choose **Save as PDF**. Same content as the on-screen summary plus full per-question detail (MCQ + in-browser coding only; Jupyter not included yet).

### Jupyter-only assessment (with notebook coding)

1. Open the participant page and load the assessment (`notebook_expected: true`).
2. Click **Download .ipynb** for the template (jupyter **coding** questions only).
3. Solve locally in JupyterLab / VS Code / Colab.
4. Upload the completed `.ipynb` and click **Submit notebook**.

If the assessment has jupyter topics but **no coding** on those tiers, the UI stays in-browser only (no template/download).

### Mixed assessment

1. Load the assessment; answer MCQ and Pyodide coding in the web UI.
2. When `notebook_expected` is true, use the **Jupyter Required** banner to download the template; jupyter coding items show a placeholder instead of Pyodide.
3. Attach the completed `.ipynb` (optional until submit).
4. Click **Submit answers** once — in-browser questions and the notebook are graded together when a file is attached.

> Submitting without a notebook while one is expected shows a confirmation dialog.

See [docs/participant-experience.md](docs/participant-experience.md) for shuffle, labels, and timed behavior.

## Participant feedback report

After an in-browser submit (`POST /submit-assessment`), the participant page:

1. Fetches `GET /assessment/{id}/report?employee_id=…` (no LLM — reads submission rows from PostgreSQL).
2. Displays a **topic summary** table: topic name, question count, total score, average %.
3. Offers **Download report (PDF)** — `reportRenderer.js` builds print-friendly HTML and triggers `window.print()` via a hidden iframe (avoids pop-up blockers).

The report includes:

| Section | Content |
|---------|---------|
| Header | Participant name, employee ID, assessment ID, submission time |
| Overall | Average score and questions graded |
| Topic summary | Aggregated scores per catalog `topic_name` (or **General** when untagged) |
| Question details | Stem, code snippet, your answer, score, feedback per question |

**Scope (v1):** MCQ, coding, and subjective questions submitted through the web UI. Jupyter notebook rows (`question_id=notebook`, `routing_flag=jupyter`) and jupyter-modality coding placeholders are excluded.

**Backend:** `services/report_service.py` (`build_report`, `aggregate_topic_summary`). **Frontend:** `frontend/src/lib/reportRenderer.js`, results UI in `ClientPage.jsx`.

## Per-participant randomization (anti-cheating)

When a participant loads an assessment, they must enter their **employee ID** first. The API shuffles:

- **Question order** on the web UI (MCQ, Pyodide coding, subjective, Jupyter placeholders)
- **MCQ option order** (letters A/B/C/D follow the shuffled list; grading still uses the option text)

The shuffle seed is `assessment_id + employee_id` only (participant name is **not** used). The same employee ID always sees the same order on reload.

Participants see **Question 3 of 7** (position in their shuffled list), not internal `Q1` / `Q4` IDs. After submit, feedback appears **under each question card**.

**Not randomized:** Jupyter `.ipynb` template download order (canonical order for notebook coding tasks).

Admin preview and `GET /assessment/{id}/template` omit `employee_id` and return canonical order.

### Clipboard restrictions (participant page)

On `/client`, while a test is in progress:

| Area | Behaviour |
|------|-----------|
| MCQ / stem **code snippets** | Copy, cut, and context menu blocked; `user-select: none` on snippet blocks |
| **Coding editor** (feeds Pyodide Execute) | Paste blocked (`Ctrl+V`, `Shift+Insert`, drag-drop) — participants must type code |

Implemented in `frontend/src/lib/assessmentClipboard.js`, `McqCodeBlock.jsx`, `SimpleCodeEditor.jsx`, and `ClientPage.jsx`. This is a **browser-side deterrent** only (not a cryptographic guarantee).

## Python catalog: Tier 1 and Tier 2 topics

### Tier 1 — Core Python (evaluated in-browser via Pyodide)

| Topic |
|-------|
| Data Structures & Manipulation (Lists, Sets, Strings) |
| Logic & Flow Control (Conditionals, Loops, Comprehensions) |
| OOP Basics (Classes, Methods, Encapsulation) |
| Functions & Dictionaries (Nested lookups, signatures, defaults) |
| Error Handling (Basic try-except, raising exceptions) |
| Type Hinting & Annotations (Typing module, static analysis support) |
| Built-in Iterators & Utilities (enumerate, zip, any, all) |
| Basic File I/O & Context Managers (with open statements) |
| Modules, Namespaces & Imports (Absolute/Relative, Circular imports) |
| Generators & Iterables (yield, generator expressions) |
| Testing (unittest, pytest) |
| Packaging and virtual environments (venv) — coding answers use **Bash** or **PowerShell** editor highlighting, not Python |

### Tier 2 — Applied Python

Some Tier 2 topics use in-browser Pyodide; others require a live runtime and use Jupyter (`jupyter` modality) for **coding** questions.

| Topic | Modality |
|-------|----------|
| Resilience & Reliability: Retry decorators, exponential backoff, jitter | Pyodide |
| Security: PII/Credit card Regex redaction, AuthN vs AuthZ | Pyodide |
| LLM Output Validation & Repair: Parsing and validating broken JSON | Pyodide |
| Observability: Dictionary manipulation for Trace/Correlation IDs | Pyodide |
| Performance: Python Data Model `__slots__` memory footprint | Pyodide |
| LLM Integration: Live API calls to the Google Gemini API | **Jupyter** |
| Data & Persistence Patterns: Real SQLAlchemy sessions, transactions, cache-aside | **Jupyter** |
| Real Async Concurrency: Live HTTP endpoints with `httpx.AsyncClient` | **Jupyter** |

## Assessment routing

### `routing_flag` (topic mix)

| `routing_flag` | Meaning |
|----------------|---------|
| `pyodide` | All selected topics are pyodide-modality |
| `jupyter` | All selected topics are jupyter-modality |
| `mixed` | Both modalities in the topic selection |

### `notebook_expected` (participant notebook UI)

| Condition | Notebook download / upload |
|-----------|----------------------------|
| `notebook_expected: true` | At least one **coding** question configured on a jupyter-modality topic |
| `notebook_expected: false` | No jupyter coding (e.g. MCQ-only tier-2, or pyodide-only assessment) |

MCQ and subjective questions on jupyter topics are always answered in the web UI. Only **coding** on jupyter topics goes into the `.ipynb` template.

Generation fails with **400** if jupyter coding was configured but no notebook coding rows were produced — regenerate with adjusted counts.

Details: [docs/assessment-generation.md](docs/assessment-generation.md).

## Per-topic and auto allocation (Admin)

**Auto (default with multiple catalog topics):**

- Select language and topics; set global MCQ / coding / subjective totals.
- Backend derives per-topic counts (`derive_per_topic_config`) and calls the LLM once per topic.
- Every question is stored with `topic_name` for routing.

**Per-topic mode:**

- Switch to “Per-topic” distribution and set counts per topic explicitly.
- Same per-topic LLM loop; routing and notebook rules are unchanged.

## Jupyter Notebook internals

### Template generation

`GET /assessment/{id}/template`:

- **404** if `notebook_expected` is false.
- **409** if notebook is expected but no jupyter coding questions exist in storage.
- **200** — `.ipynb` with one markdown cell + one empty code cell per jupyter coding question.

### Notebook grading

`notebook_service.py` pairs each markdown question cell with the following code cell, grades via LLM, and stores submission rows. Blank trailing cells are skipped.

## Timed assessments

Admins enable **Timed assessment** when generating:

- **Duration (minutes)** — minimum 1; no fixed upper cap (short durations allowed for testing).
- **Notebook grace (minutes)** — default 5; applies when `notebook_expected` is true.

The timer starts when the participant loads the test with employee ID. At main expiry, in-browser answers auto-submit; notebook upload remains until grace ends (auto-grade on file select during grace).

See [docs/timed-assessments.md](docs/timed-assessments.md).

## Code editor

| Shortcut | Action |
|----------|--------|
| `Tab` | Insert 4-space indent (or indent selected lines) |
| `Shift+Tab` | Dedent selected lines |
| `Ctrl+/` / `Cmd+/` | Toggle `# ` comment on current line or selection |
| Standard clipboard | Copy / paste |

Syntax mode follows the assessment catalog language; participants can override per coding question.

### Shell commands (venv / packaging topic)

For topics with `coding_editor_language` set on the catalog row (seeded for **Tier 1 - Packaging and virtual environments (venv)**):

- Coding questions show a **Shell commands** editor (full width) with Bash or PowerShell syntax highlighting.
- Participants switch **Bash / sh** vs **PowerShell** via the Shell dropdown; there is no in-browser terminal or Execute button.
- Answers are shell command text, graded by the LLM on submit (generation prompts steer away from Python scripts for venv setup).

After pulling this feature, re-run `python scripts/seed_sample_catalog.py` so existing DB topics get `coding_editor_language: shell`.

## Port conflicts

If another app already uses **8000** or **5173**:

- Confirm the API: `curl -s http://127.0.0.1:8000/openapi.json` should report title **AI Assessment API**.
- Run the backend on another port, e.g. `uvicorn app:app --reload --port 8010`, then:

  ```bash
  cd frontend && VITE_PROXY_TARGET=http://127.0.0.1:8010 npm run dev -- --port 5174
  ```

## Production build (frontend)

```bash
cd frontend
npm run build
npm run preview
```

Serve `frontend/dist` behind your reverse proxy and point `/api` to the FastAPI service.

## Project layout

```
assessment/
├── app.py                      # FastAPI routes, UUID validation, request models
├── docs/                       # Detailed feature documentation
├── services/
│   ├── assessment_service.py   # LLM orchestration: _generate_rows_*, _compute_routing_flag, build_notebook_template
│   ├── attempt_service.py      # Timed attempts, deadlines, TimedAssessmentError
│   ├── auth_service.py         # JWT + bcrypt-aware ADMIN_PASSWORD verification
│   ├── catalog_service.py
│   ├── db_service.py           # PostgreSQL persistence; routing_flag accepted as param (not re-derived)
│   ├── database.py             # Engine, session factory, idempotent migrations
│   ├── llm_service.py          # Groq wrappers for generation and grading
│   ├── models.py               # ORM (modality, routing_flag, timed columns)
│   ├── notebook_plan_service.py # notebook_expected, derive_per_topic_config
│   ├── notebook_service.py     # Jupyter parsing and cell grading
│   ├── report_service.py       # Participant feedback report (in-browser questions)
│   ├── question_stem.py        # Stem parsing/prettification (split_stem_for_display)
│   └── shuffle_service.py      # Per-participant shuffle
├── tests/
│   ├── test_assessment_service_unit.py  # 26 unit tests for refactored helpers
│   ├── test_attempt_service.py
│   ├── test_notebook_plan_service.py
│   ├── test_question_stem.py
│   ├── test_shuffle_service.py
│   ├── test_tier1_presets.py
│   ├── test_report_service.py
│   ├── test_auth_api.py
│   ├── test_openapi.py
│   └── test_security.py
├── frontend/
│   └── src/
│       ├── api.js              # apiFetch; JWT stored in sessionStorage (tab-scoped)
│       ├── components/
│       │   ├── AssessmentTimerBar.jsx
│       │   ├── JupyterWorkspacePanel.jsx  # Pure-jupyter 2-step download/upload panel
│       │   ├── McqCodeBlock.jsx           # Syntax-highlighted code block (HTML-escaped)
│       │   ├── MixedNotebookPanel.jsx     # Mixed-routing compact upload + JupyterRequiredBanner
│       │   ├── Pagination.jsx             # Reusable admin table pagination
│       │   ├── PythonRunPanel.jsx
│       │   ├── SimpleCodeEditor.jsx
│       │   └── TimerExpiredBanner.jsx     # Grace-period notification bar
│       ├── hooks/useAssessmentTimer.js  # paused option stops ticker + callbacks after submit
│       ├── lib/
│       │   ├── assessmentClipboard.js # Block copy (snippets) / paste (editors) on client
│       │   ├── codeHighlight.js       # escapeHtml + token highlighters
│       │   ├── resolveQuestionStem.js # Pass-through (server pre-splits prose/code)
│       │   ├── reportRenderer.js      # Report HTML + iframe print (Save as PDF)
│       │   ├── shellEditor.js
│       │   └── tier1Presets.js
│       └── pages/
│           ├── AdminPage.jsx             # Generate → preview (no DB write)
│           ├── AdminReviewPage.jsx       # Edit questions; Confirm & save
│           ├── AdminAssessmentsPage.jsx  # Filter by ID/language, sort by date
│           ├── AdminCatalogPage.jsx
│           ├── AdminSubmissionsPage.jsx  # Formatted dates, sort, employee/assessment filter
│           └── ClientPage.jsx
├── scripts/seed_sample_catalog.py
├── scripts/seed_demo_students.py      # Demo C001–C003 + ASM-DEMO0001
├── scripts/demo_questions_snapshot.json  # Real Tier 1 questions for demo seed
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

## Main routes (UI)

| Path | Description |
|------|-------------|
| `/` | Home |
| `/login/admin` | Admin sign-in |
| `/admin` | Generate assessment (auto, per-topic, timed options) |
| `/admin/review` | Review and edit generated questions before saving |
| `/admin/assessments` | List / delete assessments (filter by ID, language; sort by date) |
| `/admin/catalog` | Languages and topics (with modality) |
| `/admin/question-bank` | Browse question bank — filter, sort by % wrong, % correct, or times used |
| `/admin/employee-report/:employeeId` | Employee skills progress report (print/PDF) |
| `/client/my-report` | Participant self-service skills report |
| `/client/improve` | Help me improve — weak areas practice (bank-only) |
| `/admin/submissions` | Submission review — formatted dates, sort by date, filter by employee / assessment ID |
| `/client` | Take assessment (Pyodide, Jupyter, mixed, timed) |

## API overview

| Endpoint | Auth | Description |
|----------|------|-------------|
| `POST /auth/login` | — | Admin password or client ID |
| `POST /generate-assessment` | Admin | Create assessment directly (legacy; still available) |
| `POST /admin/preview-questions` | Admin | Generate questions for review — **no DB write** |
| `POST /admin/confirm-assessment` | Admin | Persist admin-reviewed question list & upsert to Question Bank |
| `PATCH /admin/assessment/{id}/question/{qid}` | Admin | Patch one question on a saved assessment |
| `GET /admin/assessments` | Admin | List assessments (`routing_flag`, `is_timed`, …) |
| `DELETE /admin/assessments/{id}` | Admin | Delete assessment |
| `GET /admin/question-bank` | Admin | Browse the reusable question bank and view correctness stats |
| `GET /admin/question-bank/availability` | Admin | Check bank availability by topics and difficulty before generation |
| `GET /admin/employee-report?employee_id=` | Admin | Cross-assessment skills progress report (JSON) |
| `GET /client/employee-profile?employee_id=&scope=` | Public | Topic performance profile for improvement flows |
| `GET /client/my-report?employee_id=&period=` | Public | Shippable skills progress report (JSON) |
| `POST /client/improvement/weak-areas` | Public | Bank-only practice assessment on weak topics (last 3 assessments) |
| `POST /client/improvement/new-areas` | Public | Bank-only practice on unexplored catalog topics (full history) |
| `GET /assessment/{id}?employee_id=…` | Public* | Questions, `topic_modality`, `notebook_expected`, `timer` |
| `GET /assessment/{id}/report?employee_id=…` | Public* | Feedback report JSON (MCQ + Pyodide coding; no Jupyter) |
| `POST /submit-assessment` | Public* | Grade in-browser answers (`employee_id` for timed) |
| `GET /assessment/{id}/template` | Public* | Download `.ipynb` (404/409 per notebook plan) |
| `POST /submit-notebook-assessment` | Public* | Upload and grade `.ipynb` |

\*Shared assessments only without client token; client-scoped assessments require client JWT.

## Testing

Run from the **project root** (`assessment/`), not from inside `tests/`:

```bash
source .venv/bin/activate
pip install -r requirements.txt pytest

# All tests (93 total)
python -m pytest tests/ -q

# One file (pytest)
python -m pytest tests/test_question_stem.py -q

# One file (stdlib unittest — also works)
python -m unittest tests.test_question_stem -v
```

Do not run `python tests/test_question_stem.py` unless you use `python -m unittest tests.test_question_stem` from the repo root; plain script execution needs the project root on `PYTHONPATH`.

| Test file | Coverage |
|-----------|----------|
| `test_assessment_service_unit.py` | `create_assessment` helpers, routing flag, notebook template builder, row normalization |
| `test_question_stem.py` | Stem parsing, inline/fenced code extraction, compound-statement prettification |
| `test_tier1_presets.py` | Preset totals, topic names, suggested durations |
| `test_shuffle_service.py` | Per-participant shuffle determinism, MCQ option ordering |
| `test_attempt_service.py` | Timed config validation, deadline enforcement, `TimedAssessmentError` |
| `test_notebook_plan_service.py` | Per-topic config derivation, notebook plan logic |
| `test_report_service.py` | Topic rollup and in-browser report building (Jupyter excluded) |

## Security notes

| Concern | Mitigation |
|---------|------------|
| `ADMIN_PASSWORD` storage | Store as a bcrypt hash (`$2b$...`) in `.env`; plain-text fallback for local dev |
| JWT tokens | Stored in `sessionStorage` (tab-scoped); cleared on tab close |
| Public route UUID injection | `_require_valid_assessment_id` validates UUID format on all `assessment_id` path params |
| MCQ code snippets | `dangerouslySetInnerHTML` only after `escapeHtml` runs inside `highlightForLanguage` |
| `GROQ_API_KEY` / `JWT_SECRET` | Never committed; loaded from `.env` via `python-dotenv` |

## Future roadmap

| Goal | Notes |
|------|--------|
| *(none queued)* | Add items here as new product goals are agreed. |

## License

Private / assessment project — add a license if you distribute this code.
