import { useRef, useEffect } from "react";

function highlightPython(code) {
  if (!code) return "";

  // Escape HTML characters
  let html = code
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Syntax highlighting regex
  const tokenRegex = /(#[^\n]*)|(f?(?:"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'))|(\b(def|class|return|if|else|elif|import|from|as|for|while|in|try|except|finally|raise|assert|with|lambda|pass|break|continue|global|nonlocal|del|yield|and|or|not|is)\b)|(\b(None|True|False)\b)|(\b(print|len|range|str|int|float|list|dict|set|tuple|open|type|enumerate|zip|sum|min|max|any|all|map|filter)\b)|(@[a-zA-Z_][a-zA-Z0-9_]*)/g;

  html = html.replace(tokenRegex, (match, comment, string, keyword, keywordWord, constant, constantWord, builtin, builtinWord, decorator) => {
    if (comment) {
      return `<span class="token-comment">${comment}</span>`;
    }
    if (string) {
      return `<span class="token-string">${string}</span>`;
    }
    if (keyword) {
      return `<span class="token-keyword">${keyword}</span>`;
    }
    if (constant) {
      return `<span class="token-constant">${constant}</span>`;
    }
    if (builtin) {
      return `<span class="token-builtin">${builtin}</span>`;
    }
    if (decorator) {
      return `<span class="token-decorator">${decorator}</span>`;
    }
    return match;
  });

  return html;
}

export default function SimpleCodeEditor({
  value,
  onChange,
  readOnly = false,
  placeholder = "Type or paste your code here…",
  minHeight = 280,
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
  }, [value]);

  const handleKeyDown = (e) => {
    if (e.key === "Tab") {
      e.preventDefault();
      const val = textareaRef.current.value;
      const start = textareaRef.current.selectionStart;
      const end = textareaRef.current.selectionEnd;
      const spaces = "    "; // 4 spaces
      const newValue = val.substring(0, start) + spaces + val.substring(end);
      onChange(newValue);

      // Reset selection cursor (we need to defer it slightly so React state updates first)
      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.selectionStart = textareaRef.current.selectionEnd = start + spaces.length;
        }
      }, 0);
    }
  };

  const highlighted = highlightPython(value);

  return (
    <div className="code-editor-container" style={{ minHeight }}>
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
        placeholder={placeholder}
        spellCheck={false}
        autoComplete="off"
        autoCapitalize="off"
        autoCorrect="off"
        style={{ minHeight }}
        aria-label="Code answer"
      />
    </div>
  );
}

