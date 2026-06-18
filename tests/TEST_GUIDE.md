# Test suite guide

This folder contains automated tests for the assessment platform backend and related frontend data contracts. Tests are designed to run **without a live PostgreSQL database** in most cases — they mock DB sessions, patch service calls, or exercise pure functions only.

## How to run

From the project root (with the virtualenv active):

```bash
# Full suite (pytest discovers unittest and pytest-style tests)
python -m pytest tests/ -q

# Single file — unittest
python -m unittest tests.test_improvement_assessment_service -v

# Single file — pytest
python -m pytest tests/test_notebook_plan_service.py -v
```

`conftest.py` adds the repo root to `sys.path` so `from services...` imports work. Many unittest files also set up `sys.path` themselves when run directly.

**Do not** run `python tests/foo.py` as a plain script unless `PYTHONPATH` includes the repo root; prefer `python -m unittest` or `pytest`.

---

## Test layers

| Layer | What it checks | Typical technique |
|-------|----------------|-------------------|
| **Unit** | Pure helpers, no I/O | Direct function calls |
| **Service unit** | Orchestration with mocked DB/LLM | `unittest.mock.patch` |
| **HTTP / API** | Routes, auth, OpenAPI | FastAPI `TestClient` |
| **Contract / config** | Presets ↔ catalog alignment | JSON fixtures + seed data |

---

## File index

### Infrastructure

| File | Module under test | What we verify |
|------|-------------------|----------------|
| [`conftest.py`](conftest.py) | — | Pytest path setup for `services` imports |

### IDs and low-level utilities

| File | Module under test | What we verify |
|------|-------------------|----------------|
| [`test_assessment_ids.py`](test_assessment_ids.py) | `services.ids` | `ASM-XXXXXXXX` format, uniqueness, legacy UUID acceptance, rejection of invalid IDs |
| [`test_shuffle_service.py`](test_shuffle_service.py) | `services.shuffle_service` | Deterministic per-employee question order and MCQ option shuffle |
| [`test_question_stem.py`](test_question_stem.py) | `services.question_stem` | MCQ stem/code splitting, prettify, LLM output normalization (stub code discarded) |
| [`test_attempt_service.py`](test_attempt_service.py) | `services.attempt_service` | Timed assessment config, employee ID normalization, submit deadline slack |

### Assessment generation and delivery

| File | Module under test | What we verify |
|------|-------------------|----------------|
| [`test_assessment_service_unit.py`](test_assessment_service_unit.py) | `services.assessment_service` | CSV/options parsing, correctness rules, routing flags, row builders, notebook template, **already-submitted** blocks repeat load |
| [`test_assessment_recycle.py`](test_assessment_recycle.py) | `services.assessment_service._build_assessment_rows` | Admin **recycle_then_generate**: bank + LLM hybrid, shortage stats; **generate_new**: LLM-only |
| [`test_notebook_plan_service.py`](test_notebook_plan_service.py) | `services.notebook_plan_service` | Per-topic question allocation, Jupyter vs Pyodide coding expectations, validation after generation |

### Question bank (Stage 1)

| File | Module under test | What we verify |
|------|-------------------|----------------|
| [`test_question_bank_service.py`](test_question_bank_service.py) | `services.question_bank_service` | Difficulty normalization, tier→level inference, bank upsert, mastery detection, `find_bank_questions`, availability counts, employee mastery backfill |

### Employee analytics (Stage 4)

| File | Module under test | What we verify |
|------|-------------------|----------------|
| [`test_employee_profile_service.py`](test_employee_profile_service.py) | `services.employee_profile_service` | Profile scopes (`last_3` / `full_history`), weak topics, unexplored topics, level-aware progress labels |
| [`test_employee_report_service.py`](test_employee_report_service.py) | `services.employee_profile_service.get_employee_report` | Shippable report shape: timeline order, time on platform, language rollup, empty employee |
| [`test_report_service.py`](test_report_service.py) | `services.report_service` | Per-assessment participant report; Jupyter coding excluded from in-browser report |

### Client improvement flows (Stages 5–6)

| File | Module under test | What we verify |
|------|-------------------|----------------|
| [`test_improvement_assessment_service.py`](test_improvement_assessment_service.py) | `services.improvement_assessment_service` | **Weak areas**: bank-only, shortage messaging, all-mastered, no LLM. **New areas**: unexplored topics, full_history scope. HTTP smoke tests for both POST endpoints |

### Security, auth, API contract

| File | Module under test | What we verify |
|------|-------------------|----------------|
| [`test_auth_api.py`](test_auth_api.py) | `app` + `routers.admin` | JWT on mutating admin routes; public GET admin lists; login success/failure |
| [`test_security.py`](test_security.py) | Middleware + audit | Security headers, rate-limit 429, audit log on failed login |
| [`test_openapi.py`](test_openapi.py) | OpenAPI schema | Documented routes, Bearer auth on protected ops, error schemas, `/docs` reachable |

> **Note:** `test_openapi.py` maintains an explicit allowlist (`EXPECTED_ROUTES`). When you add new API paths (e.g. client improvement endpoints), update that allowlist or the test will fail on “unexpected route”.

### Frontend / catalog contracts

| File | Module under test | What we verify |
|------|-------------------|----------------|
| [`test_tier1_presets.py`](test_tier1_presets.py) | `tier1EvaluationPresets.json` ↔ `seed_sample_catalog.py` | Preset topic names exist in catalog; 25 questions per preset; duration minutes |

---

## Coverage by product feature

| Feature | Primary test file(s) |
|---------|----------------------|
| Assessment IDs (`ASM-…`) | `test_assessment_ids.py` |
| Participant shuffle | `test_shuffle_service.py` |
| MCQ / code display | `test_question_stem.py` |
| Timed assessments | `test_attempt_service.py` |
| Grading / submit rules | `test_assessment_service_unit.py` |
| Admin bank + LLM hybrid | `test_assessment_recycle.py` |
| Question bank & mastery | `test_question_bank_service.py` |
| Jupyter notebook plans | `test_notebook_plan_service.py` |
| Per-assessment report | `test_report_service.py` |
| Employee profile (weak / unexplored) | `test_employee_profile_service.py` |
| Employee skills report | `test_employee_report_service.py` |
| Help me improve — weak areas | `test_improvement_assessment_service.py` |
| Help me improve — new areas | `test_improvement_assessment_service.py` |
| Help me improve — step up difficulty | `test_improvement_assessment_service.py` |
| Admin JWT auth | `test_auth_api.py` |
| Rate limits & headers | `test_security.py` |
| OpenAPI documentation | `test_openapi.py` |
| Tier 1 admin presets | `test_tier1_presets.py` |

---

## Conventions

- **unittest** is the default style; `test_notebook_plan_service.py` and `test_report_service.py` use **pytest** function tests.
- API tests patch `init_db` / `ping_database` so the app boots without PostgreSQL.
- `RATE_LIMIT_ENABLED=false` in tests avoids flaky 429s unless the test explicitly enables limiting.
- Bank/improvement tests assert **no LLM** is called on client improvement paths (`generate_questions` never invoked).
- Mastery = correct answer only; wrong answers may repeat (see `test_question_bank_service.py`).

---

## Adding tests for new work

1. **New service function** → unit test beside related module (mock DB).
2. **New public API route** → extend `test_openapi.py` `EXPECTED_ROUTES` + optional `TestClient` test in a dedicated or existing API test file.
3. **New improvement flow** → extend `test_improvement_assessment_service.py` with mocked profile + bank rows.
4. **New catalog/preset data** → extend `test_tier1_presets.py` or add a similar contract test.

Keep tests fast: prefer mocks over integration unless the behavior truly needs a database.
