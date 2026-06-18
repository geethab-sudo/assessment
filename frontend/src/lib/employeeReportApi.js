import { apiFetch } from "../api";

/**
 * @param {{ employeeId: string, period?: string, languageCode?: string, authRole?: "admin" }} opts
 */
export async function fetchEmployeeReport({
  employeeId,
  period = "all_time",
  languageCode,
  authRole,
}) {
  const params = new URLSearchParams({
    employee_id: employeeId.trim(),
    period,
  });
  if (languageCode?.trim()) {
    params.set("language_code", languageCode.trim());
  }
  const path =
    authRole === "admin"
      ? `/admin/employee-report?${params}`
      : `/client/my-report?${params}`;
  return apiFetch(path, authRole === "admin" ? { authRole: "admin" } : {});
}

/**
 * @param {{ employeeId: string, scope?: string, languageCode?: string }} opts
 */
export async function fetchEmployeeProfile({
  employeeId,
  scope = "last_3",
  languageCode,
}) {
  const params = new URLSearchParams({
    employee_id: employeeId.trim(),
    scope,
  });
  if (languageCode?.trim()) {
    params.set("language_code", languageCode.trim());
  }
  return apiFetch(`/client/employee-profile?${params}`);
}

/**
 * @param {{ employeeId: string, languageCode: string, questionsRequested?: number }} opts
 */
export async function createWeakAreasAssessment({
  employeeId,
  languageCode,
  questionsRequested = 15,
}) {
  return apiFetch("/client/improvement/weak-areas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      employee_id: employeeId.trim(),
      language_code: languageCode.trim(),
      questions_requested: questionsRequested,
    }),
  });
}

/**
 * @param {{ employeeId: string, languageCode: string, questionsRequested?: number, topicsCount?: number }} opts
 */
export async function createNewAreasAssessment({
  employeeId,
  languageCode,
  questionsRequested = 15,
  topicsCount = 5,
}) {
  return apiFetch("/client/improvement/new-areas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      employee_id: employeeId.trim(),
      language_code: languageCode.trim(),
      questions_requested: questionsRequested,
      topics_count: topicsCount,
    }),
  });
}
