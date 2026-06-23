/** Format a 0.0–1.0 score for display (one decimal). */
export function formatUnitScore(score) {
  const n = Number(score);
  if (Number.isNaN(n)) return "—";
  return n.toFixed(1);
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
