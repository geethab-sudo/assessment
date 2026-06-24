"""Route generation requests to Groq or Gemini; grading uses Groq only."""

from __future__ import annotations

from services.llm import gemini_provider, groq_provider

GENERATION_PROVIDERS = frozenset({"grok", "gemini"})
DEFAULT_GENERATION_PROVIDER = "grok"


def normalize_generation_provider(value: str) -> str:
    provider = (value or DEFAULT_GENERATION_PROVIDER).strip().lower()
    if provider not in GENERATION_PROVIDERS:
        raise ValueError("generation_provider must be grok or gemini")
    return provider


def groq_key_configured() -> bool:
    return groq_provider.groq_key_configured()


def gemini_key_configured() -> bool:
    return gemini_provider.gemini_key_configured()


def generation_provider_configured(provider: str) -> bool:
    p = normalize_generation_provider(provider)
    if p == "gemini":
        return gemini_key_configured()
    return groq_key_configured()


def list_generation_providers_available() -> list[str]:
    out: list[str] = []
    if groq_key_configured():
        out.append("grok")
    if gemini_key_configured():
        out.append("gemini")
    return out


def assert_generation_provider_configured(provider: str) -> None:
    """Raise RuntimeError when the selected generation provider is not configured."""
    p = normalize_generation_provider(provider)
    if p == "gemini" and not gemini_key_configured():
        raise RuntimeError(
            "GOOGLE_API_KEY1 is not set. Add it to `.env` to generate questions with Gemini "
            "(https://aistudio.google.com/apikey), or choose Groq (Groq) instead."
        )
    if p == "grok" and not groq_key_configured():
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to `.env` to generate questions with Groq "
            "(https://console.groq.com/keys), or choose Gemini instead."
        )


def chat_json_for_generation(
    provider: str,
    prompt: str,
    *,
    temperature: float = 0.4,
) -> str:
    """JSON chat completion for question generation."""
    p = normalize_generation_provider(provider)
    assert_generation_provider_configured(p)
    if p == "gemini":
        return gemini_provider.chat_json_text(prompt, temperature=temperature)
    return groq_provider.chat_json_text(prompt, temperature=temperature)


def chat_json_for_grading(prompt: str) -> str:
    """Grading always uses Groq (v1)."""
    return groq_provider.chat_json_text(prompt)
