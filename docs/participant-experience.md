# Participant experience

How the client portal presents assessments, shuffles content, and submits answers.

## Loading an assessment

Route: `/client` → `GET /assessment/{id}?employee_id=…`

Required before questions appear:

- **Employee ID** — used for shuffle seed and timed attempts.
- **Participant name** — stored on submissions as `{employee_id} | {name}`.

## Question labels and feedback

- Display label: **Question 3 of 7** (position in the participant’s shuffled list).
- Internal IDs (`Q1`, `Q4`, …) are for admin/submissions only.
- After submit, **per-question feedback** appears under each card (score + comment), not one combined block at the bottom.

## Randomization

Seed: `assessment_id + employee_id` (name is **not** used).

| Shuffled | Not shuffled |
|----------|----------------|
| Question order on the web UI | Jupyter `.ipynb` template cell order |
| MCQ option order (grading by option text) | Admin preview (`GET` without `employee_id`) |

See `services/shuffle_service.py` and `tests/test_shuffle_service.py`.

## Shell / terminal coding (venv topic)

Some catalog topics set `coding_editor_language` to `shell` or `powershell` (e.g. **Packaging and virtual environments (venv)**). For those coding questions:

- The editor uses Bash or PowerShell syntax highlighting (switchable via **Shell** dropdown). There is no in-browser terminal — participants type commands in the editor only.
- Answers are graded by the LLM on submit; generation prompts steer toward shell commands, not Python scripts for `venv` setup.

Re-run `python scripts/seed_sample_catalog.py` after deploy to set `coding_editor_language` on existing catalog rows.

## Modality on the page

| Question type | `topic_modality` | UI |
|---------------|------------------|-----|
| MCQ | any | Radio options |
| Subjective | any | Textarea |
| Coding | `pyodide` | Code playground + Pyodide run (or **Bash/PowerShell terminal** for topics like venv — see `coding_editor_language`) |
| Coding | `jupyter` | “Complete in Jupyter” placeholder |
| Coding | `null` (legacy) | Code playground |

## Notebook workflow

Shown only when `notebook_expected === true` (not merely `routing_flag === "mixed"`).

### Jupyter-only (`routing_flag === "jupyter"` and notebook expected)

Full-page workspace: download template → solve locally → upload → **Submit notebook**.

### Mixed

- Banner + **Download .ipynb** when notebook expected.
- In-browser questions + single **Submit answers**.
- Optional notebook file at bottom; same submit grades browser answers then notebook.
- Confirm dialog if submitting without a notebook while one is expected.

### No notebook

If all jupyter-tier topics have **zero coding** in the generated set, `notebook_expected` is false: no banner, download, or upload — MCQ/subjective on those tiers stay in the web UI only.

## Timed tests

See [timed-assessments.md](./timed-assessments.md). Summary:

- Countdown bar fixed while scrolling.
- Auto-submit in-browser answers at main deadline.
- Grace window for notebook upload and auto-grade on file select.

## Submit endpoints

| Action | Endpoint |
|--------|----------|
| In-browser answers | `POST /submit-assessment` (body includes `employee_id`) |
| Notebook file | `POST /submit-notebook-assessment` (multipart `.ipynb`) |

Mixed timed flow may call both: auto in-browser at expiry, then notebook during grace.
