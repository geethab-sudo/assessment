# Question Bank & Personalized Improvement — Task Checklist

> Use with **[plan.md](plan.md)**. Each section is a **stage** sized for a single agent session.  
> **Status key:** `[x]` done · `[ ]` todo · `[~]` partial

---

## Stage 0 — Question persistence in database ✅

> **Goal:** Every generated/confirmed question is stored in `question_bank` with stats updated on submit.  
> **Agent:** No work required unless regressions are found.

### Database & models

- [x] `question_bank` table with dedup `content_hash`, topic, difficulty, stats columns (`services/database.py`, `services/models.py`)
- [x] `assessment_questions.bank_question_id` FK + `difficulty` column
- [x] Index on `(topic_name, difficulty)`

### Write path

- [x] `question_bank_service.add_questions_to_bank` — upsert + `times_used`
- [x] `question_bank_service.link_assessment_questions_to_bank`
- [x] Called from `assessment_service.create_assessment` and `confirm_assessment` via `_upsert_to_bank`

### Read / analytics path

- [x] `record_question_outcome` on submit (`assessment_service.submit_assessment`)
- [x] `get_bank_stats` with `percent_correct` / `percent_wrong`
- [x] `get_bank_availability` per topic + total shortage
- [x] `find_bank_questions` + `get_employee_mastered_bank_ids` (service layer)

### API

- [x] `GET /admin/question-bank` (`routers/admin.py`)
- [x] `GET /admin/question-bank/availability`
- [x] Pydantic models `QuestionBankItem`, `BankAvailabilityResponse` (`schemas/admin.py`)

### Not in Stage 0 (deferred)

- [ ] `find_bank_questions` used in generation pipeline
- [ ] Admin or client UI for bank
- [ ] Dedicated `tests/test_question_bank_service.py` → done in Stage 1
- [ ] Fix difficulty label mismatch → done in Stage 1

---

## Stage 1 — Data correctness & stats hardening ✅

> **Goal:** Bank difficulty values match admin `level`; mastered-only exclusion; tests lock behavior.  
> **Depends on:** Stage 0  
> **Blocks:** Stage 2 (recycling)

### Backend

- [x] Store bank `difficulty` as `beginner` | `intermediate` | `advanced` in `add_questions_to_bank` (pass `level`, not LLM `easy/medium/hard`)
- [x] Update `_upsert_to_bank` call sites in `assessment_service.py` to pass `level`
- [x] One-time backfill in `database.py`: map existing `easy→beginner`, `medium→intermediate`, `hard→advanced`
- [x] Ensure `link_assessment_questions_to_bank` sets `AssessmentQuestion.difficulty` to same labels
- [x] Refactor `get_employee_seen_bank_ids` → `get_employee_mastered_bank_ids` (exclude only **correct** answers)
- [x] `employee_question_mastery` table — persistent per-employee mastered `bank_question_id`s
- [x] `record_employee_question_mastery` on correct submit (`assessment_service.submit_assessment`)
- [x] One-time backfill from historical submissions when table is empty
- [x] Update `find_bank_questions` and `get_bank_availability` to use mastered exclusion

### Tests

- [x] `tests/test_question_bank_service.py`
  - [x] Upsert same content twice → one row, `times_used` incremented
  - [x] `record_question_outcome` → correct `times_correct` / `times_wrong` and percentages in `get_bank_stats`
  - [x] `find_bank_questions` filters by topic + difficulty
  - [x] `get_employee_mastered_bank_ids` — wrong answers still eligible; correct answers excluded
  - [x] `get_employee_mastered_bank_ids` respects `E1001 | Name` user_id format
  - [x] `get_bank_availability` shortage math (with mastered exclusion)

### Docs

- [x] Note difficulty convention in `plan.md` §3.6 once fixed (mark issue resolved)

**Acceptance:** `GET /admin/question-bank/availability?topic_names=...&difficulty=beginner&n_requested=5` returns non-zero `available` after generating a beginner assessment on that topic.

---

## Stage 2 — Admin question source + hybrid generation ✅

> **Goal:** Admin picks **Generate new** or **Recycle then generate** (bank first, LLM for shortage — always).  
> **Depends on:** Stage 1  
> **Blocks:** Nothing for client flows (admin-only stage)

### Schema

- [x] Add to `GenerateAssessmentBody`:
  - [x] `question_source: Literal["generate_new", "recycle_then_generate"]` default `generate_new`
  - [x] `target_employee_id: str | None` — exclude bank questions this employee has **mastered**
- [x] Extend `GenerateAssessmentResponse` with `bank_sourced_count`, `llm_generated_count`, `shortage_messages`
- [x] `ReviewQuestionItem.bank_question_id` optional for confirm after recycle preview

### Service (`assessment_service.py`)

- [x] `_build_assessment_rows` / per-topic-type bank + LLM hybrid
- [x] `find_bank_questions` filters by `question_type`
- [x] Wire into `preview_questions` and `create_assessment`; confirm preserves `bank_question_id`
- [x] Recycled rows: `bank_question_id` on save; `increment_question_usage` not duplicate upsert
- [x] No duplicate `bank_question_id` within one assessment

### Admin UI (`AdminPage.jsx`)

- [x] Question source: **Generate new** | **Recycle then generate**
- [x] Optional `target_employee_id`
- [x] Availability banner before generate
- [x] Pass `question_source` in preview/confirm payloads
- [x] Review page shows bank vs LLM counts

### Tests

- [x] `tests/test_assessment_recycle.py`

---

## Stage 3 — Admin question bank browser ✅

> **Goal:** Admin UI to browse/filter/sort bank stats.  
> **Depends on:** Stage 1 (readable difficulty)  
> **Can run in parallel with:** Stage 4

### Frontend

- [x] `frontend/src/pages/AdminQuestionBankPage.jsx`
- [x] Route + nav link in `App.jsx` / `NavBar.jsx`
- [x] Filters: `language_code`, `topic_name`, `difficulty`, `question_type`
- [x] Table columns: topic, difficulty, type, times_used, % correct, % wrong, question preview (truncate)
- [x] Sort by `percent_wrong` desc (default), `percent_correct` desc, and `times_used` desc
- [x] `questionBankApi.js` — wrapper for `GET /admin/question-bank`

### Admin extras (same release)

- [x] Per-assessment **Allow copy-paste in Pyodide terminal** checkbox on `AdminPage.jsx` (default off)
- [x] `allow_pyodide_paste` on `assessments` table + API + `ClientPage.jsx` coding editors

### Docs

- [x] README — one line under Admin portal listing question bank page

**Acceptance:** Admin opens bank page, filters Python beginner MCQ, sees stats from seeded assessments.

---

## Stage 4 — Employee performance profile + stats report ✅

> **Goal:** Backend profile API for “Help me improve” modes **and** a shippable employee stats report (screen + print/PDF).  
> **Depends on:** Stage 0 (submissions + reports)  
> **Blocks:** Stages 5–7

### 4A — Profile API (improvement foundation)

#### Backend

- [x] `services/employee_profile_service.py`
  - [x] `get_employee_profile(employee_id, language_code=None, scope="last_3" | "full_history")`
  - [x] `scope=last_3`: merge topic summaries from **last 3 distinct submitted assessments** only → `weakest_topics` (default avg &lt; 70%)
  - [x] `scope=full_history`: merge across **all** assessments → `explored_topic_names`, `unexplored_topic_names`, `recommended_difficulty_by_topic`
  - [x] Each improvement endpoint calls with the correct scope (weak areas → `last_3`; new areas + difficulty → `full_history`)
- [x] `GET /client/employee-profile` in `app.py` with `scope` query param
- [x] Pydantic response schema in `schemas/improvement.py`

#### Tests

- [x] `tests/test_employee_profile_service.py`
  - [x] Employee with 5 assessments: weak-areas scope analyzes only last 3
  - [x] Full-history scope: topic from assessment #1 still in `explored_topic_names` even if not in last 3
  - [x] `unexplored_topic_names` excludes all historically explored topics

**Acceptance (4A):** Weak areas ignores assessments older than the last 3; new areas and difficulty use complete history.

### 4B — Employee stats report (shippable to user)

#### Report identity

- [x] Title: **Skills Progress Report**
- [x] Fields: `employee_id`, display name, period toggle (“All time” / “Last 90 days”), `report_generated_at`, report version

#### Page layout (print-ready)

- [x] Hero strip → languages + mastery → score trend + question-type donut → topic tables + insights

#### Sections

- [x] **A. Executive summary (hero)**
- [x] **B. Languages evaluated**
- [x] **C. Topics covered (per language)** — trend arrows; sparkline data in API
- [~] **D. Progress over time (plots)** — score trend, cumulative stacked chart, and radar chart in UI
- [x] **E. Question-type analytics** — donut
- [x] **F. Mastery & repetition**
- [x] **G. Strengths & focus areas (narrative)**
- [x] **H. Footer / CTA** — disclaimer; Stage 5 link placeholder

#### Data model (`get_employee_report`)

- [x] Full `EmployeeReportResponse` shape in `schemas/improvement.py`

#### Backend

- [x] `get_employee_report(employee_id, language_code=None, period="all_time" | "last_90_days")`
- [x] `GET /admin/employee-report?employee_id=` (admin JWT)
- [x] `GET /client/my-report` (public; `employee_id` query param)

#### Frontend

- [x] `EmployeeReportPage.jsx` — SVG charts (ring, line, donut)
- [x] Traffic-light topic chips
- [x] Empty state
- [x] `@media print` + **Download PDF / Print** button
- [x] Routes: `/admin/employee-report/:employeeId`, `/client/my-report`

#### Tests

- [x] `tests/test_employee_report_service.py` — timeline ordering, time-on-platform sum, language rollup, empty employee

**Acceptance (4B):** Admin or employee opens report for a user with history; sees hero, language cards, trend chart, topic table; can print/export PDF.

### 4B optional polish (enhancements — not blocking “done”)

> Core 4B meets acceptance above. Items below are follow-up UI/visual work, not missing stages.

| Item | API | UI |
|------|-----|-----|
| Topic heatmap (language × topic) | — | [x] |
| Cumulative correct/wrong stacked chart | [x] `cumulative_progress` | [x] |
| Radar chart (latest vs rolling average) | [x] `radar_topics` | [x] |
| QR code in report footer | — | [ ] (deferred) |

**Out of scope (do not schedule):** email / certificate delivery (`POST …/employee-report/send`).

---

## Stage 5 — Client: “Help me improve” + weak areas ✅

> **Goal:** `/client` button → weak areas flow → **bank-only** assessment (no LLM, no admin review).  
> **Depends on:** Stage 1 (mastered exclusion), Stage 4  
> **Does not depend on:** Stage 2 (admin hybrid)

### Backend

- [x] `services/improvement_assessment_service.py`
- [x] `POST /client/improvement/weak-areas` — body: `employee_id`, `language_code`, optional `questions_requested`
- [x] Profile `scope=last_3` → `weakest_topics` → `per_topic_config`
- [x] **`question_source=bank_only`** — `find_bank_questions` only; never call LLM
- [x] Exclude **mastered** bank IDs for `employee_id`
- [x] Returns `{ assessment_id?, questions_requested, questions_delivered, availability_message, topic_summary }`
- [x] If `questions_delivered == 0` → no assessment; return explanation (all mastered or bank empty)
- [x] If `questions_delivered < questions_requested` → still create assessment + availability message

### Frontend

- [x] **Help me improve** button on `ClientPage.jsx` (visible when `employee_id` filled)
- [x] Route or modal: `/client/improve` with three options (only wire **weak areas** in this stage)
- [x] Show merged **last-3-assessments** topic table (reuse report table styling)
- [x] Show availability message when delivered &lt; requested
- [x] **Start practice assessment** → call API → set `assessmentIdInput` and load assessment (or show “nothing left” state)

### Product note

- [x] **Never** pass LLM-generated questions to participants without admin review
- [x] Wrong answers may repeat; only mastered (correct) questions are excluded

### Tests

- [x] API test: weak-areas creates bank-only assessment on weak topics
- [x] API test: shortage returns 12/15 with message, not LLM fill
- [x] API test: all mastered → no assessment, clear message

**Acceptance:** Participant opens weak areas → gets only bank questions; if 12 of 15 available, sees shortage message; if all mastered, sees “nothing left” instead of new assessment.

---

## Stage 6 — Client: explore new areas ✅

> **Goal:** Second improvement option — unseen topics; **bank-only**.  
> **Depends on:** Stage 5 (wizard shell), Stage 4

### Backend

- [x] `POST /client/improvement/new-areas`
- [x] Profile `scope=full_history` → `unexplored_topic_names`; select top K topics
- [x] **`question_source=bank_only`** — no LLM
- [x] Exclude **mastered** bank IDs; same requested/delivered/messaging as Stage 5

### Frontend

- [x] Wire **Explore new areas** option in improvement wizard
- [x] Copy: topics not yet assessed (full history); shortage / all-mastered messages

**Acceptance:** User gets bank-only assessment on new topics, or clear message when bank cannot supply questions.

---

## Stage 7 — Client: improve difficulty ✅

> **Goal:** Third option — harder questions on familiar topics; **bank-only**.  
> **Depends on:** Stage 5–6 pattern, Stage 1, Stage 4

### Backend

- [x] `POST /client/improvement/difficulty`
- [x] Profile `scope=full_history` → `recommended_difficulty_by_topic`
- [x] **`question_source=bank_only`** at stepped difficulty — no LLM
- [x] Exclude mastered questions; handle “all mastered at this level” per topic

### Frontend

- [x] Wire **Improve difficulty** option
- [x] Explain stepped level using full-history performance; show shortage / all-mastered messages

**Acceptance:** User receives harder **bank** questions where available; “all mastered at intermediate” messaged clearly.

---

## Stage 9 — Coding quality, test cases, hints & decimal scoring

> **Goal:** Pyodide-safe coding questions, optional sample I/O and beginner hints, 0.0–1.0 score display.  
> **Depends on:** Stages 0–3 (generation + admin review)  
> **Blocks:** Stage 10

### 9A — Self-contained coding questions (no external files)

#### LLM / docs

- [x] Update generation prompt + `docs/assessment-generation.md`: **never** require reading/writing external files (`text.txt`, CSV on disk, etc.)
- [x] Require exercises runnable entirely in Pyodide (function/class + inline validation, or observable print output)
- [x] Grader evaluates submitted code only — no filesystem the student cannot access

#### Admin review

- [x] Flag or surface questions mentioning external files in `AdminReviewPage.jsx` (optional validator)

#### Tests / QA

- [ ] Regression: preview Tier 1 beginner coding batch — zero file-read prompts
- [ ] Manual QA: every coding item self-testable in Pyodide terminal

**Acceptance:** No new assessment ships file-dependent coding questions.

---

### 9B — Sample test cases (coding, function/class only)

#### Schema & API

- [x] Add `sample_test_cases: [{ input, expected_output, label? }]` to question/bank/review schemas
- [x] Add `include_sample_test_cases: bool = false` to `GenerateAssessmentBody` (default **off**)
- [x] Pass flag through preview → confirm → persisted on `assessment_questions` / bank

#### LLM generation

- [x] When flag on + function/class coding: emit 2–4 representative input → output examples (not exhaustive)
- [x] Append mandatory student note: *These examples help you validate your solution; make sure you also consider edge cases beyond the examples shown.*
- [x] When flag off: no sample test cases generated

#### Admin UI

- [x] `AdminPage.jsx`: checkbox **Include test cases in some coding questions** (default off)
- [x] `AdminReviewPage.jsx`: render each test case in a **code-snippet panel**; add/edit/remove rows

#### Client UI

- [x] `ClientPage.jsx`: read-only formatted sample I/O block below coding questions that have test cases

#### Tests

- [ ] API/schema round-trip for `sample_test_cases`
- [ ] Flag off → no test cases; flag on → at least one function coding item has cases

**Acceptance:** Admin enables flag → review shows editable snippet blocks → client sees partial I/O examples + edge-case note.

---

### 9C — Decimal scoring display (0.0–1.0)

#### Backend / schema

- [x] Submit response includes `score_decimal` (0.0–1.0) per question and `achieved_total` / `max_total`
- [x] Keep internal 0–100 if needed for mastery (≥70) and certificate (>85) thresholds

#### Client UI

- [x] Per-question: `0.7 / 1.0` instead of `70 / 100`
- [x] Post-submit summary: **Achieved X.X out of Y.Y** (+ optional percentage)

#### Tests

- [x] Unit test: score conversion and total aggregation

**Acceptance:** After submit, participant sees decimal per-question scores and achieved/total summary.

---

### 9D — Beginner coding hints (optional)

#### Schema & API

- [x] Add optional `hint: str | null` on coding questions
- [x] Add `include_beginner_coding_hints: bool = false` to `GenerateAssessmentBody` (default **off**)

#### LLM generation

- [x] When flag on + beginner + coding: append `hint: <text>` at end of question
- [x] **Critical prompt rule:** hint must NEVER be full answer, complete algorithm, or copy-paste solution — nudge only (repeat in system prompt)

#### Admin UI

- [x] `AdminPage.jsx`: checkbox **Include hints for beginner coding questions** (default off)
- [x] `AdminReviewPage.jsx`: editable hint field; optional warning if hint looks like full solution

#### Client UI

- [x] Show `hint: …` below beginner coding questions when present

#### Tests

- [ ] Hints only when flag on + beginner + coding; never on intermediate/advanced

**Acceptance:** Flag on → beginner coding has editable hint in review; client sees nudge only, not solution.

---

## Stage 10 — Tier 1 certificates & admin grant

> **Goal:** Certificate when score **> 85%** on Tier 1 preset (beginner/intermediate/advanced).  
> **Depends on:** Stage 9C (post-submit score display)  
> **Excludes:** `certificates/Professional-tier2.jpg` in v1

### Assets & rendering

- [ ] Map `certificates/` templates: beginner, intermediate, advanced Tier 1 (exclude Professional-tier2)
- [ ] `certificate_service.py`: overlay participant name on template → PNG/PDF

### Database

- [ ] `certificates_issued` table: `employee_id`, `display_name`, `level`, `assessment_id?`, `score`, `issued_at`, `issued_by` (auto vs admin)

### Admin — preset checkbox

- [ ] `AdminPage.jsx` (Tier 1 preset): **Enable certificate on completion** (default **off**)
- [ ] `assessments.certificate_enabled`, `assessments.certificate_level`
- [ ] Pass through preview → confirm

### Participant — success modal

- [ ] After submit: if certificate enabled + Tier 1 + score > 85% → modal:
  - *Your grade is {grade}%*
  - *You earned your certificate for Python {level}!*
  - Name input → **Generate certificate** / **Skip**
- [ ] `POST /client/certificate/generate` → download/preview + audit row

### Admin — manual grant

- [ ] On admin employee performance/report page: **Generate certificate**
- [ ] Prompt: level (beginner | intermediate | advanced) + name on certificate
- [ ] `POST /admin/certificate/issue`

### Tests

- [ ] Threshold: 85% → no modal; 86% + enabled → modal
- [ ] Disabled preset → no certificate flow
- [ ] Admin manual issue creates audit row

**Acceptance:** Enabled Tier 1 preset + >85% → named certificate; admin can grant manually; Tier 2 template not used.

---

## Stage 10 optional — LinkedIn sharing (superseded by Stage 12E)

- [x] Documented in plan (Stage 10 optional)
- [ ] **Moved to Stage 12E** — implement LinkedIn + social share there

**Acceptance:** See Stage 12E.

---

## Stage 11A — Admin model picker: Grok vs Gemini (generation)

> **Goal:** Admin chooses **Grok** or **Gemini** when generating questions; Gemini uses `GOOGLE_API_KEY1` + `gemini-3.5-flash` (configurable).  
> **Depends on:** Stages 0–3 (generation pipeline)  
> **Blocks:** Nothing  
> **Does not include:** Grading provider switch (stays Groq); MongoDB (Stage 11B)

### Backend — provider layer

- [ ] Create `services/llm/` package: `providers.py`, `groq_provider.py`, `gemini_provider.py`
- [ ] Move Groq `_chat_json_text`, client init, key helpers into `groq_provider.py`
- [ ] Implement `gemini_provider.chat_json_text` via `google-genai` SDK
- [ ] `gemini_key_configured()` — non-empty `GOOGLE_API_KEY1` after normalize
- [ ] `generate_questions(..., generation_provider="grok"|"gemini")` routes to provider
- [ ] Keep shared prompt + JSON parse + `normalize_generated_question` in facade
- [ ] `evaluate_answers` unchanged (Groq only) — document in code comment

### Dependencies & env

- [ ] Add `google-genai` to `requirements.txt`
- [ ] `.env.example`: `GOOGLE_API_KEY1`, `GEMINI_MODEL=gemini-3.5-flash`
- [ ] Default model `gemini-3.5-flash`; override via `GEMINI_MODEL`

### Schema & API

- [ ] `GenerateAssessmentBody.generation_provider: Literal["grok", "gemini"]` default `grok`
- [ ] Pass `generation_provider` through `assessment_service` (`gen_kwargs`, preview, create, confirm)
- [ ] HTTP 503 when selected provider key missing (clear error message)
- [ ] `HealthResponse.gemini_configured: bool`
- [ ] Update `/health` handler and OpenAPI examples
- [ ] Update `openapi_config.ERROR_503` copy if needed

### Admin UI

- [ ] `AdminPage.jsx`: radio **Grok (Groq)** | **Gemini** in Generate section (default Grok)
- [ ] Note: grading still uses Groq
- [ ] Disable/warn on Gemini when `gemini_configured` false (fetch `/health` or pass flag)
- [ ] Include `generation_provider` in preview + confirm payloads
- [ ] Optional: show provider in `AdminReviewPage` preview meta

### Tests

- [ ] Unit: provider routing mock (gemini vs groq)
- [ ] Schema: default + invalid `generation_provider`
- [ ] API: preview with `gemini` + no key → 503
- [ ] Regression: `tests/test_assessment_recycle.py` still passes

**Acceptance:** Admin selects Gemini → preview returns questions; Grok path unchanged; submit grading still uses Groq.

---

## Stage 11B — PostgreSQL → MongoDB Atlas

> **Goal:** All persistence on **MongoDB Atlas** via `MONGODB_URI`; no Postgres Docker on cloud server; schema ready for future `question_bank` vector search.  
> **Depends on:** Stages 0–7 (all DB-backed features)  
> **Recommended order:** 11B-1 → 11B-2 → … → 11B-6 (one sub-session per agent)  
> **Out of scope:** Embedding generation, Atlas Vector Search index creation

### 11B-1 — Mongo connection & indexes

- [ ] Replace `services/database.py` with pymongo client + `get_database()` + `ping_database()`
- [ ] `init_db()`: create all collection indexes (idempotent)
- [ ] `counters` collection for integer `id` sequences (`next_id("question_bank")`)
- [ ] Remove SQLAlchemy engine / `SessionLocal` / Postgres URL helpers
- [ ] `requirements.txt`: add `pymongo` (+ `dnspython` if needed); remove `sqlalchemy`, `psycopg`

### 11B-2 — Document models & catalog

- [ ] Replace `services/models.py` ORM with document type definitions (or inline dicts)
- [ ] Rewrite `catalog_service.py` for `languages` + `topics` collections
- [ ] Rewrite `scripts/seed_sample_catalog.py` for Mongo
- [ ] Port difficulty backfill logic to Mongo `init_db` or one-time script

### 11B-3 — Assessments & submissions

- [ ] Rewrite `services/db_service.py` (assessments, assessment_questions, submissions)
- [ ] Preserve all public function signatures used by `assessment_service`, `app.py`, routers
- [ ] Rewrite `attempt_service.py` for `assessment_attempts`

### 11B-4 — Question bank & mastery

- [ ] Rewrite `question_bank_service.py` (upsert, stats `$inc`, find, availability, mastery)
- [ ] `employee_question_mastery` collection + backfill from submissions when empty
- [ ] `backfill_question_bank_from_assessment_questions` on Mongo

### 11B-5 — Reports, certificates, remaining services

- [ ] `employee_profile_service.py`, `report_service.py` — Mongo reads
- [ ] `certificate_service.py` — `certificates_issued` collection
- [ ] `improvement_assessment_service.py` — verify no direct SQLAlchemy imports
- [ ] `scripts/seed_demo_students.py` — Mongo

### 11B-6 — Migration, deploy docs, cleanup

- [ ] `scripts/migrate_postgres_to_mongodb.py` (PG `DATABASE_URL` → `MONGODB_URI`, dry-run)
- [ ] `.env.example`: `MONGODB_URI`, `MONGODB_DB_NAME`; deprecate `DATABASE_URL` / `POSTGRES_*`
- [x] `README.md`: Atlas setup, IP allowlist, seed without Docker
- [x] `docker-compose.yml`: removed (Atlas-only deploy)
- [ ] `ARCHITECTURE.md`: MongoDB + future vector note on `question_bank`
- [ ] `tests/TEST_GUIDE.md`: update DB assumptions
- [ ] Full `pytest tests/ -q` green
- [ ] Manual QA script (task.md) on Atlas-backed deploy

**Acceptance:** App runs with only `MONGODB_URI`; all admin/client flows work; cloud deploy needs no local Postgres; migration script can copy existing PG data to Atlas.

---

## Stage 12 — Interactive guided practice, inclusive UX & social sharing

> **Goal:** Topic pickers on Skills Progress Report (heatmap, radar, unexplored, recommendations quick-start); selectable topics on improvement wizard; **75%** proficiency rules; no “weak” in participant UI; LinkedIn/social certificate share.  
> **Depends on:** Stages 4B, 5–7, 10, 11B  
> **Recommended order:** 12A → 12B + 12C (parallel) → 12D → 12E

### Shared caps (enforce in API + UI)

- [ ] Max **15** questions per practice session (`questions_requested` clamped 1–15)
- [ ] Max **3** questions per topic (MCQ + coding combined) in one assessment
- [ ] Max **5** topics per session (new-areas + step-up; focus path respects same per-topic cap)
- [ ] Bank-only — never call LLM on client improvement paths
- [ ] Unexplored / new topics always **beginner** difficulty

### 12A — Inclusive language & 75% threshold

**Frontend**

- [ ] `EmployeeReportPage.jsx`: replace “weak” with **“need improvement”** (topic table, insights, empty states)
- [ ] `ImprovementPage.jsx`: rename **“Improve my weak areas”** → inclusive label (e.g. **“Strengthen my focus areas”**)
- [ ] Remove **“weak”** badge on topic rows; use **“need improvement”** or styling only
- [ ] Update copy on `path=weak` screens (headings, buttons, helper text) — no “weak areas” phrasing
- [ ] Report print/PDF strings: no “weak”

**Backend**

- [ ] Align focus-topic threshold to **75%** in `employee_profile_service` (was 70% in places)
- [ ] Document `FOCUS_TOPIC_PERCENT_THRESHOLD` in `.env.example` (optional, default 75)
- [ ] Step-up eligibility consistent with **≥ 75%** at current level

**Tests**

- [ ] CI or test: participant-facing JSX does not contain “weak” / “Weak areas” (allowlist internal vars if needed)

**Acceptance:** `/client/my-report` and `/client/improve` show inclusive copy; focus topics use 75% cutoff.

---

### 12B — My Report: heatmap & radar topic picker

**Frontend (`EmployeeReportPage.jsx`)**

- [ ] Click handler on **heatmap cells** only → open modal **“Choose the topics you would like to practice more”**
- [ ] Click handler on **radar chart** topics only → same modal (scoped to radar topics)
- [ ] Per topic: show **Improve this topic** if &lt; 75%; **Step up difficulty** if ≥ 75%
- [ ] Multi-select + question count (default 10, max 15) + **Start practice**
- [ ] On success → navigate to `/client` with new `assessment_id`

**Backend**

- [ ] `POST /client/improvement/from-topics` (or extend improvement service):
  - [ ] Body: `employee_id`, `language_code`, `topic_names[]`, optional `questions_requested`, per-topic intent derived from profile or explicit
  - [ ] Bank-only assembly with 5/topic and 15 total caps
- [ ] Pydantic schemas + `routers/client.py` route
- [ ] OpenAPI: add to `EXPECTED_ROUTES` in `test_openapi.py`

**Tests**

- [ ] API: mixed intents (below/above 75%) → correct difficulty per topic
- [ ] API: rejects &gt; 15 questions or &gt; 5 topics when applicable

**Acceptance:** Heatmap/radar click → modal → practice assessment with correct difficulty rules.

---

### 12C — My Report: unexplored picker & “Ok, let’s do it!”

**Frontend**

- [ ] **Unexplored topics** section: button to open **“Choose the topics you would like to explore”** modal
- [ ] Multi-select up to **5** topics; max **15** questions; beginner only
- [ ] **Recommendations** heading: add **“Ok, let’s do it!”** button
- [ ] Quick practice: default **10** questions from recommendation bullets (explore + momentum topics)

**Backend**

- [ ] Extend `POST /client/improvement/new-areas` with optional `topic_names[]` (client-selected unexplored topics)
- [ ] `POST /client/improvement/quick-practice` — `employee_id`, `language_code`, optional `questions_requested` (default 10, max 15)
  - [ ] Server builds topic plan from `get_employee_report` insights (explore vs focus vs step-up)
- [ ] Schemas + routes + tests

**Acceptance:** Unexplored multi-select works; one-click recommendations → 10-question assessment.

---

### 12D — Improvement wizard: topic selection & caps

**Frontend (`ImprovementPage.jsx`)**

**Focus path (`path=weak` → display as focus / strengthen)**

- [ ] Checkbox list of topics **below 75%** (last 3 assessments)
- [ ] User selects topics + question count (max 15) → **Start practice**
- [ ] **“Help me improve all my focus areas”** — selects all eligible topics, still server-capped

**New areas path (`path=new`)**

- [ ] Checkbox list of unexplored topics; max **5** selections; max **15** questions; beginner only

**Step-up path (`path=difficulty`)**

- [ ] Checkbox list of topics eligible for step-up (≥ 75% at current level); max **5** topics; max **15** questions

**Backend**

- [ ] Extend `POST /client/improvement/weak-areas` with `topic_names?`, `questions_requested?` (max 15)
- [ ] Extend `POST /client/improvement/new-areas` with `topic_names?`, `questions_requested?`
- [ ] Extend `POST /client/improvement/difficulty` with `topic_names?`, `questions_requested?`
- [ ] `improvement_assessment_service`: allocate questions across topics; enforce ≤ 5 per topic
- [ ] Backward compatible when `topic_names` omitted (current auto-select behavior)

**Tests**

- [ ] Focus: subset of topics → only those in assessment
- [ ] New: 6 topics selected → 400 or clamp to 5
- [ ] Difficulty: only ≥ 75% topics offered
- [ ] All paths: 16 questions requested → clamped to 15

**Acceptance:** All three improvement paths support topic pickers and caps; inclusive labels throughout.

---

### 12E — Social certificate sharing (LinkedIn & other)

> Promoted from Stage 10 optional.

**Frontend**

- [ ] After certificate download: **Share on LinkedIn** button
- [ ] **Copy link** for verification / achievement URL
- [ ] Optional: Web Share API or X intent URL on supported browsers

**Backend**

- [ ] `GET /client/certificate/{id}/share-metadata` — title, level, date, public URL
- [ ] Stable share URL per issued certificate (document in README)

**Product / legal**

- [ ] LinkedIn button branding guidelines
- [ ] No auto-post without explicit user action

**Tests**

- [ ] Share metadata endpoint returns expected fields for issued cert
- [ ] Manual QA: deep link opens LinkedIn add-certification flow

**Acceptance:** User can share earned certificate to LinkedIn and copy a shareable link.

---

## Stage 13 — Admin assessment lifecycle (re-review, alias, delete, regenerate, incremental save)

> **Goal:** Fix “edits didn’t reach participants”; re-open saved assessments in full review UI; human-readable aliases; delete/regenerate individual questions; **save each approved question immediately** so crashes don’t lose work.  
> **Plan:** [plan.md](plan.md) §Phase 5.  
> **Depends on:** Stages 2, 9B, 9D, 11B.  
> **Order:** **13A → 13E → 13B → 13C → 13D** (13C/13D can parallel after 13A + 13E save paths exist).

### Root cause checklist (investigate before coding)

- [ ] Confirm: edits lost when admin leaves `/admin/review` without clicking **Save assessment** (state-only draft).
- [ ] Confirm: no path from `/admin/assessments` to `/admin/review` for existing `ASM-…` IDs.
- [ ] Confirm: `PATCH /admin/assessment/…/question/…` not wired in UI; missing `sample_test_cases` / `coding_hint`.
- [ ] Confirm: in-place PATCH does not fork `bank_question_id` (recycle can serve old bank text).
- [ ] Confirm: no per-question save — crash/tab close loses partial review progress.
- [ ] Document findings in PR / commit message when 13A ships.

---

### Stage 13A — Re-review existing assessment

**Backend**

- [ ] `GET /admin/assessment/{assessment_id}/review` → `ReviewQuestionItem[]` + assessment metadata
- [ ] `PUT /admin/assessment/{assessment_id}/review` (or `POST …/review/save`) — save to **same** `assessment_id`
- [ ] Edited questions → new `question_id`; new `assessment_questions` row; new bank row + `bank_question_id`
- [ ] Unchanged questions → preserve `question_id` + `bank_question_id`
- [ ] Removed questions → delete or soft-delete; handle submissions gracefully (warn/block)
- [ ] Audit log `assessment.review.save`
- [ ] OpenAPI summary + description; `tests/test_openapi.py` routes

**Frontend**

- [ ] `AdminAssessmentsPage`: **Re-review** button → navigate to `/admin/review` with loaded payload
- [ ] `AdminReviewPage`: support **existing** assessment mode (`assessmentId` + `isReReview` flag)
- [ ] Save calls re-review endpoint (not `confirm-assessment` that mints new ID)
- [ ] Success screen shows same assessment ID

**Tests**

- [ ] `tests/test_assessment_re_review.py` — load, edit one question, save, participant GET matches
- [ ] Edited question `question_id` changes; `bank_question_id` updated for new content

**Acceptance:** Re-open ASM-…, edit a question, save, participant sees new text on reload.

---

### Stage 13E — Incremental per-question save (“This question is good, save it”)

**Backend**

- [ ] `POST /admin/assessment/review/draft` — create draft assessment shell on first save (new review flow); return `assessment_id`
- [ ] `POST /admin/assessment/{assessment_id}/review/questions/{question_id}/save` — persist one `ReviewQuestionItem` + bank upsert
- [ ] `GET …/review` returns `saved_at` per question (and `review_status` on assessment)
- [ ] `assessments.review_status`: `draft` | `in_review` | `published`; participant GET blocked until `published`
- [ ] Final **Save assessment** sets `published` when all questions individually saved (or saves remainder + publish)
- [ ] Audit log `assessment.review.question_save`

**Frontend**

- [ ] Per-question button on the **right** of each card: **“This question is good, save it”**
- [ ] After save: **Saved** badge; button disabled until question edited again
- [ ] Top progress: *“N / M questions saved”*
- [ ] Banner shows `assessment_id` after first incremental save on new draft
- [ ] Reload / Re-review restores saved vs unsaved state from API

**Tests**

- [ ] Save 2 questions → reload review → 2 saved, content matches DB
- [ ] Draft assessment not visible to participant until publish
- [ ] Edit after save clears saved state until re-saved

**Acceptance:** Reviewer saves 3 questions, simulates refresh, work is intact; publish when done; participant can take assessment.

---

### Stage 13B — Assessment alias & search

**Backend**

- [ ] `assessments.alias` field (optional string); persist on create + re-review save
- [ ] `PATCH /admin/assessment/{id}` body `{ alias }` for quick rename
- [ ] `GET /admin/assessments` — include `alias`; filter param `q` matches ID or alias (case-insensitive)
- [ ] Schema: `alias` on confirm/re-review bodies + list response items

**Frontend**

- [ ] Optional alias on generate → review flow (`AdminPage` / confirm payload)
- [ ] `/admin/assessments`: Alias column; search box *ID or alias*; edit alias inline or modal
- [ ] Show alias in re-review banner

**Tests**

- [ ] Create with alias → list search finds by alias substring
- [ ] PATCH alias → list reflects change

**Acceptance:** Search `Maria June` finds assessment; ID sharing unchanged.

---

### Stage 13C — Delete question in review

**Frontend**

- [ ] Trash icon on each `QuestionCard` in `AdminReviewPage.jsx`
- [ ] Confirm dialog before remove
- [ ] Block save when zero questions remain
- [ ] Works for bank-sourced and LLM questions (recycle mode)

**Backend**

- [ ] Re-review save handles `removed_question_ids` or infers from submitted question set
- [ ] If submissions exist for removed `question_id`, warn or block per 13A rules

**Tests**

- [ ] Remove one of five questions → save → `question_count` = 4

**Acceptance:** Admin discards a question during review; it disappears for participants after save.

---

### Stage 13D — Regenerate single question (similar topic)

**Backend**

- [ ] `POST /admin/assessment/review/regenerate-question`
- [ ] Body: topic, type, level, language, reference question snapshot, optional `admin_preference`, generation flags
- [ ] LLM `count=1`; return `ReviewQuestionItem` with hints/test cases per flags
- [ ] Rate-limit / auth same as other admin generate routes

**Frontend**

- [ ] ♻️ button per question card → modal with optional preference textarea
- [ ] Loading + error states on card
- [ ] Replace question in local review state (clear `bank_question_id` until save)

**Tests**

- [ ] Mock LLM: regenerate returns one valid MCQ + one coding item
- [ ] `admin_preference` appears in prompt fixture

**Acceptance:** Admin regenerates one question with preference; review shows new content; save persists for participants.

---

### Stage 13 — Docs

- [ ] `README.md` — re-review, incremental save, alias, delete, regenerate
- [ ] `plan.md` — mark Phase 5 complete when done
- [ ] `tests/TEST_GUIDE.md` — new admin routes

---

### Stage 12 — Docs & regression

- [ ] `README.md` — document new improvement/report interactions and caps
- [ ] `plan.md` — mark Stage 12 complete when done
- [ ] `tests/TEST_GUIDE.md` — new endpoints and copy rules
- [ ] Full `pytest tests/ -q` green on Atlas `test_db`

---

## Stage 8 — Future backlog (not scheduled)

### 4B report polish (optional)

- [x] Topic heatmap (language × topic) — `EmployeeReportPage`
- [x] Wire `cumulative_progress` → stacked correct/wrong chart in `EmployeeReportPage`
- [x] Wire `radar_topics` → radar chart in `EmployeeReportPage`
- [ ] Optional QR code in report footer (deferred)

### Platform / ops

- [ ] Employee authentication (replace self-declared `employee_id`)
- [ ] Admin retire/archive bank question
- [ ] `scripts/seed_question_bank.py` — bulk demo questions from catalog
- [ ] Update [ARCHITECTURE.md](ARCHITECTURE.md) — MongoDB Atlas + question bank (Stage 11B)
- [ ] **LinkedIn / social certificate share** — **Stage 12E**

**Explicitly out of scope:** email delivery (`POST …/employee-report/send`).

---

## Manual QA script (end-to-end, after Stage 7)

1. Seed catalog: `python scripts/seed_sample_catalog.py`
2. Admin: generate **Beginner** Tier 1 assessment (generate new) → confirm → note `assessment_id`
3. Client: take as `E1001 | Test User` → submit
4. Admin: generate second assessment with **Recycle then generate** → verify availability banner and mixed counts
5. Client: take second assessment as `E1001` → submit
6. Client: **Help me improve** → weak areas → if 12/15 available, confirm shortage message (no LLM questions)
7. Client: **Explore new areas** → verify new topics, bank-only
8. Client: **Improve difficulty** → verify harder bank questions or “all mastered” message
9. Client: answer same question wrong twice → it may appear again; answer correctly → it should not reappear for that topic/difficulty
10. Admin: open question bank page → confirm `times_used` and % stats moved
11. Admin: generate Tier 1 with test cases + hints checkboxes **off** → confirm no I/O examples or hints
12. Admin: regenerate with both checkboxes **on** → review snippet panels + hints → confirm
13. Client: take assessment → verify decimal scores (`0.0–1.0`) and achieved/total after submit
14. Admin: Tier 1 with certificate enabled → client scores >85% → certificate modal + download
15. Admin: employee report → manual **Generate certificate** for eligible user

### After Stage 11A

16. Admin: select **Gemini** → generate Tier 1 preview → confirm questions parse correctly
17. Admin: select **Grok** → same flow still works
18. Submit assessment → coding/subjective grading still works (Groq)

### After Stage 11B

19. Seed catalog against Atlas: `python scripts/seed_sample_catalog.py`
20. Re-run steps 1–15 on MongoDB-backed deploy (no local Postgres)
21. If migrating: run `scripts/migrate_postgres_to_mongodb.py --dry-run` then live; verify row counts

### After Stage 12

22. My Report: click heatmap cell → modal → improve topic (&lt; 75%) or step up (≥ 75%)
23. My Report: **Ok, let’s do it!** → 10-question quick practice from recommendations
24. Improvement: focus path — select topics, max 15 questions, no “weak” copy
25. Improvement: new areas — select up to 5 topics, beginner only
27. Certificate: Share on LinkedIn + copy link

### After Stage 13

28. Admin: create assessment → confirm → participant takes → **Re-review** same ASM-ID → edit Q3 → save → participant reload sees edit
29. Admin: set alias `Python beginner Maria Jun 25` → assessments search finds it
30. Admin: re-review → delete one question → save → participant question count drops
31. Admin: re-review → regenerate one coding question with preference → save → new hint/test cases visible
32. Admin: review 10 questions → **save 4 individually** → refresh browser → 4 still marked saved → finish + publish → participant can start

---

## Agent session quick-pick

| If you want to… | Do stage |
|-----------------|----------|
| Fix bank queries / difficulty labels | **1** |
| Refactor seen → mastered exclusion | **1** |
| Let admin recycle questions (bank + LLM + review) | **2** |
| Show bank analytics in admin | **3** |
| Build improvement API foundation | **4A** |
| Build shippable employee stats report | **4B** (core done) |
| Polish report charts (cumulative, radar, heatmap) | **4B optional** or **8** |
| Add Help me improve button | **5** then **6**–**7** (done) |
| Fix coding questions that need external files | **9A** |
| Add sample test cases + admin snippet review | **9B** |
| Show scores as 0.0–1.0 | **9C** |
| Add optional beginner coding hints | **9D** |
| Tier 1 certificates + admin grant | **10** |
| LinkedIn share (future) | **10 optional** |
| Grok vs Gemini generation picker | **11A** |
| MongoDB Atlas migration | **11B** (split 11B-1…11B-6) |
| Inclusive copy + 75% threshold | **12A** |
| Report heatmap/radar topic picker | **12B** |
| Report unexplored + quick practice | **12C** |
| Improvement wizard topic selection | **12D** |
| LinkedIn / social certificate share | **12E** |
| Re-review saved assessment | **13A** |
| Incremental per-question save | **13E** |
| Assessment alias + search | **13B** |
| Delete question in review | **13C** |
| Regenerate one question in review | **13D** |

Copy the stage block + **Acceptance** line into the agent prompt as scope boundary.
