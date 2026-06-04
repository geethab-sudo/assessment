import { useRef, useEffect } from "react";
import { defaultEditorPlaceholder, highlightForLanguage } from "../lib/codeHighlight.js";

export default function SimpleCodeEditor({
  value,
  onChange,
  readOnly = false,
  placeholder,
  minHeight = 280,
  language = "python",
}) {
  const textareaRef = useRef(null);
  const preRef = useRef(null);

  const syncScroll = () => {
    if (textareaRef.current && preRef.current) {
      preRef.current.scrollTop = textareaRef.current.scrollTop;
      preRef.current.scrollLeft = textareaRef.current.scrollLeft;
    }
  };

  useEffect(() => {
    syncScroll();
  }, [value, language]);

  const handleKeyDown = (e) => {
    const ta = textareaRef.current;

    if (e.key === "Tab" && !e.shiftKey) {
      e.preventDefault();
      const val = ta.value;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const spaces = "    ";
      onChange(val.substring(0, start) + spaces + val.substring(end));
      setTimeout(() => {
        if (ta) ta.selectionStart = ta.selectionEnd = start + spaces.length;
      }, 0);
      return;
    }

    if ((e.ctrlKey || e.metaKey) && e.key === "/") {
      e.preventDefault();
      const val = ta.value;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const lineStart = val.lastIndexOf("\n", start - 1) + 1;
      const lineEndRaw = val.indexOf("\n", end);
      const lineEnd = lineEndRaw === -1 ? val.length : lineEndRaw;
      const block = val.substring(lineStart, lineEnd);
      const lines = block.split("\n");
      const allCommented = lines.every(
        (l) => l.trim() === "" || l.trimStart().startsWith("#")
      );
      let newBlock;
      if (allCommented) {
        newBlock = lines
          .map((l) => {
            const trimmed = l.trimStart();
            const indent = l.slice(0, l.length - trimmed.length);
            if (trimmed.startsWith("# ")) return indent + trimmed.slice(2);
            if (trimmed.startsWith("#")) return indent + trimmed.slice(1);
            return l;
          })
          .join("\n");
      } else {
        newBlock = lines.map((l) => (l === "" ? l : "# " + l)).join("\n");
      }
      onChange(val.substring(0, lineStart) + newBlock + val.substring(lineEnd));
      setTimeout(() => {
        if (ta) {
          ta.selectionStart = lineStart;
          ta.selectionEnd = lineStart + newBlock.length;
        }
      }, 0);
    }
  };

  const highlighted = highlightForLanguage(value, language);
  const resolvedPlaceholder = placeholder ?? defaultEditorPlaceholder(language);
  return (
    <div className={`code-editor-container code-editor-container--${language}`} style={{ minHeight }}>
      <pre
        ref={preRef}
        className="code-editor-highlight"
        aria-hidden="true"
        style={{ minHeight }}
        dangerouslySetInnerHTML={{ __html: highlighted + "\n" }}
      />
      <textarea
        ref={textareaRef}
        className="code-editor-textarea"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onScroll={syncScroll}
        onKeyDown={handleKeyDown}
        readOnly={readOnly}
        placeholder={resolvedPlaceholder}
        spellCheck={false}
        autoComplete="off"
        autoCapitalize="off"
        autoCorrect="off"
        style={{ minHeight }}
        aria-label={language === "python" ? "Code answer" : "Shell commands answer"}
      />
    </div>
  );
}
