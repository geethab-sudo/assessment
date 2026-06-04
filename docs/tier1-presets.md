# Tier 1 evaluation presets (Admin)

## Purpose

Standard **Python Tier 1** assessments for three difficulty bands. Presets fill topic selection, per-topic MCQ/coding counts, LLM difficulty level, and a **suggested** timed duration. Admins can change anything before generating.

## How to use

1. Admin → **Generate assessment**
2. **Catalog: language + topics**
3. Check **Preset Tier 1 evaluation (Python)**
4. Select **Beginner**, **Intermediate**, or **Advanced**
5. Optionally click **Edit question distribution** to change counts or add/remove catalog topics
6. Adjust **Duration (minutes)** under Timed assessment if needed (suggested values: 60 / 90 / 120)
7. **Generate assessment**

## Preset summary

| Preset | Suggested time | MCQ | Coding | Topics |
|--------|----------------|-----|--------|--------|
| Beginner | 60 min | 15 | 10 | 6 fundamentals (data structures, logic, functions, errors, modules, file I/O) |
| Intermediate | 90 min | 15 | 10 | 7 topics (OOP, functions, data structures, iterators, I/O, errors, testing) |
| Advanced | 120 min | 15 | 10 | 7 topics (OOP, generators, testing, iterators, type hints, logic, packaging MCQ-only) |

Data lives in `frontend/src/data/tier1EvaluationPresets.json`. Topic names must match the catalog seed (`scripts/seed_sample_catalog.py`).

## Technical notes

- No new API: same `POST /generate-assessment` with `per_topic_config` and `level`.
- Packaging (Advanced) uses **0 coding** — MCQ only for venv/packaging (shell editor applies when coding is used on that topic elsewhere).
