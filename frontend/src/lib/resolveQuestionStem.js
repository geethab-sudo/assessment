import { catalogCodeToMonaco } from "./monacoLanguageMap.js";

const FENCE_RE = /```(\w*)\s*\n([\s\S]*?)```/;

const INLINE_AFTER_COLON =
  /^(.{0,200}?\b(?:following(?:\s+python)?\s+code(?:\s+snippet)?|given (?:the )?(?:following )?code|consider (?:the )?following (?:python )?code|this (?:python )?code(?:\s+snippet)?)\s*:\s*)(.+?)\s*\??\s*$/i;

const IMPLEMENTATION_STEM =
  /\b(write|implement|create|design|develop|build|define|complete|finish)\b.{0,80}\b(function|class|program|method|module|script|routine)\b/i;

const ANALYZE_STEM =
  /output of|what (?:will|would) be printed|what is printed|what does .+ print|following (?:python )?code(?: snippet)?|given (?:the )?(?:following )?code|consider (?:the )?following (?:python )?code|according to (?:the )?code|what (?:will|would) .+ (?:return|output|evaluate)/i;

const STUB_SIGNATURE = /^\s*def\s+\w+\s*\([^)]*\)\s*:\s*$/m;

function prettifyInlineCode(raw) {
  const s = (raw || "").trim().replace(/\?$/, "");
  if (!s) return "";
  if (s.split("\n").length >= 2) return s;
  const parts = s.split(/;\s*/);
  const lines = [];
  for (const part of parts) {
    const p = part.trim();
    if (!p) continue;
    if (p.startsWith("else:") || p.startsWith("elif ")) {
      lines.push("    " + p);
    } else if (lines.length && lines[lines.length - 1].trimEnd().endsWith(":")) {
      lines.push("    " + p);
    } else {
      lines.push(p);
    }
  }
  return lines.join("\n");
}

function extractFencedCodeFromStem(stem) {
  const text = (stem || "").trim();
  if (!text) return { prose: "", code: null, lang: "python" };
  const m = FENCE_RE.exec(text);
  if (!m) return { prose: text, code: null, lang: "python" };
  const lang = (m[1] || "python").trim().toLowerCase() || "python";
  const code = m[2].trim();
  let prose = (text.slice(0, m.index) + text.slice(m.index + m[0].length)).trim();
  prose = prose.replace(/\n{3,}/g, "\n\n");
  return { prose, code: code || null, lang };
}

function extractInlineCodeFromStem(stem) {
  const text = (stem || "").trim();
  const m = INLINE_AFTER_COLON.exec(text);
  if (!m) return { prose: text, code: null };
  let prose = m[1].trim();
  if (!prose.endsWith("?")) {
    prose = prose.replace(/:?\s*$/, "").trim() + "?";
  }
  const raw = m[2].trim().replace(/\?$/, "");
  if (raw.length < 12 || !/[;=()]|def |class |print\(|return |if |for /.test(raw)) {
    return { prose: text, code: null };
  }
  return { prose, code: prettifyInlineCode(raw) };
}

function shouldShowCodeBlock(code, prose) {
  const c = (code || "").trim();
  if (!c) return false;
  if (IMPLEMENTATION_STEM.test(prose || "")) return false;
  if (STUB_SIGNATURE.test(c)) return false;
  const lines = c.split("\n").filter((l) => l.trim());
  if (lines.length === 1 && lines[0].trimEnd().endsWith(":") && lines[0].includes("def ")) {
    return false;
  }
  if (ANALYZE_STEM.test(prose || "")) return true;
  return false;
}

/**
 * @param {string} question
 * @param {string | null | undefined} codeField API `code` field (usually empty now)
 * @param {string | null | undefined} languageCode assessment catalog language
 */
export function resolveQuestionStem(question, codeField, languageCode) {
  let prose = (question || "").trim();
  let code = (codeField || "").trim() || null;
  let lang = catalogCodeToMonaco(languageCode);
  let fromInline = false;

  const inline = extractInlineCodeFromStem(prose);
  if (inline.code) {
    prose = inline.prose;
    code = inline.code;
    fromInline = true;
  } else if (!code) {
    const extracted = extractFencedCodeFromStem(prose);
    prose = extracted.prose;
    code = extracted.code;
    if (extracted.lang && extracted.lang !== "python") {
      lang = catalogCodeToMonaco(extracted.lang);
    }
  }

  if (!fromInline && code && !shouldShowCodeBlock(code, prose)) {
    code = null;
  }

  if (code && prose.includes(code)) {
    prose = prose.replace(code, "").trim().replace(/\n{3,}/g, "\n\n");
  }

  return { prose, code, highlightLanguage: lang };
}
