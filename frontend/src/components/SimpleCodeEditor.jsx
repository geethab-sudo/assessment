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
    const ta = textareaRef.current;

    // Tab → insert 4 spaces
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

    // Ctrl+/ or Cmd+/ → toggle line comment
    if ((e.ctrlKey || e.metaKey) && e.key === "/") {
      e.preventDefault();
      const val = ta.value;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;

      // Expand selection to full line boundaries
      const lineStart = val.lastIndexOf("\n", start - 1) + 1;
      const lineEndRaw = val.indexOf("\n", end);
      const lineEnd = lineEndRaw === -1 ? val.length : lineEndRaw;

      const block = val.substring(lineStart, lineEnd);
      const lines = block.split("\n");

      // If every non-empty line already starts with #, uncomment; otherwise comment
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

      // Restore selection to cover the whole modified block
      setTimeout(() => {
        if (ta) {
          ta.selectionStart = lineStart;
          ta.selectionEnd = lineStart + newBlock.length;
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

