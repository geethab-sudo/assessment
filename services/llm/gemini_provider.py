"""Google Gemini API for JSON-mode question generation."""

from __future__ import annotations

import os

from google import genai
from google.genai import errors as genai_errors

_client: genai.Client | None = None

# Tried in order when a model is unavailable (503 high demand, 429, etc.).
DEFAULT_GEMINI_MODEL_CHAIN: tuple[str, ...] = (
    "gemini-3.1-pro-preview",
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
)

# First model in the chain — kept for docs / optional GEMINI_MODEL override.
DEFAULT_GEMINI_MODEL = DEFAULT_GEMINI_MODEL_CHAIN[0]


def normalize_gemini_key(raw: str | None) -> str | None:
    if raw is None:
        return None
    key = raw.strip().strip('"').strip("'").strip()
    return key or None


def gemini_key_configured() -> bool:
    return normalize_gemini_key(os.environ.get("GOOGLE_API_KEY1")) is not None


def _dedupe_preserve_order(models: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for model in models:
        m = model.strip()
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def resolve_gemini_model_chain(explicit: str | None = None) -> list[str]:
    """
    Build the ordered Gemini model list for one generation request.

    Default order:
      gemini-3.1-pro-preview → gemini-3.5-flash → gemini-3-flash-preview → gemini-2.5-flash

    Optional overrides:
    - ``GEMINI_MODEL_CHAIN``: comma-separated list replaces the default chain
    - ``GEMINI_MODEL`` or ``explicit``: prepended (tried first), defaults deduped after
    """
    raw_chain = (os.environ.get("GEMINI_MODEL_CHAIN") or "").strip()
    if raw_chain:
        chain = [m.strip() for m in raw_chain.split(",") if m.strip()]
    else:
        chain = list(DEFAULT_GEMINI_MODEL_CHAIN)

    preferred = (explicit or os.environ.get("GEMINI_MODEL") or "").strip()
    if preferred:
        chain = [preferred, *[m for m in chain if m != preferred]]

    return _dedupe_preserve_order(chain)


def _auth_hint() -> str:
    return (
        "Gemini returned an authentication error. (1) Create an API key at "
        "https://aistudio.google.com/apikey . (2) Put it in `.env` as "
        "GOOGLE_API_KEY1=... on one line, no quotes. (3) Restart the API server."
    )


def _chain_failure_message(chain: list[str], last_exc: BaseException | None) -> str:
    tried = " → ".join(f"`{m}`" for m in chain)
    detail = str(last_exc) if last_exc else "unknown error"
    return (
        f"All Gemini models failed after trying, in order: {tried}. "
        f"Last error: {detail}"
    )


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = normalize_gemini_key(os.environ.get("GOOGLE_API_KEY1"))
        if not api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY1 is not set. Add it to your environment or .env "
                "(create a key at https://aistudio.google.com/apikey)."
            )
        _client = genai.Client(api_key=api_key)
    return _client


def _is_auth_error(exc: BaseException) -> bool:
    code = getattr(exc, "code", None)
    if code in (401, 403):
        return True
    msg = str(exc).lower()
    return "api key" in msg or "permission" in msg or "unauthenticated" in msg


def _is_retryable_error(exc: BaseException) -> bool:
    """Try the next model in the chain for transient / capacity / missing-model errors."""
    code = getattr(exc, "code", None)
    if code in (404, 429, 503):
        return True
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "unavailable",
            "high demand",
            "overloaded",
            "resource exhausted",
            "rate limit",
            "not found",
            "does not exist",
        )
    )


def _generate_once(
    client: genai.Client,
    model: str,
    contents: str,
    *,
    temperature: float,
) -> str:
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config={
            "response_mime_type": "application/json",
            "temperature": temperature,
        },
    )
    text = getattr(response, "text", None)
    if not text or not str(text).strip():
        raise RuntimeError("Empty response from Gemini")
    return str(text).strip()


def chat_json_text(
    prompt: str,
    model: str | None = None,
    *,
    temperature: float = 0.4,
) -> str:
    """
    Generate a single JSON object response via Gemini.

    Uses ``google.genai.Client`` (``client.models.generate_content``). Models are
    attempted in order until one succeeds; see ``resolve_gemini_model_chain``.
    """
    chain = resolve_gemini_model_chain(model)
    if not chain:
        raise RuntimeError("No Gemini models configured in the model chain.")

    client = _get_client()
    system = "You reply only with a single valid JSON object. No markdown."
    contents = f"{system}\n\n{prompt}"

    last_exc: BaseException | None = None
    for index, model_id in enumerate(chain):
        try:
            return _generate_once(client, model_id, contents, temperature=temperature)
        except (genai_errors.ClientError, genai_errors.ServerError) as e:
            if _is_auth_error(e):
                raise RuntimeError(_auth_hint()) from e
            last_exc = e
            if _is_retryable_error(e) and index < len(chain) - 1:
                continue
            code = getattr(e, "code", None)
            raise RuntimeError(f"Gemini API error ({code}) on `{model_id}`: {e}") from e
        except Exception as e:
            if _is_auth_error(e):
                raise RuntimeError(_auth_hint()) from e
            last_exc = e
            if _is_retryable_error(e) and index < len(chain) - 1:
                continue
            raise RuntimeError(f"Gemini API error on `{model_id}`: {e}") from e

    raise RuntimeError(_chain_failure_message(chain, last_exc))
