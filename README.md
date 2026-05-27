# AI Assessment Platform

Web application for generating and delivering technical assessments. Administrators use an LLM (Groq) to create question sets from a language/topic catalog; participants take tests in the browser with optional in-browser Python execution (Pyodide) or a downloadable Jupyter Notebook for topics that require a live runtime environment.

Persistence is **PostgreSQL** (SQLAlchemy). Legacy CSV storage under `data/` has been removed.

## Features

- **Admin**: Sign in with a configured password; generate assessments (MCQ, coding, subjective); manage catalog languages/topics; browse assessments (language, topics, added date); delete assessments; review submissions.
- **Participant**: Open a test with employee ID, name, and assessment ID (no account required for shared assessments).
- **Grading**: Answers scored via Groq with per-question feedback; MCQ correctness uses stored answers when applicable. Notebook submissions are graded cell-by-cell.
- **Coding questions**: Code editor with catalog language selection; run Python in the browser via Pyodide.
- **Jupyter Notebook mode**: Topics that require a live environment (e.g. live API calls, async HTTP, real database sessions) are delivered as a downloadable `.ipynb` template. Participants solve it locally and upload the completed notebook for LLM grading.
- **Mixed assessments**: A single assessment can contain both in-browser (Pyodide) questions and Jupyter-required questions side-by-side.
- **Per-topic question allocation**: Admins can set independent MCQ/coding/subjective counts for each topic in one assessment, and the backend generates questions per topic (one LLM call per topic) so each question is tagged to its originating topic.

## Tech stack

| Layer | Stack |
|-------|--------|
| Backend | FastAPI, SQLAlchemy 2, PostgreSQL, PyJWT |
| Frontend | React 18, Vite 6, React Router |
| LLM | Groq (OpenAI-compatible API) |

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

Tables are created automatically on API startup (`init_db()`). All schema migrations (new columns for modality, routing, notebook storage, topic attribution) are applied idempotently on each startup — no manual migration steps needed.

### 3. Seed catalog

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/seed_sample_catalog.py
```

The seed script populates the catalog with Python topics (Tier 1 and Tier 2), Java, Node.js, and general English CS topics. It is **idempotent** — safe to re-run; existing rows are updated, not duplicated.

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

## Python catalog: Tier 1 and Tier 2 topics

The `py` language catalog has been expanded and divided into two tiers:

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
| `jupyter` | All topics require a live environment | Download `.ipynb` template → solve locally → upload |
| `mixed` | Mix of pyodide and jupyter topics | All questions shown; Pyodide terminal for pyodide coding questions; "Complete in Jupyter Notebook" placeholder for jupyter coding questions; download + upload panel displayed |

MCQ and subjective questions from jupyter-modality topics are always answered in the web UI — only **coding** questions from jupyter topics go into the downloadable notebook.

## Per-topic question allocation (Admin)

When generating an assessment with multiple catalog topics, admins can switch to **per-topic** allocation mode:

- Select a language and one or more topics.
- Switch to "Per-topic" distribution mode.
- Set independent MCQ / coding / subjective counts for each topic.
- On generation, the backend calls the LLM **separately for each topic**, tagging every question with its originating topic name.
- This enables correct routing: questions from `jupyter` topics are sent to the notebook; questions from `pyodide` topics use the in-browser terminal.

## Jupyter Notebook workflow

### Generating a notebook template

When an assessment contains jupyter-modality topics, a **Download .ipynb** button appears on the participant page. The template is generated by `GET /assessment/{id}/template` and contains only the coding questions from jupyter topics (one Markdown cell with the question, one empty code cell for the answer).

### Submitting a completed notebook

For **mixed** assessments, the participant selects their solved `.ipynb` file via the file picker on the assessment page, then clicks **Submit answers** once — the in-browser questions and the notebook are graded in the same request. No separate upload button is needed.

For **jupyter-only** assessments, the upload is also triggered by the single Submit button.

The backend (`notebook_service.py`) pairs each markdown question cell with the immediately following code cell (the template structure is `[markdown: question] → [code: answer] → repeat`). Blank trailing code cells with no associated question are skipped automatically. Each pair is graded individually by the LLM; a combined score and per-cell feedback are returned and stored as a submission row.

## Code editor improvements

- **Python syntax highlighting** via Monaco language mapping (`monacoLanguageMap.js`).
- **Copy/paste support** and **Tab key indentation** in the in-browser code editor (`SimpleCodeEditor`).
- **Comment toggling** (`Ctrl+/` on Windows/Linux, `Cmd+/` on macOS): selects the current line (or all selected lines) and toggles the `# ` prefix, preserving indentation and detecting mixed-comment state.
- Language override selector per coding question so participants can switch syntax mode independently of the assessment default.

## Port conflicts

If another app already uses **8000** or **5173**, you may see the wrong API or UI.

- Confirm the API: `curl -s http://127.0.0.1:8000/openapi.json` should report title **AI Assessment API** and include `/auth/login`.
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
├── app.py                      # FastAPI routes and validation
├── services/
│   ├── assessment_service.py   # LLM orchestration, per-topic generation
│   ├── auth_service.py
│   ├── catalog_service.py
│   ├── db_service.py           # PostgreSQL read/write, routing flag logic
│   ├── database.py             # Engine, session, idempotent migrations
│   ├── llm_service.py
│   ├── models.py               # SQLAlchemy ORM (incl. modality, routing_flag, topic_name)
│   └── notebook_service.py     # Jupyter notebook parsing, cell grading
├── frontend/                   # React SPA
│   └── src/
│       ├── components/
│       │   └── SimpleCodeEditor.jsx   # Monaco-based editor (Tab, copy/paste)
│       └── pages/
│           ├── AdminPage.jsx          # Generate assessment (per-topic allocation)
│           ├── AdminCatalogPage.jsx   # Manage languages and topics
│           └── ClientPage.jsx         # Take assessment (Pyodide + Jupyter mixed)
├── scripts/
│   ├── seed_sample_catalog.py         # Seed Python Tier 1/2, Java, Node.js catalog
│   └── cleanup_python_topics.py      # Standalone script to remove legacy Python topics
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
| `GET /assessment/{id}` | Public* | Questions with `topic_modality` per question |
| `POST /submit-assessment` | Public* | Submit and grade (Pyodide questions) |
| `GET /assessment/{id}/template` | Public* | Download `.ipynb` template (jupyter coding questions only) |
| `POST /submit-notebook-assessment` | Public* | Upload and grade completed `.ipynb` |

\*Shared assessments only without client token; client-scoped assessments require client JWT.

## License

Private / assessment project — add a license if you distribute this code.
