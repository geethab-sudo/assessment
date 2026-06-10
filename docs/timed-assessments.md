# Timed assessments

Timed mode adds per-participant deadlines, auto-submit for in-browser answers, and a grace window for notebook upload.

## Admin configuration

When generating an assessment, enable **Timed assessment** and set:

| Setting | Rules |
|---------|--------|
| **Duration (minutes)** | Required when timed; minimum **1** (no upper cap in v1 — short durations are allowed for testing). |
| **Notebook grace (minutes)** | Optional; defaults to **5**; minimum **0**. Applies only when the assessment `notebook_expected` is true. |

Stored on the `assessments` row: `is_timed`, `duration_minutes`, `notebook_grace_minutes`.

## Participant lifecycle

1. Participant enters employee ID, name, and assessment ID and loads the test.
2. With `employee_id` on `GET /assessment/{id}`, the API creates or returns an `assessment_attempts` row with:
   - `started_at`
   - `main_deadline_at` = started + duration
   - `notebook_deadline_at` = main_deadline + grace (if notebook expected)
3. Response includes a `timer` object (remaining seconds, phase labels) for the UI countdown bar.

### Phases

| Phase | UI | Submit behavior |
|-------|-----|-----------------|
| **Main window** | Countdown to main deadline | Normal submit (in-browser + optional notebook on mixed) |
| **Main expired** | Banner + grace countdown (if notebook expected) | In-browser answers **auto-submit** once at main deadline |
| **Notebook grace** | Upload emphasis | Selecting a `.ipynb` can auto-grade; grace end triggers notebook-only submit if a file is attached |

### Enforcement (backend)

- `attempt_service.assert_main_submit_allowed()` — blocks manual in-browser submit after main deadline (small slack for clock skew).
- `attempt_service.assert_notebook_submit_allowed()` — allows notebook upload until `notebook_deadline_at`.
- Duplicate submit: if any submission exists for `employee_id | name`, `GET /assessment` returns `already_submitted: true` and an empty question list.

Employee ID normalization uses case-insensitive matching on the `user_id` prefix (`{employee_id} | {name}`).

## UI

- Fixed/sticky timer bar when `is_timed` and `timer` are present (`AssessmentTimerBar`, `useAssessmentTimer`).
- Warning styles below 5 minutes and critical below 1 minute.
- Mixed assessments: grace period and auto notebook grading only when `notebook_expected` is true.

## Data model

Table `assessment_attempts` (created by idempotent migration in `services/database.py`):

- Primary key: `(assessment_id, employee_id)`
- `started_at`, `main_deadline_at`, `notebook_deadline_at`, `submitted_at`

See `services/attempt_service.py` for deadline math and tests in `tests/test_attempt_service.py`.
