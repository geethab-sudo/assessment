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
- [x] **D. Progress over time (plots)** — line chart + cumulative data in API
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

---

## Stage 5 — Client: “Help me improve” + weak areas

> **Goal:** `/client` button → weak areas flow → **bank-only** assessment (no LLM, no admin review).  
> **Depends on:** Stage 1 (mastered exclusion), Stage 4  
> **Does not depend on:** Stage 2 (admin hybrid)

### Backend

- [ ] `services/improvement_assessment_service.py`
- [ ] `POST /client/improvement/weak-areas` — body: `employee_id`, `language_code`, optional `questions_requested`
- [ ] Profile `scope=last_3` → `weakest_topics` → `per_topic_config`
- [ ] **`question_source=bank_only`** — `find_bank_questions` only; never call LLM
- [ ] Exclude **mastered** bank IDs for `employee_id`
- [ ] Returns `{ assessment_id?, questions_requested, questions_delivered, availability_message, topic_summary }`
- [ ] If `questions_delivered == 0` → no assessment; return explanation (all mastered or bank empty)
- [ ] If `questions_delivered < questions_requested` → still create assessment + availability message

### Frontend

- [ ] **Help me improve** button on `ClientPage.jsx` (visible when `employee_id` filled)
- [ ] Route or modal: `/client/improve` with three options (only wire **weak areas** in this stage)
- [ ] Show merged **last-3-assessments** topic table (reuse report table styling)
- [ ] Show availability message when delivered &lt; requested
- [ ] **Start practice assessment** → call API → set `assessmentIdInput` and load assessment (or show “nothing left” state)

### Product note

- [ ] **Never** pass LLM-generated questions to participants without admin review
- [ ] Wrong answers may repeat; only mastered (correct) questions are excluded

### Tests

- [ ] API test: weak-areas creates bank-only assessment on weak topics
- [ ] API test: shortage returns 12/15 with message, not LLM fill
- [ ] API test: all mastered → no assessment, clear message

**Acceptance:** Participant opens weak areas → gets only bank questions; if 12 of 15 available, sees shortage message; if all mastered, sees “nothing left” instead of new assessment.

---

## Stage 6 — Client: explore new areas

> **Goal:** Second improvement option — unseen topics; **bank-only**.  
> **Depends on:** Stage 5 (wizard shell), Stage 4

### Backend

- [ ] `POST /client/improvement/new-areas`
- [ ] Profile `scope=full_history` → `unexplored_topic_names`; select top K topics
- [ ] **`question_source=bank_only`** — no LLM
- [ ] Exclude **mastered** bank IDs; same requested/delivered/messaging as Stage 5

### Frontend

- [ ] Wire **Explore new areas** option in improvement wizard
- [ ] Copy: topics not yet assessed (full history); shortage / all-mastered messages

**Acceptance:** User gets bank-only assessment on new topics, or clear message when bank cannot supply questions.

---

## Stage 7 — Client: improve difficulty

> **Goal:** Third option — harder questions on familiar topics; **bank-only**.  
> **Depends on:** Stage 5–6 pattern, Stage 1, Stage 4

### Backend

- [ ] `POST /client/improvement/difficulty`
- [ ] Profile `scope=full_history` → `recommended_difficulty_by_topic`
- [ ] **`question_source=bank_only`** at stepped difficulty — no LLM
- [ ] Exclude mastered questions; handle “all mastered at this level” per topic

### Frontend

- [ ] Wire **Improve difficulty** option
- [ ] Explain stepped level using full-history performance; show shortage / all-mastered messages

**Acceptance:** User receives harder **bank** questions where available; “all mastered at intermediate” messaged clearly.

---

## Stage 8 — Future backlog (not scheduled)

- [ ] Employee authentication (replace self-declared `employee_id`)
- [ ] Admin retire/archive bank question
- [ ] `scripts/seed_question_bank.py` — bulk demo questions from catalog
- [ ] Update [ARCHITECTURE.md](ARCHITECTURE.md) — PostgreSQL + question bank (currently describes CSV)

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

---

## Agent session quick-pick

| If you want to… | Do stage |
|-----------------|----------|
| Fix bank queries / difficulty labels | **1** |
| Refactor seen → mastered exclusion | **1** |
| Let admin recycle questions (bank + LLM + review) | **2** |
| Show bank analytics in admin | **3** |
| Build improvement API foundation | **4A** |
| Build shippable employee stats report | **4B** |
| Add Help me improve button | **5** then **6**–**7** |

Copy the stage block + **Acceptance** line into the agent prompt as scope boundary.
