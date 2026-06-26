/** Stage 12 — client improvement session limits (mirror backend). */

export const PROFICIENCY_THRESHOLD = 75;
export const MAX_QUESTIONS = 15;
export const MAX_TOPICS = 5;
export const DEFAULT_QUICK_PRACTICE_QUESTIONS = 10;

export function practiceIntentLabel(percent) {
  const p = Number(percent);
  if (Number.isNaN(p)) return "Explore (beginner)";
  if (p >= PROFICIENCY_THRESHOLD) return "Step up difficulty";
  return "Improve this topic";
}
