# Assessment generation and routing

This document describes how the backend generates questions, tags them by topic, and decides when a Jupyter notebook is required.

## Generation modes

### Global allocation (legacy)

When no catalog `topic_names` are sent, the backend makes a **single** LLM call with the combined topic string. Questions are stored with an empty `topic_name`. Routing uses the assessment-level `routing_flag` only.

### Auto allocation (catalog topics, global counts)

When the admin selects multiple catalog topics and sets **global** MCQ/coding/subjective counts (not per-topic mode), the backend:

1. Calls `derive_per_topic_config()` to split counts evenly across topics (remainder distributed to the first topics).
2. Runs **one LLM call per topic** with that topic’s counts.
3. Tags every row with `topic_name` so per-question modality can be resolved.

Example: 4 topics, `{ mcq: 4, coding: 4 }` → each topic gets `{ mcq: 1, coding: 1 }`.

### Per-topic allocation (admin explicit)

When the admin switches to **Per-topic** mode and sets counts per topic, the same per-topic LLM loop runs using `per_topic_config` from the request body instead of the derived split.

## Routing flags

After generation, `save_shared_assessment_rows()` sets `routing_flag` on the assessment row:

| Flag | Condition |
|------|-----------|
| `pyodide` | No jupyter-modality topics in the selection |
| `jupyter` | All selected topics are jupyter-modality |
| `mixed` | Both jupyter and non-jupyter topics |

`routing_flag` describes the **topic mix**, not whether a notebook download is mandatory.

## Notebook expectation (`notebook_expected`)

Notebook UI and `.ipynb` download are driven by **jupyter-topic coding counts**, not by `routing_flag === "mixed"` or the mere presence of jupyter catalog topics.

| Field | Meaning |
|-------|---------|
| `expected_notebook_coding_count` | Sum of **coding** counts configured for jupyter-modality topics |
| `actual_notebook_coding_count` | Coding rows tagged for the notebook (jupyter topic + modality) |
| `notebook_expected` | `expected > 0` — participant may need a notebook |
| `notebook_ready` | `actual > 0` — template can be built |

Examples:

- Mixed assessment with tier-2 **coding** on a jupyter topic → `notebook_expected: true`, template includes those coding questions only.
- Jupyter-tier topic with **MCQ only** (0 coding on that tier) → `notebook_expected: false`, no download/upload UI.
- Legacy jupyter-only assessment without `topic_name` tags → all coding rows count toward the notebook (fallback).

### Validation at generation

If `expected_notebook_coding_count > 0` but `actual_notebook_coding_count === 0` after LLM generation, creation fails with **400** and a clear error. Regenerate with adjusted counts or topics.

### Template endpoint

`GET /assessment/{id}/template`:

- **404** — `notebook_expected` is false (no notebook required).
- **409** — notebook expected but no jupyter coding questions in storage (inconsistent; regenerate).
- **200** — `.ipynb` with one markdown + one empty code cell per jupyter coding question.

## Per-question modality

`GET /assessment/{id}` returns `topic_modality` on each question:

- `pyodide` — answer in browser (MCQ, subjective, Pyodide coding).
- `jupyter` — MCQ/subjective in browser; **coding** shown as “Complete in Jupyter” and included in the template.
- `null` — legacy rows without `topic_name`.

Implementation: `services/notebook_plan_service.py` (`resolve_question_modality`, `derive_per_topic_config`, `notebook_plan_for_assessment`).

## Related API fields

`GET /assessment/{id}?employee_id=…` includes:

```json
{
  "notebook_expected": true,
  "notebook_ready": true,
  "expected_notebook_coding_count": 1,
  "actual_notebook_coding_count": 1,
  "routing_flag": "mixed",
  "jupyter_topic_names": ["Real Async Concurrency: ..."]
}
```

`POST /generate-assessment` accepts `topic_names`, optional `per_topic_config`, `is_timed`, `duration_minutes`, `notebook_grace_minutes`.
