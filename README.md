# AI Assessment Platform

Web application for generating and delivering technical assessments. Administrators use an LLM (Groq) to create question sets from a language/topic catalog; participants take tests in the browser with optional in-browser Python execution (Pyodide) or a downloadable Jupyter Notebook for topics that require a live runtime environment.

Persistence is **PostgreSQL** (SQLAlchemy 2). The backend applies all schema migrations automatically on startup — no manual migration steps needed.

## Features

- **Admin portal**: Sign in with a configured password; generate assessments (MCQ, coding, subjective); manage catalog languages/topics; browse all assessments (language, topics, routing, timed flag); delete assessments; review participant submissions.
- **Participant portal**: Open a test with employee ID, name, and assessment ID — no account required for shared assessments.
- **Auto topic allocation**: Select multiple catalog topics with global MCQ/coding counts — the backend splits counts evenly across topics, generates per topic, and tags each question with `topic_name` for correct routing (no manual per-topic grid required).
- **Per-topic question allocation**: Optional admin mode with independent MCQ/coding/subjective counts per topic; one LLM call per topic either way when catalog topics are selected.
- **Notebook-aware routing**: Jupyter download/upload appears only when the assessment **expects notebook coding** (`notebook_expected`), not merely because a jupyter-modality topic is selected (e.g. MCQ-only on a tier-2 topic skips the notebook UI).
- **Pyodide coding questions**: In-browser Python execution with a full code editor. Participants write and run code without leaving the page.
- **Jupyter Notebook mode**: Coding on jupyter-modality topics is delivered as a downloadable `.ipynb` template. Participants solve locally and submit for LLM grading.
- **Mixed assessments**: Pyodide and Jupyter coding in one test; single **Submit answers** for in-browser work plus optional notebook upload in the same flow.
- **Timed assessments**: Optional countdown per participant; auto-submit in-browser answers at expiry; configurable grace period for notebook upload with auto-grade on attach.
- **Per-participant shuffle**: Deterministic question and MCQ option order from `assessment_id + employee_id`; display **Question N of M**; per-question feedback under each card after submit.
- **LLM grading**: All answers (MCQ, coding, subjective, notebook cells) are scored via Groq with per-question written feedback.
- **Code editor**: Tab indentation, `Ctrl+/` comment toggling, syntax highlighting, and per-question language override.

## Documentation

| Document | Description |
|----------|-------------|
| [docs/assessment-generation.md](docs/assessment-generation.md) | Auto vs per-topic allocation, `routing_flag`, `notebook_expected`, template 404/409 |
| [docs/timed-assessments.md](docs/timed-assessments.md) | Duration, grace period, attempts, enforcement |
| [docs/participant-experience.md](docs/participant-experience.md) | Shuffle, labels, submit flows, mixed/jupyter UI |

## Tech stack

| Layer | Stack |
|-------|--------|
| Backend | FastAPI, SQLAlchemy 2, PostgreSQL, PyJWT |
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
| `ADMIN_PASSWORD` | Admin portal password |
| `DATABASE_URL` | PostgreSQL URL, e.g. `postgresql+psycopg://postgres:postgres@127.0.0.1:5433/assesment` |

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

## Per-participant randomization (anti-cheating)

When a participant loads an assessment, they must enter their **employee ID** first. The API shuffles:

- **Question order** on the web UI (MCQ, Pyodide coding, subjective, Jupyter placeholders)
- **MCQ option order** (letters A/B/C/D follow the shuffled list; grading still uses the option text)

The shuffle seed is `assessment_id + employee_id` only (participant name is **not** used). The same employee ID always sees the same order on reload.

Participants see **Question 3 of 7** (position in their shuffled list), not internal `Q1` / `Q4` IDs. After submit, feedback appears **under each question card**.

**Not randomized:** Jupyter `.ipynb` template download order (canonical order for notebook coding tasks).

Admin preview and `GET /assessment/{id}/template` omit `employee_id` and return canonical order.

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
├── app.py                      # FastAPI routes and request validation
├── docs/                       # Detailed feature documentation
├── services/
│   ├── assessment_service.py   # LLM orchestration, per-topic/auto generation
│   ├── attempt_service.py      # Timed attempts, deadlines, submit guards
│   ├── auth_service.py
│   ├── catalog_service.py
│   ├── db_service.py           # PostgreSQL read/write, routing flag
│   ├── database.py             # Engine, session factory, idempotent migrations
│   ├── llm_service.py          # Groq wrappers for generation and grading
│   ├── models.py               # ORM (modality, routing_flag, timed columns)
│   ├── notebook_plan_service.py # notebook_expected, derive_per_topic_config
│   ├── notebook_service.py     # Jupyter parsing and cell grading
│   └── shuffle_service.py      # Per-participant shuffle
├── tests/
│   ├── test_notebook_plan_service.py
│   ├── test_attempt_service.py
│   └── test_shuffle_service.py
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── AssessmentTimerBar.jsx
│       │   ├── SimpleCodeEditor.jsx
│       │   └── PythonRunPanel.jsx
│       ├── hooks/useAssessmentTimer.js
│       └── pages/
│           ├── AdminPage.jsx
│           ├── AdminAssessmentsPage.jsx
│           ├── AdminCatalogPage.jsx
│           └── ClientPage.jsx
├── scripts/seed_sample_catalog.py
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
| `/admin/assessments` | List / delete assessments |
| `/admin/catalog` | Languages and topics (with modality) |
| `/admin/submissions` | Submission review |
| `/client` | Take assessment (Pyodide, Jupyter, mixed, timed) |

## API overview

| Endpoint | Auth | Description |
|----------|------|-------------|
| `POST /auth/login` | — | Admin password or client ID |
| `POST /generate-assessment` | Admin | Create assessment (`topic_names`, `per_topic_config`, `is_timed`, …) |
| `GET /admin/assessments` | Admin | List assessments (`routing_flag`, `is_timed`, …) |
| `DELETE /admin/assessments/{id}` | Admin | Delete assessment |
| `GET /assessment/{id}?employee_id=…` | Public* | Questions, `topic_modality`, `notebook_expected`, `timer` |
| `POST /submit-assessment` | Public* | Grade in-browser answers (`employee_id` for timed) |
| `GET /assessment/{id}/template` | Public* | Download `.ipynb` (404/409 per notebook plan) |
| `POST /submit-notebook-assessment` | Public* | Upload and grade `.ipynb` |

\*Shared assessments only without client token; client-scoped assessments require client JWT.

## Testing

```bash
source .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest tests/ -q
```

## Future roadmap

| Goal | Notes |
|------|--------|
| **MCQ code snippets as formatted blocks** | Render code in MCQ stems as syntax-highlighted blocks; optional separate `code` field from the LLM. |

## License

Private / assessment project — add a license if you distribute this code.
