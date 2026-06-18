/**
 * Insert a 4-space indent at the textarea cursor (Tab key).
 * Works with React controlled textareas — call onValueChange, then restore selection.
 */
export function applyTabIndent(event, value, onValueChange) {
  if (event.key !== "Tab" || event.shiftKey) return false;

  event.preventDefault();
  const el = event.currentTarget;
  const start = el.selectionStart;
  const end = el.selectionEnd;
  const indent = "    ";
  const next = value.slice(0, start) + indent + value.slice(end);
  const cursor = start + indent.length;

  onValueChange(next);

  setTimeout(() => {
    if (document.activeElement === el) {
      el.selectionStart = cursor;
      el.selectionEnd = cursor;
    }
  }, 0);

  return true;
}
