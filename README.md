# AI Assessment Platform

Web application for generating and delivering technical assessments. Administrators use an LLM (Groq) to create question sets from a language/topic catalog; participants take tests in the browser with optional in-browser Python execution (Pyodide).

Persistence is **PostgreSQL** (SQLAlchemy). Legacy CSV storage under `data/` has been removed.

## Features

- **Admin**: Sign in with a configured password; generate assessments (MCQ, coding, subjective); manage catalog languages/topics; browse assessments (language, topics, added date); delete assessments; review submissions.
- **Participant**: Open a test with employee ID, name, and assessment ID (no account required for shared assessments).
- **Grading**: Answers scored via Groq with per-question feedback; MCQ correctness uses stored answers when applicable.
- **Coding questions**: Code editor with catalog language selection; run Python in the browser via Pyodide.

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

Tables are created automatically on API startup (`init_db()`).

### 3. Optional: seed catalog

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/seed_sample_catalog.py
```

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

## Port conflicts

If another app already uses **8000** or **5173**, you may see the wrong API or UI (e.g. a different project’s login page).

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
pyassesment/
├── app.py                 # FastAPI routes and validation
├── services/
│   ├── assessment_service.py
│   ├── auth_service.py
│   ├── catalog_service.py
│   ├── db_service.py
│   ├── database.py
│   ├── llm_service.py
│   └── models.py
├── frontend/              # React SPA
├── scripts/
│   └── seed_sample_catalog.py
├── docker-compose.yml     # PostgreSQL only
├── requirements.txt
└── .env.example
```

## Main routes (UI)

| Path | Description |
|------|-------------|
| `/` | Home |
| `/login/admin` | Admin sign-in |
| `/admin` | Generate assessment |
| `/admin/assessments` | List / delete assessments |
| `/admin/catalog` | Languages and topics |
| `/admin/submissions` | Submission review |
| `/client` | Take assessment |

## API overview

| Endpoint | Auth | Description |
|----------|------|-------------|
| `POST /auth/login` | — | Admin password or client ID |
| `POST /generate-assessment` | Admin | Create assessment via LLM |
| `GET /admin/assessments` | Admin | List assessments |
| `DELETE /admin/assessments/{id}` | Admin | Delete assessment |
| `GET /assessment/{id}` | Public* | Questions (no answers) |
| `POST /submit-assessment` | Public* | Submit and grade |

\*Shared assessments only without client token; client-scoped assessments require client JWT.

## License

Private / assessment project — add a license if you distribute this code.
