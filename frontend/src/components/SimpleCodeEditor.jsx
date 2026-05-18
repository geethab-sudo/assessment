/**
 * Lightweight code area (textarea) — no WASM, no heavy editor bundle.
 * Clipboard blocked for the same honor-system policy as other answer fields.
 */
export default function SimpleCodeEditor({
  value,
  onChange,
  readOnly = false,
  placeholder = "Type your code here (paste disabled)…",
  minHeight = 280,
}) {
  const block = (e) => {
    e.preventDefault();
  };

  return (
    <textarea
      className="simple-code-editor"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      readOnly={readOnly}
      placeholder={placeholder}
      spellCheck={false}
      autoComplete="off"
      autoCapitalize="off"
      autoCorrect="off"
      onPaste={block}
      onCopy={block}
      onCut={block}
      style={{ minHeight }}
      aria-label="Code answer"
    />
  );
}
