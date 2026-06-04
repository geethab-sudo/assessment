import { highlightForLanguage } from "../lib/codeHighlight.js";

/**
 * Read-only syntax-highlighted code block for MCQ / question stems.
 */
export default function McqCodeBlock({ code, language = "python" }) {
  const src = (code || "").trim();
  if (!src) return null;
  const html = highlightForLanguage(src, language);
  const label =
    language === "shell" || language === "sh"
      ? "bash"
      : language === "powershell"
        ? "powershell"
        : language;

  return (
    <figure className="mcq-code-block" aria-label="Code snippet">
      <figcaption className="mcq-code-block-lang">{label}</figcaption>
      <pre className="mcq-code-block-pre">
        <code
          className="mcq-code-block-code"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </pre>
    </figure>
  );
}
