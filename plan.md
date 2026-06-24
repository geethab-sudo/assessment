# Question Bank & Personalized Improvement — Implementation Plan

> **Purpose:** Living roadmap for the question-bank, recycling, analytics, and “Help me improve” features.  
> **Companion file:** [task.md](task.md) — checkbox tasks per stage for agentic implementation.  
> **Last reviewed:** 2026-06-23

---

## 1. Product vision

Today, every new assessment triggers fresh LLM generation. We want a **reusable question bank** so admins can choose:


| Mode                      | Who    | Behavior                                                                                                                                     |
| ------------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **Generate new**          | Admin  | LLM creates all questions; each is upserted into the bank; admin reviews before save.                                                        |
| **Recycle then generate** | Admin  | Bank first by topic + difficulty; LLM fills shortfall; **admin review** before participants see anything.                                    |
| **Bank only**             | Client | “Help me improve” pulls **only** from the bank — **no LLM**, no unreviewed questions. Deliver what is available; if shortage, tell the user. |


Each bank question should expose:

- `times_used` — how many assessments included it
- `percent_correct` / `percent_wrong` — derived from `times_correct` and `times_wrong` after participants submit

Participants already identify with `**employee_id`** (plus name). That ID is the anchor for:

- Excluding **mastered** questions (answered correctly) when building personalized assessments — **not** every question ever seen
- Aggregating performance across assessments
- Future login (out of scope for early stages)

### Employee question eligibility (mastered vs seen)

When selecting bank questions for a participant, **do not exclude questions merely because the employee has seen them before**. Exclude only questions they have **answered correctly** (mastered):


| Type                        | “Correct” / mastered                                                              |
| --------------------------- | --------------------------------------------------------------------------------- |
| **MCQ**                     | Answer matches stored `correct_answer` (case-insensitive), same as submit grading |
| **Coding** (and subjective) | Score **≥ 70 / 100** on that submission                                           |


A participant who got the same coding question wrong three times **may receive it again** — repetition until they learn it is intentional.

**“No more questions”** for a topic + difficulty means: the employee has answered **correctly** every bank question available for that topic and difficulty (nothing left to assign). The UI should say so clearly instead of creating an empty or LLM-filled assessment.

**Implementation:** mastered questions are stored per employee in `employee_question_mastery` (`employee_id` + `bank_question_id`). Updated on each correct submit; one-time backfill from historical submissions on first deploy.

On `**/client`**, a **“Help me improve”** entry point will offer three guided paths:

1. **Improve my weak areas** — summarize **last 3 assessments only**; build a **bank-only** practice assessment on weakest topics.
2. **Explore new areas** — use **full history** for explored topics; **bank-only** on catalog topics not yet covered.
3. **Improve difficulty** — use **full history**; **bank-only** at stepped difficulty on familiar topics.

**Client rule:** improvement flows never call the LLM. If the bank cannot supply the target count, deliver what is available and explain the gap (e.g. *“You asked for 15 questions; based on availability, there are only 12 valid questions for you in our question bank.”*).

**Profile window rule:** last **3** assessments for weak-area analysis; **all** completed assessments for new-area discovery and difficulty step-up.

---

## 2. Deployment context

This platform runs as a **single FastAPI app + React SPA + database** (see [README.md](README.md)). Today the database is **PostgreSQL** (local Docker or managed instance). **Phase 3 (Stage 11B)** migrates persistence to **MongoDB Atlas** so cloud deploys do not depend on a Postgres container on the app server.

There is **no separate question-bank server**. All stages extend the existing backend services and frontend pages — compatible with a simple deploy model (API + Atlas, not a standalone bank microservice).

---

## 3. What is already done (Stage 0 — complete)

The first milestone — **persist questions in the database** — is implemented.

### 3.1 Database


| Artifact                                   | Location                                                                                                      |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| `question_bank` table                      | `services/database.py` (`_ensure_question_bank_table`)                                                        |
| `assessment_questions.bank_question_id` FK | `services/database.py` (`_ensure_assessment_question_bank_columns`)                                           |
| SQLAlchemy models                          | `services/models.py` — `QuestionBank`, `AssessmentQuestion.bank_question_id`, `AssessmentQuestion.difficulty` |


`**question_bank` columns (relevant):** `content_hash` (dedup), `question_text`, `type`, `options`, `correct_answer`, `code_snippet`, `topic_name`, `language_code`, `difficulty`, `times_used`, `times_correct`, `times_wrong`, `created_at`.

### 3.2 Services


| Capability                           | Location                                                                               | Wired?                            |
| ------------------------------------ | -------------------------------------------------------------------------------------- | --------------------------------- |
| Upsert on generate/confirm           | `question_bank_service.add_questions_to_bank` via `assessment_service._upsert_to_bank` | ✅                                 |
| Link assessment rows → bank          | `question_bank_service.link_assessment_questions_to_bank`                              | ✅                                 |
| Record correct/wrong on submit       | `question_bank_service.record_question_outcome` in `submit_assessment`                 | ✅                                 |
| Browse bank + % stats                | `question_bank_service.get_bank_stats`                                                 | ✅ API only                        |
| Availability check                   | `question_bank_service.get_bank_availability`                                          | ✅ API only                        |
| Find reusable questions              | `question_bank_service.find_bank_questions`                                            | ⚠️ **Implemented but not called** |
| Employee mastered-question exclusion | `employee_question_mastery` table + `get_employee_mastered_bank_ids`                   | ✅ Stage 1                         |


### 3.3 API (admin)


| Endpoint                                | Purpose                                                           |
| --------------------------------------- | ----------------------------------------------------------------- |
| `GET /admin/question-bank`              | List bank rows with filters + `percent_correct` / `percent_wrong` |
| `GET /admin/question-bank/availability` | Per-topic availability + shortage vs `n_requested`                |


### 3.4 Participant / employee foundation


| Capability                          | Location                                                                |
| ----------------------------------- | ----------------------------------------------------------------------- |
| `employee_id` on load/submit        | `app.py`, `schemas/assessment.py`, `ClientPage.jsx`                     |
| Per-employee shuffle                | `shuffle_service.py`                                                    |
| Per-assessment topic summary report | `report_service.aggregate_topic_summary`, `GET /assessment/{id}/report` |
| Timed attempts keyed by employee    | `AssessmentAttempt`, `attempt_service.py`                               |


### 3.5 Remaining work (as of Stages 0–7 complete)

**Shipped:** Stages **0–7** — question bank persistence, admin recycle/hybrid, bank browser, employee profile + stats report (core 4B), and all three “Help me improve” flows (weak areas, new areas, step-up difficulty).

**Next (Phase 2):** Stages **9–10** — coding-question quality, sample test cases, decimal scoring, beginner hints, Tier 1 certificates — see §Stage 9–10.

**Next (Phase 3):** Stages **11A–11B** — admin **Grok vs Gemini** model picker for question generation; **MongoDB Atlas** migration (vector-search-ready, no Postgres Docker on cloud) — see §Phase 3.

**Optional / partial (not blocking “done”):**

- **Stage 4B polish** — report API is shippable; some ambitious layout items from §4B below are enhancements only (see **4B optional polish**).
- **Stage 8** — employee auth, bank retirement, bulk seed script, `ARCHITECTURE.md` update (see §Stage 8).
- **Stage 10 optional** — LinkedIn certificate sharing (backlog after certificate v1).

**Explicitly out of scope (for now):** email delivery (`POST …/employee-report/send`).

### 3.6 Difficulty labels (fixed in Stage 1)

Bank and `assessment_questions.difficulty` store admin `**level`** values: `beginner` | `intermediate` | `advanced`. Legacy `easy`/`medium`/`hard` rows are backfilled on startup via `_backfill_question_bank_difficulty_labels` in `database.py`.

---

## 4. Architecture (target state)

```mermaid
flowchart TB
  subgraph admin [Admin]
    AP[AdminPage — source mode + availability]
    AR[AdminReviewPage — unchanged review flow]
    AB[AdminQuestionBankPage — browse stats]
  end

  subgraph client [Client]
    CP[ClientPage — Help me improve]
    IMP[Improvement wizard — 3 modes]
  end

  subgraph api [FastAPI]
    GEN[POST /generate-assessment / preview / confirm]
    BANK[GET /admin/question-bank*]
    IMP_API[POST /client/improvement/* — new]
  end

  subgraph services [Services]
    AS[assessment_service]
    QBS[question_bank_service]
    EPS[employee_profile_service — new]
    IAS[improvement_assessment_service — new]
    RS[report_service]
  end

  subgraph db [PostgreSQL]
    QB[(question_bank)]
    AQ[(assessment_questions)]
    SUB[(submissions)]
    ATT[(assessment_attempts)]
  end

  AP --> GEN
  AP --> BANK
  AB --> BANK
  CP --> IMP
  IMP --> IMP_API
  GEN --> AS
  IMP_API --> IAS
  AS --> QBS
  IAS --> QBS
  IAS --> EPS
  EPS --> RS
  EPS --> SUB
  QBS --> QB
  AS --> AQ
```



**Design principles**

1. **One bank, many assessments** — dedup by content hash; stats updated on every graded submission.
2. **Admin: bank-first, LLM-second** — recycle-then-generate fills shortage only on the **admin** path, always followed by review.
3. **Client: bank-only** — “Help me improve” never surfaces LLM-generated questions; partial counts are OK with clear messaging.
4. **Mastered-only exclusion** — skip bank questions the employee already got **correct**; wrong answers can repeat until mastered.
5. **Reuse admin review flow** — any LLM-generated item goes through preview/confirm before participants see it.
6. **Stages are independent** — each stage in [task.md](task.md) can be handed to an agent with minimal cross-stage context.

---

## 5. Stages (modular roadmap)

### Stage 0 — Question persistence ✅ DONE

Save every generated/confirmed question into `question_bank`; link `assessment_questions`; increment stats on submit.

**Exit criteria:** Met (see §3). Optional: add `tests/test_question_bank_service.py` in Stage 1.

---

### Stage 1 — Data correctness & stats hardening

**Goal:** Bank rows are queryable by admin `level`; stats are trustworthy.

**Work:**

1. **Normalize difficulty in the bank** — store `beginner` | `intermediate` | `advanced` (not `easy`/`medium`/`hard`). Migration/backfill for existing rows.
2. **Align `link_assessment_questions_to_bank`** — `AssessmentQuestion.difficulty` should match bank.
3. **Unit tests** — upsert dedup, outcome counters, `get_employee_mastered_bank_ids`, availability math.
4. **Refactor employee exclusion** — rename/replace `get_employee_seen_bank_ids` → `get_employee_mastered_bank_ids`: only bank IDs where the employee’s **best or latest** submission was correct (MCQ match; coding/subjective score ≥ 70). Update `find_bank_questions` and `get_bank_availability` to use mastered exclusion by default.
5. **Optional:** index or materialized view if bank grows large (not required for v1).

**Files:** `assessment_service.py`, `question_bank_service.py`, `database.py`, `tests/test_question_bank_service.py`.

**Agent handoff:** “Fix difficulty normalization and add bank unit tests. Do not change generation behavior yet.”

---

### Stage 2 — Admin: question source mode + hybrid generation

**Goal:** Admin chooses **Generate new** vs **Recycle then generate** when creating an assessment.

There is **no “recycle only” mode** in v1 — you can never assume the bank has enough questions. “Recycle” always means **bank first, LLM for the remainder**, whether the admin uses a Tier 1 preset or picks custom topics and counts manually.

**API changes (`GenerateAssessmentBody` / preview / confirm):**

```text
question_source: "generate_new" | "recycle_then_generate"   # default: generate_new
target_employee_id: str | null   # optional; exclude bank questions this employee has already mastered
```

**Backend (`assessment_service`):**

1. When `question_source == "recycle_then_generate"`, for each topic + type + count in `per_topic_config` (or global counts):
  - Call `find_bank_questions` for that slice.
  - If shortage > 0 → generate only the shortage for that topic/type (always — no error for shortfall).
2. Mark recycled rows with existing `bank_question_id` when saving.
3. Response metadata:

```json
{
  "bank_sourced_count": 12,
  "llm_generated_count": 13,
  "shortage_messages": [
    "Tier 1 - OOP Basics: only 2 MCQ available; generating 1 new"
  ]
}
```

**Admin UI (`AdminPage.jsx`):**

- Toggle or radio: **Generate new** | **Recycle then generate** (two options only).
- When recycle-then-generate is on: call `GET /admin/question-bank/availability` with selected topics, level, total count → show message: *“Only X questions available; we will generate Y new.”*
- Pass `question_source` through preview → review → confirm.
- Works with **Tier 1 presets** and **manual topic/count selection** — the system must satisfy the full requested distribution (per-topic MCQ/coding counts) by combining bank pulls and LLM generation.

**Exit criteria:** Admin can build a 25-question Tier 1 assessment using ≥1 bank question; shortage filled by LLM; message shown in UI. Same behavior when the admin skips presets and manually selects topics + counts — demand is always fully met via bank + new questions.

**Agent handoff:** “Implement question_source in schemas, assessment_service hybrid builder, AdminPage toggle + availability banner. Depends on Stage 1 difficulty fix.”

---

### Stage 3 — Admin: question bank browser ✅

**Goal:** Admins inspect bank health — which questions are hard/tricky (high `percent_wrong`) or strong (high `percent_correct`).

**UI:** New page `AdminQuestionBankPage.jsx` (nav link from admin menu).


| Column              | Source                    |
| ------------------- | ------------------------- |
| Topic               | `topic_name`              |
| Difficulty          | `difficulty`              |
| Type                | `type`                    |
| Times used          | `times_used`              |
| % correct / % wrong | computed                  |
| Question preview    | truncated `question_text` |


**Filters:** language, topic, difficulty, type.

**Sort:** `percent_wrong` desc (default), `percent_correct` desc, `times_used` desc.

**API:** Reuse `GET /admin/question-bank` (no new endpoint required).

**Same release — per-assessment Pyodide paste:** Admin checkbox **Allow copy-paste in Pyodide terminal** (default off) → `assessments.allow_pyodide_paste` → participant coding editors respect flag (MCQ copy block unchanged).

**Exit criteria:** Admin can filter Python beginner MCQ and sort by failure rate or success rate.

**Agent handoff:** “Frontend-only stage; wire existing admin question-bank API.”

---

### Stage 4 — Employee performance profile + stats report ✅

**Goal:** (A) Backend service that powers all three “Help me improve” modes with **different history windows per mode**; (B) a **shippable employee stats report** (screen + print/PDF) for one `employee_id`.

#### 4A — Profile API (improvement foundation)

**New service:** `services/employee_profile_service.py`

**Inputs:** `employee_id`, optional `language_code`, `scope: "last_3" | "full_history"`


| Scope          | Used by                       | Meaning                                                           |
| -------------- | ----------------------------- | ----------------------------------------------------------------- |
| `last_3`       | Weak areas                    | Only the **last 3 distinct submitted assessments** (by timestamp) |
| `full_history` | New areas, Improve difficulty | **All** completed assessments for this employee                   |


**Outputs (shape varies slightly by scope):**

```json
{
  "employee_id": "E1001",
  "scope": "last_3",
  "assessments_analyzed": 3,
  "language_code": "py",
  "topic_performance": [
    {
      "topic_name": "Tier 1 - OOP Basics",
      "questions_count": 5,
      "average_percent": 62.0,
      "attempts": 2,
      "last_difficulty": "beginner"
    }
  ],
  "explored_topic_names": ["..."],
  "unexplored_topic_names": ["..."],
  "weakest_topics": ["..."],
  "recommended_difficulty_by_topic": { "Tier 1 - OOP Basics": "intermediate" }
}
```

**Logic sketch:**

1. List submissions for employee (reuse `attempt_service.normalize_employee_id`, submission joins).
2. **Weak areas (`scope=last_3`):** take last 3 distinct assessments → merge topic summaries → `weakest_topics` from lowest `average_percent` (e.g. < 70%).
3. **New areas (`scope=full_history`):** `explored_topic_names` from **all** assessments; `unexplored_topic_names` = catalog topics for `language_code` minus explored.
4. **Improve difficulty (`scope=full_history`):** merge topic performance across **all** assessments; `recommended_difficulty_by_topic` — if last difficulty was `beginner` and avg ≥ 75% → `intermediate`; if `intermediate` and avg ≥ 80% → `advanced`; else stay per product rules.
5. Reuse `report_service.aggregate_topic_summary` (or shared helper) per assessment before merging.

**API:**

- `GET /client/employee-profile?employee_id=&language_code=&scope=last_3|full_history` (client JWT), or
- Each improvement endpoint calls the service with the correct scope internally (preferred — UI does not need to choose).

**Exit criteria (4A):** Weak-areas profile uses 3 assessments only; new-areas and difficulty profiles reflect entire history (e.g. topic explored in assessment #1 still counts as explored even if not in last 3).

**Agent handoff:** “New employee_profile_service + one read endpoint; no UI yet.”

#### 4B — Employee stats report (shippable to user)

Rich, print-ready report for managers or employees: languages evaluated (Python, Java, …), topics covered per language, questions answered correctly, **time on platform**, progress history, proficiency level, and charts — suitable to **ship to a user** (in-app view, print, or PDF).

**Report identity**


| Field     | Example                               |
| --------- | ------------------------------------- |
| Title     | **Skills Progress Report**            |
| Subject   | `employee_id` + display name          |
| Period    | “All time” or “Last 90 days” (toggle) |
| Generated | timestamp + report version            |


**Page layout (print-ready)**

```text
┌─────────────────────────────────────────────────────────────┐
│ HERO: employee + overall score ring │ languages │ time stats │
├──────────────────────────┬──────────────────────────────────┤
│ Proficiency by language  │ Topic heatmap (language × topic) │
├──────────────────────────┼──────────────────────────────────┤
│ Score trend (line)       │ Question-type breakdown (donut)  │
├──────────────────────────┴──────────────────────────────────┤
│ Topic detail table │ Strengths / focus areas callouts       │
├─────────────────────────────────────────────────────────────┤
│ Recommended next steps → Help me improve CTAs               │
└─────────────────────────────────────────────────────────────┘
```

**Sections**


| Section                        | Content                                                                                                                                                                                               |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A. Executive summary**       | Proficiency index (0–100); assessments completed; questions answered; % correct overall; **time on platform** (sum `submitted_at − started_at`; avg per assessment); language badges with mini scores |
| **B. Languages evaluated**     | Per `language_code`: topics covered / catalog size, question count, % correct, proficiency (Beginner / Intermediate / Advanced)                                                                       |
| **C. Topics covered**          | Per `(language, topic)`: attempted / mastered, % correct, last difficulty, trend vs previous attempt, sparkline (last 5 scores); optional heatmap topic × difficulty                                  |
| **D. Progress over time**      | Line: score % over time; stacked area: cumulative correct vs wrong; radar: latest vs 3-assessment average                                                                                             |
| **E. Question-type analytics** | Donut/bars: MCQ / coding / subjective — count, % correct                                                                                                                                              |
| **F. Mastery & repetition**    | Mastered count; needs-practice (seen 2+ times, not mastered)                                                                                                                                          |
| **G. Strengths & focus**       | Auto bullets: strengths (≥80%, ≥5 Qs); focus areas (`scope=last_3`); unexplored topics; one-line recommendation each                                                                                  |
| **H. Footer / CTA**            | Weak-areas practice link; optional QR; platform-only disclaimer                                                                                                                                       |


**Data model (`get_employee_report`)**

```json
{
  "employee_id": "E1001",
  "display_name": "Luis",
  "report_generated_at": "2026-06-15T12:00:00Z",
  "scope": "full_history",
  "summary": {
    "assessments_completed": 12,
    "questions_answered": 186,
    "overall_percent_correct": 71.2,
    "proficiency_label": "Intermediate",
    "total_time_seconds": 15420,
    "avg_assessment_time_seconds": 1285
  },
  "languages": [
    {
      "language_code": "python",
      "language_label": "Python",
      "topics_covered": 8,
      "topics_in_catalog": 12,
      "questions_count": 142,
      "percent_correct": 74.0,
      "proficiency_label": "Intermediate",
      "topics": []
    }
  ],
  "score_timeline": [
    { "assessment_id": "ASM-…", "submitted_at": "…", "percent": 68, "language_code": "python" }
  ],
  "question_type_breakdown": { "mcq": { "count": 90, "percent_correct": 78 } },
  "mastery": { "mastered_count": 45, "needs_practice_count": 8 },
  "insights": {
    "strengths": ["OOP Basics"],
    "focus_areas": ["Exception Handling"],
    "unexplored_topics": ["Concurrency"]
  }
}
```

**Rendering & delivery**


| Layer  | Approach                                                                                  |
| ------ | ----------------------------------------------------------------------------------------- |
| Routes | `/admin/employee-report/:employee_id` (admin); `/client/my-report` (self-service)         |
| UI     | `EmployeeReportPage.jsx` — ~900px max-width, print-friendly                               |
| Charts | Recharts or Chart.js; score ring SVG; ≤4 chart types                                      |
| Export | `@media print` + Download PDF (`window.print()` or html2pdf.js / WeasyPrint server-side)  |
| Email  | **Out of scope** — `POST /admin/employee-report/send` sketched only; use print/PDF in-app |


**Visual polish**

- Traffic-light topic chips: green ≥75%, amber 50–74%, red <50%
- Consistent color per language across charts
- Empty state when no submissions

**Implementation phases**


| Phase  | Deliverable                                                                |
| ------ | -------------------------------------------------------------------------- |
| **4a** | `get_employee_profile()` — API only                                        |
| **4b** | `get_employee_report()` — richer aggregation + timeline + time-on-platform |
| **4c** | `EmployeeReportPage` — screen view with charts                             |
| **4d** | Print/PDF stylesheet + Download PDF button                                 |


**Exit criteria (4B):** Admin or employee opens report for a user with history; sees hero, language cards, trend chart, topic table; exports a clean PDF.

**Status:** Core 4B (**4a–4d**) is **done** — acceptance criteria above are met.

#### 4B optional polish (enhancements — not blocking “done”)

Some items in the layout sketch above were described ambitiously. The report is shippable without them; treat as a follow-up polish pass, not a missing stage.


| Item                                    | API                               | UI    | Notes                                                 |
| --------------------------------------- | --------------------------------- | ----- | ----------------------------------------------------- |
| Topic heatmap (language × topic)        | derived from `languages[].topics` | wired | Client-side grid; no dedicated API field              |
| Cumulative correct/wrong stacked chart  | `cumulative_progress`             | wired |                                                       |
| Radar chart (latest vs rolling average) | `radar_topics`                    | wired |                                                       |
| QR code in footer                       | —                                 | —     | Deferred — not in scope                               |
| Email report / certificate send         | `POST …/send` sketched            | —     | **Out of scope** — do not schedule until product asks |


**Agent handoff (polish only):** “Wire `cumulative_progress` + `radar_topics` in `EmployeeReportPage`; add heatmap if product wants it. No email send.”

**Agent handoff (core 4B):** “Depends on 4A aggregations; new report endpoint + page + print CSS.” ✅

---

### Stage 5 — Client: “Help me improve” shell + weak areas ✅

**Goal:** Button on `/client` → wizard step 1 → **Improve my weak areas**.

**UI (`ClientPage.jsx` or `ImprovementPage.jsx`):**

1. Require `employee_id` (already on page).
2. Button **Help me improve** → modal or sub-route `/client/improve`.
3. Option A: **Improve my weak areas** — show merged topic table for last 3 assessments; highlight weak topics; **Start practice assessment** button.

**Backend (`improvement_assessment_service.py`):**

- `POST /client/improvement/weak-areas`
- Body: `employee_id`, `language_code`, optional `questions_requested` (target count)
- Profile `scope=last_3` → `weakest_topics` → `per_topic_config`
- `**question_source = bank_only`** — call `find_bank_questions` only; **never** call LLM
- `exclude_employee_id` → exclude **mastered** bank IDs only
- Response includes `questions_requested`, `questions_delivered`, `availability_message` when `delivered < requested`
- If `questions_delivered == 0` → do not create assessment; return friendly message (e.g. mastered everything available for those topics, or bank empty)
- If `questions_delivered > 0` → auto-create shared assessment and redirect to take it

**Product decision (v1):** Participants **never** receive LLM-generated questions without admin review. Improvement assessments are **bank-only**. Shortfall is communicated, not silently filled:

> You asked for **{requested}** questions, but based on availability there are only **{delivered}** valid questions for you in our question bank.

**Exit criteria:** Employee clicks weak areas → receives up to available bank questions on weak topics; if bank has fewer than target, message explains the gap; if all relevant questions are mastered, clear “nothing left” state.

**Agent handoff:** “Client UI + improvement weak-areas endpoint; depends on Stage 1 (mastered exclusion) + 4. Does **not** use admin LLM hybrid.”

---

### Stage 6 — Client: explore new areas ✅

**Goal:** Second wizard option — topics user hasn’t tried; **bank-only**.

**Backend:** `POST /client/improvement/new-areas`

- Profile `scope=full_history` → `unexplored_topic_names`; pick top K (e.g. 3–5).
- `**question_source = bank_only`** — no LLM
- Exclude employee’s **mastered** bank IDs
- Same `questions_requested` / `questions_delivered` / availability messaging as Stage 5

**UI:** Show which new topics were selected and why; show shortage message if applicable.

**Exit criteria:** User gets bank-only assessment on unseen topics, or clear message if bank cannot supply questions.

**Agent handoff:** “Depends on Stage 4–5 patterns; one new endpoint + wizard branch.”

---

### Stage 7 — Client: improve difficulty ✅

**Goal:** Third wizard option — same topics, harder difficulty; **bank-only**.

**Backend:** `POST /client/improvement/difficulty`

- Profile `scope=full_history` → `recommended_difficulty_by_topic` per explored topic.
- `**question_source = bank_only`** at the stepped difficulty — no LLM
- Exclude **mastered** questions at that difficulty
- If user has **mastered all** bank questions at the next difficulty for a topic → message: nothing left at this level (or suggest admin-generated content later)

**Exit criteria:** Beginner-only user receives intermediate/advanced **bank** questions where available; shortage and “all mastered” states messaged clearly.

**Agent handoff:** “Depends on Stage 1 + 4 + 5 patterns; one endpoint + wizard branch.”

---

## Phase 2 — Assessment quality, scoring UX & certificates (Stages 9–10)

> **Goal:** Self-contained Pyodide-friendly coding questions, optional sample I/O and beginner hints, **0.0–1.0** score display, and Tier 1 preset certificates when score **> 85%**.  
> **Tasks:** [task.md](task.md) §Stage 9–10.

### Stage 9 — Coding question quality, test cases, hints & decimal scoring

#### 9A — Self-contained coding questions (no external files)

**Problem:** Generated coding tasks sometimes ask students to read files (e.g. `text.txt`) that do not exist in the Pyodide terminal, so they cannot verify their solution.

**Rule:** Every coding question must be **fully runnable in the in-browser terminal** with no external file dependencies.

**LLM instruction changes** (generation prompt / `docs/assessment-generation.md`):

- **Never** ask the candidate to read, write, or depend on external files (`text.txt`, CSV on disk, paths outside the editor, etc.).
- Prefer exercises where the student **implements a function or class** and validates with inline inputs, or writes a short script whose output is observable in the terminal.
- Grading must work from submitted code alone — no filesystem the participant cannot access.

**Admin review:** Reject or edit questions that reference external files.

**Exit criteria:** New Tier 1 assessments contain no file-dependent coding prompts; students can self-test every coding item in Pyodide.

---

#### 9B — Sample test cases (coding, function/class only)

**Goal:** Give candidates a **small predefined set** of input → expected output examples so they can sanity-check function/class solutions — without publishing every edge case.


| Rule                                               | Detail                                                                                                               |
| -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| **Scope**                                          | **Coding questions only**, when the task is to **implement a function or class** (not open-ended scripts).           |
| **Admin opt-in**                                   | Checkbox on `AdminPage.jsx`: **Include test cases in some coding questions** — **default off**.                      |
| **Partial coverage**                               | 1-2 representative examples, e.g. *For input `XYZ`, expect output `ABC`*. **Do not** include all test cases.         |
| **Student note (mandatory when test cases shown)** | *These examples help you validate your solution; make sure you also consider edge cases beyond the examples shown.*  |
| **Per-question optional**                          | Even with checkbox on, omit test cases when the prompt is not function/class shaped; admin may add/remove in review. |


**Data model:**

```json
{
  "sample_test_cases": [
    { "input": "[1, 2, 3]", "expected_output": "6", "label": "basic sum" }
  ]
}
```

**Admin review (`AdminReviewPage.jsx`):** Each test case in a **code-snippet panel** (monospace, formatted) — editable, add/remove rows. Forces admin to verify examples are real, not LLM hallucination.

**Participant UI:** Read-only formatted block below question text. Samples are for **self-validation** only; final grading remains LLM/existing grader (no auto-run harness in v1).

**Exit criteria:** Checkbox on → function coding items show formatted examples in client + editable snippets in review; checkbox off → unchanged behavior.

---

#### 9C — Decimal scoring display (0.0–1.0)

**Goal:** Clearer per-question and total scores after the test.


| Context              | Format                                                                                   |
| -------------------- | ---------------------------------------------------------------------------------------- |
| **Per question**     | **0.0 – 1.0** (one decimal), e.g. `0.7 / 1.0` — not `70 / 100`.                          |
| **Assessment total** | **Achieved X.X out of Y.Y** plus optional percentage, e.g. `8.7 / 10.0 (87%)`.           |
| **Internal API/DB**  | May keep 0–100 for thresholds (mastery ≥ 70, certificate > 85); UI converts for display. |


**Files:** `ClientPage.jsx` results, submit response schemas, employee report if per-question scores appear.

**Exit criteria:** Post-submit shows decimal per-question scores and achieved/total; certificate threshold (≥ 0.85) unchanged.

---

#### 9D — Beginner coding hints (optional)


| Rule                          | Detail                                                                                                                                                                                             |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Admin opt-in**              | Checkbox: **Include hints for beginner coding questions** — **default off**.                                                                                                                       |
| **Scope**                     | **Beginner** + **coding** only.                                                                                                                                                                    |
| **Format**                    | Append: `hint: <short hint>`                                                                                                                                                                       |
| **LLM constraint (critical)** | Hints must **NEVER** give the full answer, complete algorithm, or copy-paste solution. Only a nudge — concept, syntax, or one small step. Repeat this constraint prominently in the system prompt. |
| **Admin review**              | Editable hint field; optional warning if hint looks like a full solution.                                                                                                                          |


**Exit criteria:** Checkbox on → beginner coding items show editable hint in review and `hint: …` for participants; intermediate/advanced never get auto-hints.

**Stage 9 order:** `9A` → `9B` + `9D` (parallel) → `9C`. **Blocks:** Stage 10 (certificate popup uses post-submit score display).

---

### Stage 10 — Tier 1 certificates & admin grant

**Goal:** Issue a certificate when a participant scores **> 85%** on a **Tier 1 preset** at **beginner**, **intermediate**, or **advanced** — plus manual admin issuance.

#### Assets (`certificates/`)


| Template                    | Level                                     |
| --------------------------- | ----------------------------------------- |
| Beginner Tier 1 diploma     | `beginner`                                |
| Intermediate Tier 1 diploma | `intermediate`                            |
| Advanced Tier 1 diploma     | `advanced`                                |
| `Professional-tier2.jpg`    | **Excluded in v1** — Tier 2 not wired yet |


Overlay **participant name** on template (server-side Pillow/canvas or client export).

#### Admin: certificate on preset

**Checkbox on Tier 1 preset flow:** **Enable certificate on completion** — **default off**.

- On → `certificate_enabled: true`, `certificate_level` from preset difficulty.
- Off → normal assessment, no certificate modal.

#### Participant: success modal

**When:** Submit complete, certificate enabled, Tier 1 preset, score **> 85%**.

```text
Your grade is {grade}%.

You earned your certificate for Python {level}!

What name would you like on your certificate?
[ name input ]  [ Generate certificate ]  [ Skip ]
```

Persist: `employee_id`, name on certificate, level, `assessment_id`, score, `issued_at`.

#### Admin: manual grant (performance page)

On admin employee performance / report view:

- **Generate certificate** → pick **level** + **name on certificate**
- For participants who earned it under special conditions without the modal flow.

**API:** `POST /admin/certificate/issue` — `employee_id`, `level`, `display_name`, optional `assessment_id`.

**Exit criteria:** Enabled preset + > 85% → modal → downloadable certificate; admin manual grant works; disabled preset → no certificate flow.

---

### Stage 10 optional — LinkedIn sharing (future backlog)

**Not v1.** After download, optional **Share on LinkedIn?** button:

- LinkedIn “Add license/certification” deep link or OAuth share with verification URL.
- Requires product/legal review; implement after core certificate generation is stable.

---

## Phase 3 — Multi-LLM generation & MongoDB Atlas (Stages 11A–11B)

> **Goal:** (A) Let admins choose **Grok** or **Gemini** when generating assessment questions; (B) replace PostgreSQL with **MongoDB Atlas** for cloud deploys and future vector search on the question bank.  
> **Tasks:** [task.md](task.md) §Stage 11A–11B.  
> **Order:** **11A first** (small, independent) → **11B** (large; can be split across multiple agent sessions).

### Why now

| Driver | Detail |
| ------ | ------ |
| **Model choice** | Compare Groq vs Google generation quality/cost without code changes per experiment |
| **Cloud ops** | Atlas removes the need to run Postgres in Docker on the production server |
| **Future vectors** | MongoDB Atlas Vector Search can index `question_bank` embeddings for “similar question” lookup — **not implemented in 11B**, but collection/index design should not block it |

---

### Stage 11A — Admin model picker: Grok vs Gemini (generation only)

**Scope:** Question **generation** only (`generate_questions`). **Grading** (`evaluate_answers` for coding/subjective) stays on **Groq** in v1 — document in README; a follow-up could add provider choice for grading later.

#### Provider abstraction

Refactor `services/llm_service.py` into a thin facade + provider modules:

```text
services/llm/
  __init__.py          # re-export generate_questions, evaluate_answers, *configured helpers
  providers.py         # GenerationProvider protocol, resolve provider by name
  groq_provider.py     # existing Groq OpenAI-compatible client (_chat_json_text)
  gemini_provider.py   # Google Gemini API (JSON mode)
```

`generate_questions(..., generation_provider: str = "grok")` routes to the selected provider. Shared pieces stay centralized: prompt text, `_parse_strict_json`, `normalize_generated_question`, test-case/hint flags.

#### Environment variables

| Variable | Purpose | Default |
| -------- | ------- | ------- |
| `GROQ_API_KEY` | Groq (existing) | — |
| `GROQ_MODEL` | Groq model id | `llama-3.3-70b-versatile` |
| `GROQ_GENERATION_TEMPERATURE` | Generation temperature | `0.72` |
| `GOOGLE_API_KEY1` | Google AI API key (user-chosen name) | — |
| `GEMINI_MODEL` | Gemini model id | `gemini-3.5-flash` |

Use **`GOOGLE_API_KEY1`** exactly as in `.env` (not `GOOGLE_API_KEY`). Add `google-genai` (official SDK) to `requirements.txt`.

**Gemini implementation notes:**

- Model id: **`gemini-3.5-flash`** (user request; override via `GEMINI_MODEL`).
- Request **JSON object** output (`response_mime_type: application/json` or SDK equivalent).
- Reuse the same user prompt as Groq so question shape is identical.
- Map Gemini auth/429 errors to clear `RuntimeError` messages (mirror `_groq_auth_hint` pattern).

#### API & service wiring

**`GenerateAssessmentBody`** (`schemas/admin.py`):

```python
generation_provider: Literal["grok", "gemini"] = "grok"
```

Pass through:

- `assessment_service.preview_questions` / `create_assessment` / `_build_assessment_rows` / `_generate_rows_*`
- `gen_kwargs` dict (already used for `admin_level`, test cases, hints) → add `generation_provider`

**Validation:** If `generation_provider == "gemini"` and `GOOGLE_API_KEY1` is missing → HTTP **503** with actionable message. Same for `grok` + missing `GROQ_API_KEY` (existing behavior).

**Health** (`GET /health`, `HealthResponse`):

- Add `gemini_configured: bool` (non-empty `GOOGLE_API_KEY1`).
- Keep `groq_configured` for grading + Grok generation.
- Optional: `generation_providers_available: list[str]` for admin UI.

**OpenAPI:** Update `ERROR_503` description to mention either provider key.

#### Admin UI (`AdminPage.jsx`)

In the **Generate assessment** section (near **Question source**):

- Radio or select: **Grok (Groq)** | **Gemini**
- Default: **Grok**
- Helper text: *Grading still uses Groq.*
- Disable Gemini option when `/health` reports `gemini_configured: false` (or show warning).
- Include `generation_provider` in `previewPayload` / confirm body.


#### Tests

| Test | Assert |
| ---- | ------ |
| Schema | `generation_provider` defaults to `grok`; rejects unknown values |
| Routing | `generate_questions(..., generation_provider="gemini")` calls Gemini client mock |
| API 503 | Preview with `gemini` and no key → 503 |
| Regression | Existing recycle/hybrid tests still pass with default `grok` |

**Exit criteria:** Admin selects Gemini on Generate → preview returns valid questions; Grok path unchanged; grading still works with Groq only.

**Agent handoff:** “Implement 11A only. Do not start MongoDB migration.”

---

### Stage 11B — PostgreSQL → MongoDB Atlas

**Goal:** All app persistence uses **MongoDB Atlas** via `MONGODB_URI`. Remove runtime dependency on PostgreSQL and Docker Postgres for production. Preserve all existing API behavior and data shapes returned to the frontend.

#### Target architecture

```mermaid
flowchart TB
  subgraph admin [Admin SPA]
    AP[AdminPage — provider + generate]
  end

  subgraph api [FastAPI]
    SVC[services layer]
  end

  subgraph atlas [MongoDB Atlas]
    LANG[(languages)]
    TOP[(topics)]
    QB[(question_bank)]
    ASM[(assessments)]
    AQ[(assessment_questions)]
    SUB[(submissions)]
    ATT[(assessment_attempts)]
    EQM[(employee_question_mastery)]
    CERT[(certificates_issued)]
    CTR[(counters)]
  end

  AP --> SVC
  SVC --> atlas
```

#### Technology choices

| Choice | Rationale |
| ------ | --------- |
| **pymongo** (sync) | Matches existing synchronous service style; minimal async refactor |
| **Explicit integer `id` fields** | Keeps `bank_question_id` and join-style code recognizable; use a `counters` collection for `$inc` sequences |
| **Separate collections** | Mirror current normalized tables (not full embed of questions inside assessment) — simpler migration from SQLAlchemy queries |
| **JSON-native fields** | `topic_names`, `related_documents`, `sample_test_cases`, `raw_notebook` stored as BSON arrays/objects (no JSONB type) |

**Remove:** `sqlalchemy`, `psycopg`, PostgreSQL-specific `database.py` migrations (`information_schema`, `SERIAL`, `JSONB`).

**Add:** `pymongo`, optional `dnspython` (SRV URIs for Atlas).

#### Collection schema (v1)

| Collection | Primary key | Notes |
| ---------- | ----------- | ----- |
| `counters` | `_id` = collection name | `{ seq: N }` for auto-increment |
| `languages` | `id` (int) | `code` unique |
| `topics` | `id` (int) | `language_id` + `name` unique compound |
| `question_bank` | `id` (int) | `content_hash` unique; indexes on `topic_name+difficulty`, `language_code` |
| `employee_question_mastery` | `id` (int) | unique `(employee_id, bank_question_id)` |
| `assessments` | `assessment_id` (string) | ASM-… ids unchanged |
| `assessment_questions` | `id` (int) | unique `(assessment_id, question_id)` |
| `assessment_attempts` | `id` (int) | unique `(assessment_id, employee_id)` |
| `submissions` | `id` (int) | indexes on `(assessment_id, user_id)`, `timestamp` |
| `certificates_issued` | `id` (int) | indexes on `employee_id`, `assessment_id` |

**Future vector field (do not implement now):** optional `embedding: list[float]` on `question_bank` + Atlas Vector Search index — document in README/ARCHITECTURE only.

#### `services/database.py` rewrite

Replace SQLAlchemy engine with:

```python
def get_mongo_client() -> MongoClient
def get_database() -> Database
def init_db() -> None  # create indexes, run one-time backfills
def ping_database() -> bool
```

`init_db()` responsibilities (idempotent):

1. Create all indexes (equivalent to current `_ensure_*` + model `__table_args__`).
2. Run data backfills that today run on PG startup (`_backfill_question_bank_difficulty_labels`, mastery backfill if empty) — port logic to Mongo queries.
3. No `information_schema` / `DO $$` blocks.

#### Service migration map

Rewrite persistence in place (keep function signatures in `db_service.py`, `catalog_service.py`, `question_bank_service.py`, etc.):

| Module | PG today | Mongo action |
| ------ | -------- | ------------ |
| `services/models.py` | SQLAlchemy ORM | **Replace** with TypedDict / dataclass document shapes OR delete and use dicts |
| `services/db_service.py` | SQLAlchemy sessions | `pymongo` CRUD |
| `services/catalog_service.py` | ORM | `languages` / `topics` collections |
| `services/question_bank_service.py` | ORM + joins | aggregation / `find` + `update_one` with `$inc` for stats |
| `services/attempt_service.py` | ORM | `assessment_attempts` |
| `services/certificate_service.py` | ORM | `certificates_issued` |
| `services/employee_profile_service.py` | read submissions/assessments | same queries on Mongo |
| `services/report_service.py` | read submissions | same |
| `scripts/seed_sample_catalog.py` | SQLAlchemy | Mongo inserts |
| `scripts/seed_demo_students.py` | SQLAlchemy | Mongo inserts |

**Delete or archive:** entire PostgreSQL migration section in old `database.py` (~600 lines of `ALTER TABLE`).

#### Environment & deploy

| Variable | Example |
| -------- | ------- |
| `MONGODB_URI` | `mongodb+srv://user:pass@cluster.mongodb.net/assesment?retryWrites=true&w=majority` |
| `MONGODB_DB_NAME` | `assesment` (optional; default from URI path) |

Update `.env.example`, README:

- **Quick start:** Atlas URI instead of `docker compose up` for DB (Docker Postgres optional for legacy local dev during transition, then remove).
- Document Atlas IP allowlist (`0.0.0.0/0` for dev or app server IP for prod).
- Remove `DATABASE_URL` / `POSTGRES_*` from required vars after cutover.

**`docker-compose.yml`:** Remove `db` service (or mark deprecated in comment) once migration is complete.

#### Data migration (existing Postgres → Atlas)

One-shot script: `scripts/migrate_postgres_to_mongodb.py`

1. Read `DATABASE_URL` (source) + `MONGODB_URI` (target).
2. Export tables in FK order: languages → topics → question_bank → assessments → assessment_questions → submissions → attempts → mastery → certificates.
3. Preserve integer `id` values and string `assessment_id`s.
4. Seed `counters` collection to `max(id)` per collection.
5. Dry-run mode (`--dry-run`) + row counts printed.

**Cutover strategy:**

1. Deploy code with Mongo support behind env flag **or** hard cutover (recommended: single PR, migrate script, update prod `.env`).
2. Run migration script on staging; run full manual QA script.
3. Point production to Atlas; retire Postgres container.

#### Testing strategy

| Area | Approach |
| ---- | -------- |
| Unit tests | Keep mocks — most tests already patch `_session()` |
| Integration | Optional `MONGODB_URI` test DB; or `mongomock` for lightweight CI |
| Regression | Full `pytest tests/ -q` after migration |
| Manual QA | Re-run [task.md](task.md) manual QA script end-to-end on Atlas |

Update `tests/TEST_GUIDE.md`: “MongoDB (or mocked) instead of PostgreSQL”.

#### Docs

- `README.md` — Atlas setup, env vars, remove Postgres-first quick start
- `ARCHITECTURE.md` — MongoDB + question bank (replace CSV/Postgres wording)
- `plan.md` / `task.md` — mark 11B complete when done

**Exit criteria:** App runs with only `MONGODB_URI` set; seed script works; admin generate/recycle, client submit, question bank, improvement flows, and employee report all work against Atlas; no Postgres container required on cloud server.

**Suggested 11B sub-sessions (for agents):**

```text
11B-1  database.py + indexes + counters + ping/init
11B-2  catalog_service + seed_sample_catalog.py
11B-3  db_service (assessments, questions, submissions)
11B-4  question_bank_service + mastery
11B-5  attempt, certificate, profile, report services
11B-6  migrate script + README + docker-compose cleanup + full test pass
```

**Agent handoff:** “Implement 11B-n sub-session only; do not change LLM providers unless fixing a regression.”

---

### Stage 8 — Future backlog (platform / ops)


| Item                                       | Notes                                                              |
| ------------------------------------------ | ------------------------------------------------------------------ |
| **4B report polish**                       | QR code deferred — see **4B optional polish**                      |
| Employee login                             | `employee_id` today is self-declared; later tie to SSO/users table |
| Question retirement                        | Admin retires high-wrong or low-discrimination items               |
| Seeding bank from `seed_sample_catalog.py` | Bulk import script for demo environments                           |
| ARCHITECTURE.md update                     | Reflect MongoDB Atlas + question bank (Stage 11B); was CSV/PostgreSQL |
| **LinkedIn certificate share**             | Stage 10 optional — after certificate v1                           |


**Not scheduled:** email delivery (`POST /admin/employee-report/send`).

---

## 6. Per-topic selection algorithms

### Admin — recycle then generate (Stage 2)

For catalog mode with `per_topic_config`:

```text
for each topic T:
  for each type in {mcq, coding, subjective}:
    needed = per_topic_config[T][type]
    found, shortage = find_bank_questions([T], level, needed,
      exclude_employee_id=..., exclude_mastered_only=true)
    append found to rows
    if shortage > 0 and question_source == "recycle_then_generate":
      generate shortage via LLM → admin review → confirm
```

### Client — bank only (Stages 5–7)

```text
for each topic T in selected topics:
  for each type with needed count:
    found, shortage = find_bank_questions(..., exclude_mastered_only=true)
    append found to rows
    # shortage > 0: do NOT generate — record for availability_message
deliver len(rows) questions; if len(rows) < questions_requested, show message
if len(rows) == 0: no assessment created — explain why
```

**Ordering:** Interleave or group by topic to match current assessment UX (keep topic blocks consistent with today).

**Deduplication:** Within one assessment, never attach the same `bank_question_id` twice.

---

## 7. Messaging copy (admin + client)

**Admin shortage (recycle then generate):**

> Only **{available}** questions available for the selected topics at **{level}** level. We will generate **{shortage}** new questions.

**Per-topic variant:**

> **{topic_name}:** {available} available, generating {shortage} new.

**Client improvement — shortage:**

> You asked for **{requested}** questions, but based on availability there are only **{delivered}** valid questions for you in our question bank.

**Client improvement — all mastered:**

> You have already answered all available questions correctly for **{topic}** at **{level}** level. Great work — check back later or try another improvement path.

**Client weak areas:**

> Based on your last 3 assessments, we recommend extra practice on: **{topic list}**.

**Client new areas / difficulty:**

> Based on your full assessment history, …

**Coding question — sample test cases footer:**

> These examples help you validate your solution; make sure you also consider edge cases beyond the examples shown.

**Certificate success modal:**

> Your grade is **{grade}%**. You earned your certificate for Python **{level}**! What name would you like on your certificate?

---

## 8. Testing strategy


| Stage | Tests                                                                     |
| ----- | ------------------------------------------------------------------------- |
| 1     | `tests/test_question_bank_service.py` — unit                              |
| 2     | `tests/test_assessment_recycle.py` — hybrid generation, shortage metadata |
| 4A    | `tests/test_employee_profile_service.py` — rollup, unexplored topics      |
| 4B    | `tests/test_employee_report_service.py` — timeline, time-on-platform      |
| 5–7   | API integration tests + manual QA on `/client`                            |
| 9A    | Prompt/regression: no file-read coding questions in generated preview     |
| 9B    | Schema + review UI: `sample_test_cases` round-trip                        |
| 9C    | Submit response: decimal display mapping from stored scores               |
| 9D    | Generation: beginner hints present only when flag on; never full solution |
| 10    | Certificate issue: threshold, modal, admin grant, audit row               |
| 11A   | `generation_provider` schema; Gemini provider; AdminPage picker; health    |
| 11B   | Mongo collections + services; migrate script; README; full regression   |


---

## 9. Related docs


| File                                                           | Topic                                             |
| -------------------------------------------------------------- | ------------------------------------------------- |
| [task.md](task.md)                                             | Checkbox tasks per stage                          |
| [README.md](README.md)                                         | Runbook, API table                                |
| [docs/assessment-generation.md](docs/assessment-generation.md) | Per-topic allocation + LLM constraints (Stage 9A) |
| [docs/tier1-presets.md](docs/tier1-presets.md)                 | Preset combos (good test fixture for recycle)     |
| [Plan.md](Plan.md) / [Task.md](Task.md)                        | Separate Tier 1 preset feature (complete)         |


---

## 10. Suggested agent execution order

```text
Stage 0 ✅ → Stage 1 ✅ → Stage 2 ✅ → Stage 3 ✅ (parallel ok after 1)
                                    ↘
Stage 4 ✅ → Stage 5 ✅ → Stage 6 ✅ → Stage 7 ✅
         ↘
         4B optional polish (heatmap, cumulative, radar UI) — anytime after 4B core

Phase 2 (certificates & quality):
Stage 9A → Stage 9B + 9D (parallel) → Stage 9C → Stage 10 → Stage 10 optional (LinkedIn)

Phase 3 (infra — active next):
Stage 11A (Grok vs Gemini) → Stage 11B-1 … 11B-6 (MongoDB Atlas; multi-session)
```

Stages **0–7** are complete. **Phase 2 (9–10)** and **Phase 3 (11A–11B)** are on the roadmap. **4B optional polish** and **Stage 8** remain enhancements / backlog.