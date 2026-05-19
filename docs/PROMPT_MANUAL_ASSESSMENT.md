# Prompt: Manual assessment creation (MCQ + subjective)

Use this spec when implementing or extending **manual** assessments in the AI Assessment platform (`manual` branch).

## Goal

Allow admins to build assessments **without the LLM** by appending questions in the UI:

1. **Multiple choice (MCQ)** — question stem, two or more options (append options), one correct answer (must match an option).
2. **Coding** — prompt text, optional reference solution/rubric; requires catalog **language** for editor syntax.
3. **Subjective** — question stem, optional reference answer for grading context.
3. **Topics** — tie the assessment to catalog language + selected topic names (or a custom topic label).
4. **Assessments list** — saved assessments appear in **Admin → Assessments** with `creation_mode: manual`, sorted by date like AI-generated tests.

## Backend

- **POST** `/admin/assessments/manual` (admin JWT)
- Body:
  ```json
  {
    "language_code": "py",
    "language_label": "Python",
    "topic_names": ["Variables", "Loops"],
    "questions": [
      {
        "type": "mcq",
        "question": "What is 2+2?",
        "options": ["3", "4", "5"],
        "correct_answer": "4"
      },
      {
        "type": "coding",
        "question": "Write a function that returns the sum of a list.",
        "options": [],
        "correct_answer": "def sum_list(xs):\n    return sum(xs)"
      },
      {
        "type": "subjective",
        "question": "Explain a for-loop.",
        "options": [],
        "correct_answer": "Optional rubric for the grader"
      }
    ]
  }
  ```
- Persist via `assessment_service.create_manual_assessment()` → `db_service.save_shared_assessment_rows(..., creation_mode="manual")`.
- Store MCQ `options` as JSON string; `correct_answer` exact match for MCQ scoring.
- Question IDs: `"1"`, `"2"`, … in order appended.

## Database

- `assessments.creation_mode`: `'generated'` | `'manual'` (default `generated`).
- Existing columns: `language_code`, `language_label`, `topic_names`, `created_at`.

## Frontend

- Route: **`/admin/manual`** (`AdminManualPage.jsx`)
- Nav: **Manual** next to Generate
- Flow:
  1. Pick language + catalog topics (or custom topic label).
  2. Choose MCQ or Subjective → fill form → **Append question** (adds to local list).
  3. Repeat; **Save assessment** posts full `questions` array.
  4. Show new `assessment_id`; link to assessments list and participant view.

## Assessments list

- **Type** column: pill `manual` vs `AI` (`creation_mode`).
- **Access** column: `shared` / `client` (unchanged `source` field).

## Out of scope (future)

- Edit questions on an existing assessment
- Import MCQ from CSV

## Acceptance criteria

- [ ] Admin can append ≥1 MCQ with ≥2 options and a valid correct answer.
- [ ] Admin can append ≥1 subjective question.
- [ ] Assessment requires ≥1 topic name.
- [ ] New assessment visible on `/admin/assessments` with type **manual**.
- [ ] Participant can load and submit the manual assessment like AI-generated ones.
