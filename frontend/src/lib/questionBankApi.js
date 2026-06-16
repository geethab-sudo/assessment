import { apiFetch } from "../api";

/**
 * @param {{ language_code?: string, topic_name?: string, difficulty?: string, question_type?: string }} filters
 */
export async function fetchQuestionBank(filters = {}) {
  const params = new URLSearchParams();
  if (filters.language_code?.trim()) {
    params.set("language_code", filters.language_code.trim());
  }
  if (filters.topic_name?.trim()) {
    params.set("topic_name", filters.topic_name.trim());
  }
  if (filters.difficulty?.trim()) {
    params.set("difficulty", filters.difficulty.trim());
  }
  if (filters.question_type?.trim()) {
    params.set("question_type", filters.question_type.trim());
  }
  const qs = params.toString();
  return apiFetch(`/admin/question-bank${qs ? `?${qs}` : ""}`, { authRole: "admin" });
}
