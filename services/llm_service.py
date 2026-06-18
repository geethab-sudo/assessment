"""
LLM calls via configurable providers (Groq, OpenAI, Claude, Gemini).
The active provider and API key are read from the `agents` table at request time.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from openai import APIStatusError, OpenAI

from services import agent_service

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

ClientType = Literal["openai", "anthropic"]


@dataclass(frozen=True)
class ProviderConfig:
    client_type: ClientType
    base_url: str | None
    default_model: str
    display_name: str


PROVIDER_CONFIGS: dict[str, ProviderConfig] = {
    "groq": ProviderConfig(
        client_type="openai",
        base_url="https://api.groq.com/openai/v1",
        default_model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        display_name="Groq",
    ),
    "openai": ProviderConfig(
        client_type="openai",
        base_url="https://api.openai.com/v1",
        default_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        display_name="OpenAI",
    ),
    "gemini": ProviderConfig(
        client_type="openai",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        default_model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
        display_name="Gemini",
    ),
    "claude": ProviderConfig(
        client_type="anthropic",
        base_url=None,
        default_model=os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
        display_name="Claude",
    ),
}


def _normalize_key(raw: str | None) -> str | None:
    if raw is None:
        return None
    key = raw.strip().strip('"').strip("'").strip()
    return key or None


def groq_key_configured() -> bool:
    """Backward-compatible alias: true when a usable LLM agent is configured."""
    return llm_key_configured()


def llm_key_configured() -> bool:
    """True if the selected active agent has a non-empty API key."""
    agent = agent_service.get_selected_agent()
    if not agent:
        return False
    return _normalize_key(agent.get("api_key_masked")) is not None


def get_active_agent_info() -> dict[str, Any] | None:
    """Public summary of the selected agent (no API key)."""
    agent = agent_service.get_selected_agent()
    if not agent:
        return None
    name = agent["agent_name"]
    cfg = PROVIDER_CONFIGS.get(name)
    return {
        "id": agent["id"],
        "agent_name": name,
        "display_name": cfg.display_name if cfg else name,
        "model": cfg.default_model if cfg else None,
    }


def _get_active_agent() -> dict[str, Any]:
    agent = agent_service.get_selected_agent()
    if not agent:
        raise RuntimeError(
            "No active LLM agent is configured. An admin must add an agent and select it "
            "under Admin → Agents."
        )
    api_key = _normalize_key(agent.get("api_key_masked"))
    if not api_key:
        raise RuntimeError(
            f"The selected agent ({agent.get('agent_name', 'unknown')}) has no API key. "
            "Update it in Admin → Agents."
        )
    name = agent["agent_name"]
    cfg = PROVIDER_CONFIGS.get(name)
    if not cfg:
        raise RuntimeError(
            f"Unsupported agent provider: {name!r}. "
            f"Supported: {', '.join(sorted(PROVIDER_CONFIGS))}."
        )
    return {
        "id": agent["id"],
        "agent_name": name,
        "api_key": api_key,
        "config": cfg,
    }


def _auth_hint(provider: str) -> str:
    return (
        f"{provider} returned 401 (invalid API key). Update the API key for this agent "
        "in Admin → Agents, then try again."
    )


def _chat_openai_json(
    *,
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    temperature: float,
    provider_label: str,
) -> str:
    client = OpenAI(api_key=api_key, base_url=base_url)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You reply only with a single valid JSON object. No markdown.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=temperature,
        )
    except APIStatusError as e:
        if e.status_code == 401:
            raise RuntimeError(_auth_hint(provider_label)) from e
        raise RuntimeError(f"{provider_label} API error ({e.status_code}): {e}") from e

    choice = response.choices[0].message
    text = choice.content if choice else None
    if not text:
        raise RuntimeError(f"Empty response from {provider_label}")
    return text


def _chat_anthropic_json(
    *,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float,
) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError(
            "Claude support requires the anthropic package. Install with: pip install anthropic"
        ) from e

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system="You reply only with a single valid JSON object. No markdown.",
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
    except anthropic.AuthenticationError as e:
        raise RuntimeError(_auth_hint("Claude")) from e
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Claude API error ({e.status_code}): {e}") from e

    parts: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    text = "".join(parts).strip()
    if not text:
        raise RuntimeError("Empty response from Claude")
    return text


def _chat_json_text(
    prompt: str,
    model: str | None = None,
    *,
    temperature: float = 0.4,
) -> str:
    active = _get_active_agent()
    cfg: ProviderConfig = active["config"]
    m = model or cfg.default_model
    api_key = active["api_key"]

    if cfg.client_type == "openai":
        return _chat_openai_json(
            api_key=api_key,
            base_url=cfg.base_url or "",
            model=m,
            prompt=prompt,
            temperature=temperature,
            provider_label=cfg.display_name,
        )
    return _chat_anthropic_json(
        api_key=api_key,
        model=m,
        prompt=prompt,
        temperature=temperature,
    )


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


def generate_questions(
    topic: str,
    difficulty: str,
    types: list[str],
    *,
    questions_per_type: dict[str, int],
    assessment_id: str,
) -> list[dict[str, Any]]:
    """
    Ask the LLM to generate assessment questions; returns a list of question dicts.
    Each dict: id, type, question, options (list or empty), answer (correct / reference).
    Each assessment_id gets a distinct prompt so successive assessments do not reuse the same items.
    """
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
- "subjective": provide empty "options" [] and "answer" as a short model answer outline. Do not use "code".

Return ONLY valid JSON (no markdown fences) with this exact shape:
{{
  "questions": [
    {{
      "id": 1,
      "type": "mcq",
      "question": "string",
      "options": ["a","b","c","d"],
      "answer": "correct option text"
    }}
  ]
}}

Use sequential integer "id" values starting at 1 across all questions."""

    raw = _chat_json_text(prompt, temperature=gen_temp)
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
        normalized.append(
            {
                "id": nq.get("id"),
                "type": nq["type"],
                "question": nq["question"],
                "options": nq["options"],
                "answer": nq["answer"],
                "code_snippet": nq.get("code_snippet") or "",
            }
        )
    if not normalized:
        raise ValueError("No valid questions in model output")
    return normalized


def evaluate_answers(question: str, user_answer: str) -> dict[str, Any]:
    """
    Evaluate a single free-form or structured answer; returns { "score": number, "feedback": string }.
    Score should be 0-100.
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

    raw = _chat_json_text(prompt)
    data = _parse_strict_json(raw)
    score = data.get("score")
    feedback = data.get("feedback", "")
    try:
        score_num = float(score)
    except (TypeError, ValueError) as e:
        raise ValueError("Evaluation JSON must include numeric score") from e
    score_num = max(0.0, min(100.0, score_num))
    return {"score": score_num, "feedback": str(feedback).strip()}
