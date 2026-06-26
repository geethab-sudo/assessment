"""Groq OpenAI-compatible Chat Completions API."""

from __future__ import annotations

import os

from openai import APIStatusError, OpenAI

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

_client: OpenAI | None = None


def normalize_groq_key(raw: str | None) -> str | None:
    """Strip whitespace and optional surrounding quotes often pasted by mistake."""
    if raw is None:
        return None
    key = raw.strip().strip('"').strip("'").strip()
    return key or None


def groq_key_configured() -> bool:
    return normalize_groq_key(os.environ.get("GROQ_API_KEY")) is not None


def _auth_hint() -> str:
    return (
        "Groq returned 401 (invalid API key). (1) Copy a key from "
        "https://console.groq.com/keys (starts with `gsk_`). (2) Put it in `.env` as "
        "GROQ_API_KEY=gsk_... on one line, no quotes. (3) Save the file — unsaved editor "
        "buffers still leave the old placeholder on disk. (4) Restart uvicorn. "
        "If you previously `export`ed GROQ_API_KEY in the terminal, close that shell or "
        "unset it; the app now prefers `.env` over stale env vars."
    )


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = normalize_groq_key(os.environ.get("GROQ_API_KEY"))
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your environment or .env "
                "(create a key at https://console.groq.com/keys)."
            )
        _client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
    return _client


def chat_json_text(
    prompt: str,
    model: str | None = None,
    *,
    temperature: float = 0.4,
) -> str:
    """Chat Completions with JSON object mode."""
    m = model or os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    client = _get_client()
    try:
        response = client.chat.completions.create(
            model=m,
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
            raise RuntimeError(_auth_hint()) from e
        raise RuntimeError(f"Groq API error ({e.status_code}): {e}") from e

    choice = response.choices[0].message
    text = choice.content if choice else None
    if not text:
        raise RuntimeError("Empty response from Groq")
    return text
