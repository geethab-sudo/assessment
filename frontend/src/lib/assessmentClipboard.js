/** Prevent copy/cut from protected assessment content (e.g. MCQ code snippets). */
export function blockCopyEvent(event) {
  event.preventDefault();
}

/** Prevent paste and drag-drop into coding editors during an assessment. */
export function blockPasteEvent(event) {
  event.preventDefault();
}
