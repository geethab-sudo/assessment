"""
LLM facade: question generation (Groq or Gemini) and answer grading (Groq only).

Get a Groq key at https://console.groq.com/keys — set GROQ_API_KEY in .env
Get a Gemini key at https://aistudio.google.com/apikey — set GOOGLE_API_KEY1 in .env
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from services.llm.providers import (
    assert_generation_provider_configured,
    chat_json_for_generation,
    chat_json_for_grading,
    gemini_key_configured,
    groq_key_configured,
    normalize_generation_provider,
)

# Ensure `.env` is loaded when this module is imported (project root = parent of `services/`)
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

__all__ = [
    "generate_questions",
    "evaluate_answers",
    "groq_key_configured",
    "gemini_key_configured",
    "normalize_generation_provider",
    "_normalize_sample_test_cases",
    "_split_embedded_coding_hint",
]


def _parse_strict_json(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Model did not return valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object")
    return data


_VARIATION_HINTS = (
    "Emphasize short, concrete scenarios rather than abstract definitions alone.",
    "Include at least one question that tests edge cases or common misconceptions.",
    "Where relevant, reference idiomatic Python or the standard library.",
    "Use fresh variable names and numeric examples; avoid overused textbook clichés.",
    "Blend syntax questions with small behavior-prediction snippets.",
)


def _normalize_sample_test_cases(raw: object) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw[:6]:
        if not isinstance(item, dict):
            continue
        inp = str(item.get("input", "")).strip()
        exp = str(
            item.get("expected_output", item.get("output", ""))
        ).strip()
        if not inp and not exp:
            continue
        row: dict[str, str] = {"input": inp, "expected_output": exp}
        label = str(item.get("label", "") or "").strip()
        if label:
            row["label"] = label
        out.append(row)
    return out


def _normalize_coding_hint(raw: object) -> str:
    if not raw:
        return ""
    hint = str(raw).strip()
    if hint.lower().startswith("hint:"):
        hint = hint[5:].strip()
    return hint


_TRAILING_HINT_RE = re.compile(
    r"(?:\n|\s)hint:\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def _split_embedded_coding_hint(question: str) -> tuple[str, str]:
    """Pull a trailing `hint: …` suffix out of the question stem into coding_hint."""
    text = (question or "").strip()
    if not text:
        return "", ""
    m = _TRAILING_HINT_RE.search(text)
    if not m:
        return text, ""
    hint = m.group(1).strip()
    prose = text[: m.start()].rstrip()
    return prose, hint


def generate_questions(
    topic: str,
    difficulty: str,
    types: list[str],
    *,
    questions_per_type: dict[str, int],
    assessment_id: str,
    admin_level: str = "",
    include_sample_test_cases: bool = False,
    include_beginner_coding_hints: bool = False,
    generation_provider: str = "grok",
) -> list[dict[str, Any]]:
    """
    Ask the LLM to generate assessment questions; returns a list of question dicts.
    Each dict: id, type, question, options (list or empty), answer (correct / reference).
    Each assessment_id gets a distinct prompt so successive assessments do not reuse the same items.
    """
    provider = normalize_generation_provider(generation_provider)
    assert_generation_provider_configured(provider)

    type_lines: list[str] = []
    total = 0
    for t in types:
        n = int(questions_per_type.get(t, 0))
        type_lines.append(f'- For type "{t}": create exactly {n} question(s).')
        total += n
    counts_block = "\n".join(type_lines)
    types_str = ", ".join(types)
    h = int(hashlib.sha256(assessment_id.strip().encode()).hexdigest(), 16)
    variation = _VARIATION_HINTS[h % len(_VARIATION_HINTS)]
    gen_temp = float(os.environ.get("GROQ_GENERATION_TEMPERATURE", "0.72"))
    level_norm = admin_level.strip().lower()
    want_test_cases = include_sample_test_cases and "coding" in types
    want_hints = (
        include_beginner_coding_hints
        and level_norm == "beginner"
        and "coding" in types
    )

    test_case_rules = ""
    if want_test_cases:
        test_case_rules = """
- For "coding" questions that ask the candidate to implement a **function or class** (not open-ended scripts):
  include "sample_test_cases": an array of 1-2 objects with "input" and "expected_output" strings.
  Use representative examples only — do NOT list every edge case.
  Omit "sample_test_cases" (or use []) for coding prompts that are not function/class tasks.
"""
    hint_rules = ""
    if want_hints:
        hint_rules = """
- For "coding" questions at beginner level only: include "hint" with a **very short nudge**.
  CRITICAL: the hint must NEVER contain the full answer, complete algorithm, pseudocode for the
  whole solution, or copy-paste-ready code. At most one conceptual or syntax reminder.
  Wrong: "hint: return sum(x for x in lst)". Right: "hint: think about iterating over each element".
  Omit "hint" for non-coding types or if no nudge is appropriate.
"""

    prompt = f"""You are an expert examiner. Generate a NEW set of assessment questions.

Unique assessment instance ID: {assessment_id}
This ID is different for every assessment you generate. You MUST invent fresh questions—
different scenarios, wording, code snippets, and distractors from any other assessment,
including common "template" questions. Do not repeat stock examples if you can avoid it.

Topic: {topic}
Difficulty: {difficulty}
Question types to include: {types_str}
Total questions (all types): {total}

Creative angle for this instance: {variation}

Follow these per-type counts exactly (do not skip or add extra questions):
{counts_block}
Types use these lowercase labels: "mcq", "coding", "subjective".

Rules:
- "mcq": provide "options" as an array of 4 strings and "answer" as the exact correct option text.
  Put the entire stem in "question". Do NOT add a separate "code" field unless absolutely necessary.
  For "what is the output of the following code" style items, put the prompt and the snippet in
  "question" on one line after a colon (e.g. "... code snippet: x = 1; print(x)"). The platform
  will format that snippet for display. Never use "code" for questions that ask the candidate to
  write, implement, create, or design a function/program—those are prose-only.
- "coding": provide empty "options" [] and "answer" as a brief reference solution. Do not use "code".
  The candidate runs code in an **in-browser Python terminal (Pyodide)** with a virtual filesystem.
  For most topics: do NOT ask them to read pre-existing external files that are not created by their
  own script (no mystery attachments). Prefer function/class tasks testable with inline inputs, or
  short scripts whose output is visible in the terminal.
  When the topic instructions below are specifically about **File I/O**, follow those instead:
  ask for scripts that read/write .txt, .csv, or .json using a named filename, stating the file is
  not attached — the student creates it in the terminal.
- "subjective": provide empty "options" [] and "answer" as a short model answer outline. Do not use "code".
{test_case_rules}{hint_rules}
Return ONLY valid JSON (no markdown fences) with this exact shape:
{{
  "questions": [
    {{
      "id": 1,
      "type": "mcq",
      "question": "string",
      "options": ["a","b","c","d"],
      "answer": "correct option text"
    }},
    {{
      "id": 2,
      "type": "coding",
      "question": "string",
      "options": [],
      "answer": "reference solution",
      "sample_test_cases": [{{"input": "example arg", "expected_output": "expected result", "label": "optional"}}],
      "hint": "optional short nudge for beginner coding only"
    }}
  ]
}}

Use sequential integer "id" values starting at 1 across all questions."""

    raw = chat_json_for_generation(provider, prompt, temperature=gen_temp)
    data = _parse_strict_json(raw)
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError('Expected JSON with non-empty "questions" array')

    from services.question_stem import normalize_generated_question

    normalized: list[dict[str, Any]] = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        nq = normalize_generated_question(q)
        item: dict[str, Any] = {
            "id": nq.get("id"),
            "type": nq["type"],
            "question": nq["question"],
            "options": nq["options"],
            "answer": nq["answer"],
            "code_snippet": nq.get("code_snippet") or "",
        }
        if nq["type"] == "coding":
            prose, embedded_hint = _split_embedded_coding_hint(nq["question"])
            if embedded_hint:
                item["question"] = prose
            if want_test_cases:
                cases = _normalize_sample_test_cases(q.get("sample_test_cases"))
                if cases:
                    item["sample_test_cases"] = cases
            if want_hints:
                hint = _normalize_coding_hint(q.get("hint")) or embedded_hint
                if hint:
                    item["coding_hint"] = hint
            elif embedded_hint:
                item["coding_hint"] = embedded_hint
        normalized.append(item)
    if not normalized:
        raise ValueError("No valid questions in model output")
    return normalized


def evaluate_answers(question: str, user_answer: str) -> dict[str, Any]:
    """
    Evaluate a single free-form or structured answer; returns { "score": number, "feedback": string }.
    Score should be 0-100. Always uses Groq (grading provider is not selectable in v1).
    """
    prompt = f"""You grade one exam question fairly and briefly.

Question:
{question}

Student answer:
{user_answer}

Return ONLY valid JSON (no markdown) with this exact shape:
{{
  "score": <number from 0 to 100>,
  "feedback": "<short constructive feedback>"
}}"""

    raw = chat_json_for_grading(prompt)
    data = _parse_strict_json(raw)
    score = data.get("score")
    feedback = data.get("feedback", "")
    try:
        score_num = float(score)
    except (TypeError, ValueError) as e:
        raise ValueError("Evaluation JSON must include numeric score") from e
    score_num = max(0.0, min(100.0, score_num))
    return {"score": score_num, "feedback": str(feedback).strip()}
