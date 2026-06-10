# Tier 1 evaluation presets — task checklist

Use with **Plan.md**. Estimated: **~2–4 hours** total.

**Status:** v1 implementation complete (2026-06).

---

## 1. Data

- [x] Create `frontend/src/data/tier1EvaluationPresets.json`
- [x] `language_code`: `"py"`
- [x] Three presets: `name` only — `"Beginner"`, `"Intermediate"`, `"Advanced"`
- [x] `target_duration_minutes`: **60**, **90**, **120**
- [x] `topics[]`: `{ topic_name, mcq, coding }` — full rows from Plan.md
- [x] Optional `description` per preset

---

## 2. Helpers

- [x] `frontend/src/lib/tier1Presets.js`
- [x] `getTier1Presets()` / `getPresetByName()` — load JSON
- [x] `presetNameToLevel(name)` → lowercase for API
- [x] `applyPreset(preset, catalogTopics)` → ids, counts, level, duration, types
- [x] `validatePresetAgainstCatalog` via `missingTopicNames` in `applyPreset`
- [x] `sumPresetTotals(perTopicCounts)` → `{ mcq, coding, total }`

---

## 3. Admin UI (`AdminPage.jsx`)

- [x] State: `usePresetTier1`, `selectedPresetName`, `showDistributionEditor`
- [x] Checkbox **Preset Tier 1 evaluation (Python)** (catalog mode only)
- [x] When preset on: auto-select Python, `allocationMode = "per-topic"`, hide manual topic/level/global counts
- [x] Three preset cards with distribution summary + suggested duration
- [x] On card select: `applyPreset`, timed defaults (duration is editable)
- [x] **Edit question distribution** + **Reset to preset**
- [x] Footer totals; catalog validation before generate
- [x] `handleGenerate`: `level` from `presetNameToLevel` when preset on

---

## 4. Styles

- [x] `App.css` — preset cards, selected state, distribution table

---

## 5. Tests

- [x] `tests/test_tier1_presets.py` — topic names in seed, totals 25, durations 60/90/120
- [x] `tests/test_question_stem.py` — MCQ stem / code snippet prettify

---

## 6. Docs

- [x] `README.md` — Tier 1 presets + MCQ code formatting
- [x] `docs/tier1-presets.md` for stakeholders

---

## Manual QA (operator)

1. Enable preset → **Beginner** → totals 25 → Generate → 25 questions, correct topic tags.
2. **Edit distribution** → change one MCQ count → generate still works.
3. **Advanced** → Packaging has 0 coding → no coding item for that topic in client UI.
4. Timed pre-filled 60 / 90 / 120; override minutes still works.
5. Uncheck preset → normal manual flow restored.
6. Missing catalog topic (simulate) → clear error before generate.

---

## Not in this task (out of scope)

- DB persistence of custom presets
- Admin JSON editor for presets
- Tier 2 / Java presets
- New backend routes
