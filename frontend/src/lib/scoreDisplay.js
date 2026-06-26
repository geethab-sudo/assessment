/** Format a 0.0–1.0 score for display (one decimal). */
export function formatUnitScore(score) {
  const n = Number(score);
  if (Number.isNaN(n)) return "—";
  return n.toFixed(1);
}

/** Format correct-answer count as `correct/total` (e.g. 1/2). */
export function formatCorrectTotal(correct, total) {
  const c = Number(correct);
  const t = Number(total);
  if (Number.isNaN(c) || Number.isNaN(t) || t <= 0) return "—";
  return `${Math.round(c)}/${Math.round(t)}`;
}

/** Count questions marked correct in a submit `question_results` array. */
export function countCorrectResults(questionResults) {
  if (!Array.isArray(questionResults)) return 0;
  return questionResults.filter((q) => q.correct).length;
}

export const SAMPLE_TEST_CASES_NOTE =
  "These examples help you validate your solution; make sure you also consider edge cases beyond the examples shown.";

/** Warn when a coding stem references external files the Pyodide terminal cannot access. */
export function mentionsExternalFile(text) {
  if (!text) return false;
  return /\b(read|open|load|write|parse)\s+(the\s+)?(\w+\.(txt|csv|json|xml|dat)|external file|a file|from disk|from a file)/i.test(
    text
  );
}
