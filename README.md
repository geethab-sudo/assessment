# AI Assessment Platform

Web application for generating and delivering technical assessments. Administrators use an LLM (Groq) to create question sets from a language/topic catalog; participants take tests in the browser with optional in-browser Python execution (Pyodide) or a downloadable Jupyter Notebook for topics that require a live runtime environment.

Persistence is **PostgreSQL** (SQLAlchemy 2). The backend applies all schema migrations automatically on startup — no manual migration steps needed.

## Features

- **Admin portal**: Sign in with a configured password; generate assessments (MCQ, coding, subjective); manage catalog languages/topics; browse all assessments (language, topics, date); delete assessments; review participant submissions.
- **Participant portal**: Open a test with employee ID, name, and assessment ID — no account required for shared assessments.
- **Pyodide coding questions**: In-browser Python execution with a full code editor. Participants write and run code without leaving the page.
- **Jupyter Notebook mode**: Topics that need a live runtime (live API calls, async HTTP, real DB sessions) are delivered as a downloadable `.ipynb` template. Participants solve it locally and submit the completed notebook for LLM grading.
- **Mixed assessments**: One assessment can contain both Pyodide and Jupyter questions side-by-side. A single **Submit answers** button handles both — in-browser questions are graded directly and the attached notebook is graded in the same request.
- **Per-topic question allocation**: Admins can set independent MCQ/coding/subjective counts per topic. The backend calls the LLM once per topic and tags every question with its originating topic, enabling correct per-question routing.
- **LLM grading**: All answers (MCQ, coding, subjective, notebook cells) are scored via Groq with per-question written feedback.
- **Code editor**: Tab indentation, `Ctrl+/` comment toggling, syntax highlighting, and per-question language override.

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
3. Click **Submit answers** — all questions are graded immediately and a score card with per-question feedback appears.

### Jupyter-only assessment

1. Open the participant page and load the assessment.
2. Click **Download .ipynb** to get the notebook template (one markdown question cell + one empty code cell per question).
3. Solve the notebook locally in JupyterLab / VS Code / Google Colab.
4. Select the completed `.ipynb` file using the file picker on the page.
5. Click **Submit answers** — the notebook is graded cell-by-cell and a score card with per-cell feedback appears.

### Mixed assessment

1. Open the participant page and load the assessment.
2. Answer MCQ questions in the web UI.
3. Write code for Pyodide topics directly in the in-browser terminal.
4. For Jupyter topics, a **"Jupyter Required"** banner lists which topics need the notebook. Click **Download .ipynb** to get the template; solve it locally.
5. Select the completed `.ipynb` file using the file picker at the bottom of the page.
6. Click **Submit answers** once — in-browser questions and the notebook are both submitted and graded in the same action.
7. Two result cards appear: one for in-browser questions, one for the Jupyter notebook.

> If you click Submit without attaching a notebook, a confirmation dialog warns you so you can cancel and attach it first.

## Per-participant randomization (anti-cheating)

When a participant loads an assessment, they must enter their **employee ID** first. The API shuffles:

- **Question order** on the web UI (MCQ, Pyodide coding, subjective, Jupyter placeholders)
- **MCQ option order** (letters A/B/C/D follow the shuffled list; grading still uses the option text)

The shuffle seed is `assessment_id + employee_id` only (participant name is **not** used, so spelling variations do not change the layout). The same employee ID always sees the same order on reload.

Participants see **Question 3 of 7** (position in their shuffled list), not internal `Q1` / `Q4` IDs. After submit, feedback appears **under each question card** (score + comment), not in one combined block. Admin preview and submissions review keep **Q1, Q2, Q3…** by `question_id` for debugging.

**Not randomized:** Jupyter `.ipynb` template download order (canonical order for coding tasks in the notebook).

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
| Packaging and virtual environments (venv) |

### Tier 2 — Applied Python

Some Tier 2 topics can be evaluated in-browser (`pyodide` modality); others require a live runtime and are delivered via Jupyter Notebook (`jupyter` modality).

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

Assessments are automatically routed based on the topics selected:

| `routing_flag` | Meaning | Participant experience |
|----------------|---------|----------------------|
| `pyodide` | All topics use in-browser execution | Regular questions + Pyodide terminal |
| `jupyter` | All topics require a live environment | Download `.ipynb` template → solve locally → submit |
| `mixed` | Mix of pyodide and jupyter topics | All questions shown; Pyodide terminal for pyodide coding questions; "Complete in Jupyter Notebook" placeholder for jupyter coding questions; download + submit panel included |

MCQ and subjective questions from jupyter-modality topics are always answered in the web UI — only **coding** questions from jupyter topics go into the downloadable notebook.

## Per-topic question allocation (Admin)

When generating an assessment with multiple catalog topics, admins can switch to **per-topic** allocation mode:

- Select a language and one or more topics.
- Switch to "Per-topic" distribution mode.
- Set independent MCQ / coding / subjective counts for each topic.
- On generation, the backend calls the LLM **separately for each topic**, tagging every question with its originating topic name.
- This enables correct routing: questions from `jupyter` topics are sent to the notebook; questions from `pyodide` topics use the in-browser terminal.

## Jupyter Notebook internals

### Template generation

`GET /assessment/{id}/template` builds a `.ipynb` with one markdown cell (question text) followed by one empty code cell (student answer) for each **coding** question from a jupyter-modality topic. MCQ and subjective questions from jupyter topics are excluded from the notebook — they are answered in the web UI.

### Notebook grading

`notebook_service.py` parses the submitted notebook and pairs each markdown question cell with the immediately following code cell:

```
[markdown: question text] → [code: student answer] → repeat
```

- Blank trailing code cells with no associated markdown question are silently skipped (Jupyter always appends an empty cell at the bottom).
- Each question/answer pair is graded individually by the LLM.
- A combined score and per-cell feedback string are stored as a submission row and returned to the participant.

## Code editor

The in-browser code editor (`SimpleCodeEditor`) provides a comfortable Python editing experience:

| Shortcut | Action |
|----------|--------|
| `Tab` | Insert 4-space indent (or indent selected lines) |
| `Shift+Tab` | Dedent selected lines |
| `Ctrl+/` / `Cmd+/` | Toggle `# ` comment on current line or all selected lines |
| Standard clipboard | Copy / paste works normally |

Syntax mode is set from the catalog language of the assessment and can be overridden per coding question via the language selector.

## Port conflicts

If another app already uses **8000** or **5173**, you may see the wrong API or UI.

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
├── services/
│   ├── assessment_service.py   # LLM orchestration, per-topic generation, routing
│   ├── auth_service.py
│   ├── catalog_service.py
│   ├── db_service.py           # PostgreSQL read/write, routing flag logic
│   ├── database.py             # Engine, session factory, idempotent migrations
│   ├── llm_service.py          # Groq wrappers for generation and grading
│   ├── models.py               # SQLAlchemy ORM (modality, routing_flag, topic_name)
│   ├── notebook_service.py     # Jupyter parsing, markdown↔code pairing, cell grading
│   └── shuffle_service.py      # Per-participant question/MCQ option shuffle
├── frontend/                   # React SPA (Vite)
│   └── src/
│       ├── components/
│       │   ├── SimpleCodeEditor.jsx   # Code editor (Tab, Ctrl+/, syntax highlight)
│       │   └── PythonRunPanel.jsx     # Pyodide execution panel
│       └── pages/
│           ├── AdminPage.jsx          # Generate assessment (per-topic allocation)
│           ├── AdminCatalogPage.jsx   # Manage languages and topics
│           └── ClientPage.jsx         # Take assessment (Pyodide + Jupyter mixed)
├── scripts/
│   ├── seed_sample_catalog.py         # Seed Python Tier 1/2, Java, Node.js catalog
│   └── cleanup_python_topics.py      # Remove legacy Python topics
├── docker-compose.yml          # PostgreSQL only
├── requirements.txt
└── .env.example
```

## Main routes (UI)

| Path | Description |
|------|-------------|
| `/` | Home |
| `/login/admin` | Admin sign-in |
| `/admin` | Generate assessment (per-topic or global allocation) |
| `/admin/assessments` | List / delete assessments |
| `/admin/catalog` | Languages and topics (with modality) |
| `/admin/submissions` | Submission review |
| `/client` | Take assessment (Pyodide, Jupyter, or mixed) |

## API overview

| Endpoint | Auth | Description |
|----------|------|-------------|
| `POST /auth/login` | — | Admin password or client ID |
| `POST /generate-assessment` | Admin | Create assessment via LLM (supports `per_topic_config`) |
| `GET /admin/assessments` | Admin | List assessments (includes `routing_flag`) |
| `DELETE /admin/assessments/{id}` | Admin | Delete assessment |
| `GET /assessment/{id}?employee_id=…` | Public* | Questions with `topic_modality`; shuffled per employee ID |
| `POST /submit-assessment` | Public* | Submit and grade in-browser questions (Pyodide + MCQ) |
| `GET /assessment/{id}/template` | Public* | Download `.ipynb` template (jupyter coding questions only) |
| `POST /submit-notebook-assessment` | Public* | Upload and grade completed `.ipynb` |

\*Shared assessments only without client token; client-scoped assessments require client JWT.

## Future roadmap

| Goal | Notes |
|------|--------|
| **MCQ code snippets as formatted blocks** | When a generated MCQ embeds Python (or other code) in the question stem, render it in a syntax-highlighted code block—not as one long inline sentence. Detect code in stems at display time and/or steer the LLM prompt to emit a separate `code` field. |

## License

Private / assessment project — add a license if you distribute this code.
