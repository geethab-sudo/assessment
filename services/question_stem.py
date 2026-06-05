"""
Normalize MCQ / question stems: format embedded code for display, not add code everywhere.

Goals:
- Split inline one-liner snippets (e.g. after "following Python code snippet:") into prose + code block.
- Do NOT keep LLM "code" fields for write/implement questions or empty stubs (def foo():).
"""

from __future__ import annotations

import re
from typing import Any

# Maximum number of compound-statement expansion passes before we accept the result.
# 12 covers arbitrarily nested class/def/if blocks without risking an infinite loop.
_MAX_EXPANSION_PASSES = 12

# Minimum character length for an inline code candidate to be separated out.
# Avoids splitting very short tokens like "x = 1" that look like code but are prose.
_MIN_INLINE_CODE_LENGTH = 12

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
    r"what is the output of the following code|"
    r"following(?:\s+python)?\s+code(?:\s+snippet)?|"
    r"given (?:the )?(?:following )?code|"
    r"consider (?:the )?following (?:python )?code|"
    r"this (?:python )?code(?:\s+snippet)?"
    r")\s*:\s*)(.+?)\s*\??\s*$"
)

_MIXED_CODE_OUTPUT_QUESTION = re.compile(
    r"(?is)(?P<code>.*?)\.\s+"
    r"(?P<prose>what is the output of the following code\s*:)\s*"
    r"(?P<trail>.+)$"
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


_COMPOUND_HEAD_BODY = re.compile(
    r"^("
    r"(?:if|elif|while|for|with)\s+.+|"
    r"else|"
    r"class\s+\w+|"
    r"def\s+\w+\s*\([^)]*\)"
    r")\s*:\s+(.+)$",
    re.IGNORECASE,
)


def _expand_compound_line_stripped(stripped: str, indent: str = "") -> list[str]:
    """Split `head: body` onto two lines with indentation under parent."""
    s = (stripped or "").strip()
    if not s:
        return []
    m = _COMPOUND_HEAD_BODY.match(s)
    if not m:
        return [f"{indent}{s}"] if indent or s else []
    head, body = m.group(1).strip(), m.group(2).strip()
    body_indent = indent + "    "
    if not body:
        return [f"{indent}{head}:"]
    return [f"{indent}{head}:", f"{body_indent}{body}"]


def _format_compound_pass(text: str) -> str:
    lines_out: list[str] = []
    for line in (text or "").splitlines():
        if not line.strip():
            lines_out.append("")
            continue
        if re.match(r"^\s+(else|elif)\b", line, re.I):
            lines_out.extend(_expand_compound_line_stripped(line.lstrip(), ""))
            continue
        indent = line[: len(line) - len(line.lstrip())]
        stripped = line.strip()
        if _COMPOUND_HEAD_BODY.match(stripped):
            lines_out.extend(_expand_compound_line_stripped(stripped, indent))
            continue
        lines_out.append(line)
    return "\n".join(lines_out).strip()


_BLOCK_HEADER = re.compile(
    r"^(?:if|elif|else|while|for|with|class|def)\b",
    re.I,
)


def _indent_orphan_body_lines(text: str) -> str:
    """Indent bare statements that continue a preceding block (e.g. second assignment in def)."""
    lines_out: list[str] = []
    expected = ""
    for line in (text or "").splitlines():
        if not line.strip():
            lines_out.append("")
            expected = ""
            continue
        indent = line[: len(line) - len(line.lstrip())]
        stripped = line.strip()
        if indent:
            lines_out.append(line)
            if stripped.endswith(":"):
                expected = indent + "    "
            elif not _BLOCK_HEADER.match(stripped):
                expected = indent
            else:
                expected = ""
            continue
        if expected and not _BLOCK_HEADER.match(stripped):
            lines_out.append(f"{expected}{stripped}")
            continue
        lines_out.append(stripped)
        expected = "    " if stripped.endswith(":") else ""
    return "\n".join(lines_out).strip()


def format_compound_statement_lines(text: str) -> str:
    """Expand inline compound statements; repeat until stable (nested class/def)."""
    result = text or ""
    for _ in range(_MAX_EXPANSION_PASSES):
        next_result = _format_compound_pass(result)
        if next_result == result:
            break
        result = next_result
    return _indent_orphan_body_lines(result)


def extract_mixed_code_output_question(text: str) -> tuple[str, str | None]:
    """
    Split stems like 'class Foo: ... model. What is the output of the following code: print(...)'.
    """
    stem = (text or "").strip()
    if not stem:
        return "", None
    m = _MIXED_CODE_OUTPUT_QUESTION.match(stem)
    if not m:
        return stem, None
    lead = prettify_inline_code(m.group("code").strip())
    trail = prettify_inline_code(m.group("trail").strip().rstrip("?"))
    code = lead
    if trail:
        code = f"{lead}\n\n{trail}" if lead else trail
    prose = m.group("prose").strip()
    if not prose.endswith("?"):
        prose = prose.rstrip(":").strip() + "?"
    return prose, code or None


def prettify_inline_code(raw: str) -> str:
    """Turn semicolon-separated one-liners into readable multi-line source."""
    s = (raw or "").strip().rstrip("?")
    if not s:
        return ""
    if s.count("\n") < 2:
        parts = re.split(r";\s*", s)
        lines: list[str] = []
        for part in parts:
            p = part.strip()
            if not p:
                continue
            if p.startswith(("else:", "elif ")):
                lines.append(p)
            elif lines and lines[-1].rstrip().endswith(":"):
                lines.append("    " + p)
            else:
                lines.append(p)
        s = "\n".join(lines)
    return format_compound_statement_lines(s)


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
    if len(raw_code) < _MIN_INLINE_CODE_LENGTH:
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

    mixed_prose, mixed_code = extract_mixed_code_output_question(prose)
    if mixed_code:
        prose = mixed_prose
        code = mixed_code
        had_inline = True
    else:
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

    if code:
        code = prettify_inline_code(code)

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
