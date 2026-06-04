"""
Normalize MCQ / question stems: format embedded code for display, not add code everywhere.

Goals:
- Split inline one-liner snippets (e.g. after "following Python code snippet:") into prose + code block.
- Do NOT keep LLM "code" fields for write/implement questions or empty stubs (def foo():).
"""

from __future__ import annotations

import re
from typing import Any

_FENCE_RE = re.compile(r"```(\w*)\s*\n([\s\S]*?)```", re.MULTILINE)

# MCQ asks candidate to write/implement — never show a separate code block
_IMPLEMENTATION_STEM = re.compile(
    r"(?i)\b("
    r"write|implement|create|design|develop|build|define|complete|finish"
    r")\b.{0,80}\b(function|class|program|method|module|script|routine)\b"
)

# MCQ presents code to read (output / behavior)
_ANALYZE_STEM = re.compile(
    r"(?i)("
    r"output of|what (?:will|would) be printed|what is printed|what does .+ print|"
    r"following (?:python )?code(?: snippet)?|given (?:the )?(?:following )?code|"
    r"consider (?:the )?following (?:python )?code|according to (?:the )?code|"
    r"what (?:will|would) .+ (?:return|output|evaluate)"
    r")"
)

_INLINE_AFTER_COLON = re.compile(
    r"(?i)^(.{0,200}?\b(?:"
    r"following(?:\s+python)?\s+code(?:\s+snippet)?|"
    r"given (?:the )?(?:following )?code|"
    r"consider (?:the )?following (?:python )?code|"
    r"this (?:python )?code(?:\s+snippet)?"
    r")\s*:\s*)(.+?)\s*\??\s*$"
)

_STUB_SIGNATURE = re.compile(r"^\s*def\s+\w+\s*\([^)]*\)\s*:\s*$", re.MULTILINE)


def strip_markdown_fence(code: str) -> str:
    """Remove wrapping ``` fences if present."""
    text = (code or "").strip()
    if not text.startswith("```"):
        return text
    m = _FENCE_RE.fullmatch(text) or _FENCE_RE.search(text)
    if m:
        return m.group(2).strip()
    lines = text.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def is_implementation_prompt(question: str) -> bool:
    return bool(_IMPLEMENTATION_STEM.search(question or ""))


def is_snippet_analysis_prompt(question: str) -> bool:
    return bool(_ANALYZE_STEM.search(question or ""))


def is_stub_only_code(code: str) -> bool:
    """Reject lone signatures like `def find_max(numbers):` with no body."""
    c = (code or "").strip()
    if not c:
        return True
    if _STUB_SIGNATURE.fullmatch(c):
        return True
    lines = [ln for ln in c.splitlines() if ln.strip()]
    if len(lines) == 1 and lines[0].rstrip().endswith(":") and "def " in lines[0]:
        return True
    return False


def prettify_inline_code(raw: str) -> str:
    """Turn semicolon-separated one-liners into readable multi-line source."""
    s = (raw or "").strip().rstrip("?")
    if not s:
        return ""
    if s.count("\n") >= 2:
        return s
    parts = re.split(r";\s*", s)
    lines: list[str] = []
    for part in parts:
        p = part.strip()
        if not p:
            continue
        if p.startswith(("else:", "elif ")):
            lines.append("    " + p)
        elif lines and lines[-1].rstrip().endswith(":"):
            lines.append("    " + p)
        else:
            lines.append(p)
    return "\n".join(lines)


def extract_inline_code_from_prose(text: str) -> tuple[str, str | None]:
    """
    Pull embedded one-line code after intro phrases like
    'following Python code snippet: x = 1; print(x)'.
    """
    stem = (text or "").strip()
    if not stem:
        return "", None
    m = _INLINE_AFTER_COLON.match(stem)
    if not m:
        return stem, None
    prose = m.group(1).strip()
    if not prose.endswith("?"):
        prose = prose.rstrip(":").strip() + "?"
    raw_code = m.group(2).strip().rstrip("?")
    if len(raw_code) < 12:
        return stem, None
    if not re.search(r"[;=()]|def |class |print\(|return |if |for ", raw_code):
        return stem, None
    return prose, prettify_inline_code(raw_code)


def extract_code_fence_from_stem(text: str) -> tuple[str, str | None]:
    """Split ```lang\\n...``` blocks out of the question stem."""
    stem = (text or "").strip()
    if not stem:
        return "", None
    m = _FENCE_RE.search(stem)
    if not m:
        return stem, None
    code = m.group(2).strip()
    prose = (stem[: m.start()] + stem[m.end() :]).strip()
    prose = re.sub(r"\n{3,}", "\n\n", prose)
    return prose, code or None


def should_keep_stored_code(code: str, question: str, qtype: str) -> bool:
    """Whether a separate code_snippet field should be shown / stored."""
    c = (code or "").strip()
    if not c:
        return False
    if qtype != "mcq":
        return False
    if is_implementation_prompt(question):
        return False
    if is_stub_only_code(c):
        return False
    if not is_snippet_analysis_prompt(question):
        return False
    return True


def split_stem_for_display(
    question: str,
    stored_code: str | None = None,
) -> tuple[str, str | None]:
    """
    Prose + optional code block for UI and API.
    Prefers parsing embedded inline/fenced code from question text.
    """
    prose = (question or "").strip()
    code: str | None = None
    had_inline = False
    had_fence = False

    prose, inline = extract_inline_code_from_prose(prose)
    if inline:
        code = inline
        had_inline = True
    else:
        prose, fenced = extract_code_fence_from_stem(prose)
        if fenced:
            code = fenced
            had_fence = True

    stored = strip_markdown_fence(stored_code or "")
    if stored and should_keep_stored_code(stored, prose, "mcq"):
        if not code:
            code = stored
        elif stored not in (code or ""):
            code = stored

    if code and code in prose:
        prose = prose.replace(code, "").strip()
        prose = re.sub(r"\n{3,}", "\n\n", prose)

    if code and not had_inline and not had_fence:
        if not should_keep_stored_code(code, prose, "mcq"):
            code = None

    return prose, code


def normalize_generated_question(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize one LLM question dict after generation."""
    qtype = str(raw.get("type", "")).lower().strip()
    text = str(raw.get("question", "")).strip()
    answer = str(raw.get("answer", "")).strip()
    options = raw.get("options") or []
    if not isinstance(options, list):
        options = []

    explicit = ""
    if raw.get("code") is not None and str(raw.get("code")).strip():
        explicit = strip_markdown_fence(str(raw.get("code")))

    prose, code = split_stem_for_display(text, explicit if qtype == "mcq" else "")

    if qtype != "mcq":
        code = None

    out: dict[str, Any] = {
        "id": raw.get("id"),
        "type": qtype,
        "question": prose,
        "options": options,
        "answer": answer,
        "code_snippet": code or "",
    }
    return out


def format_question_for_grading(question: str, code_snippet: str | None = None) -> str:
    """Build full stem text for LLM grading (prose + code block)."""
    prose, code = split_stem_for_display(question, code_snippet)
    if not code:
        return prose
    if code in prose:
        return prose
    return f"{prose}\n\nCode:\n```\n{code}\n```".strip() if prose else f"Code:\n```\n{code}\n```"
