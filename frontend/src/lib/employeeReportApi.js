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

function improvementBody(employeeId, languageCode, extra = {}) {
  return {
    employee_id: employeeId.trim(),
    language_code: languageCode.trim(),
    ...extra,
  };
}

/**
 * @param {{ employeeId: string, languageCode: string, questionsRequested?: number, topicNames?: string[] }} opts
 */
export async function createFocusAreasAssessment({
  employeeId,
  languageCode,
  questionsRequested = 15,
  topicNames,
}) {
  return apiFetch("/client/improvement/weak-areas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(
      improvementBody(employeeId, languageCode, {
        questions_requested: questionsRequested,
        ...(topicNames?.length ? { topic_names: topicNames } : {}),
      })
    ),
  });
}

/** @deprecated use createFocusAreasAssessment */
export const createWeakAreasAssessment = createFocusAreasAssessment;

/**
 * @param {{ employeeId: string, languageCode: string, questionsRequested?: number, topicsCount?: number, topicNames?: string[] }} opts
 */
export async function createNewAreasAssessment({
  employeeId,
  languageCode,
  questionsRequested = 15,
  topicsCount = 5,
  topicNames,
}) {
  return apiFetch("/client/improvement/new-areas", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(
      improvementBody(employeeId, languageCode, {
        questions_requested: questionsRequested,
        topics_count: topicsCount,
        ...(topicNames?.length ? { topic_names: topicNames } : {}),
      })
    ),
  });
}

/**
 * @param {{ employeeId: string, languageCode: string, questionsRequested?: number, topicsCount?: number, topicNames?: string[] }} opts
 */
export async function createDifficultyImprovementAssessment({
  employeeId,
  languageCode,
  questionsRequested = 15,
  topicsCount = 5,
  topicNames,
}) {
  return apiFetch("/client/improvement/difficulty", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(
      improvementBody(employeeId, languageCode, {
        questions_requested: questionsRequested,
        topics_count: topicsCount,
        ...(topicNames?.length ? { topic_names: topicNames } : {}),
      })
    ),
  });
}

/**
 * @param {{ employeeId: string, languageCode: string, topicNames: string[], questionsRequested?: number }} opts
 */
export async function createFromTopicsAssessment({
  employeeId,
  languageCode,
  topicNames,
  questionsRequested = 10,
}) {
  return apiFetch("/client/improvement/from-topics", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(
      improvementBody(employeeId, languageCode, {
        topic_names: topicNames,
        questions_requested: questionsRequested,
      })
    ),
  });
}

/**
 * @param {{ employeeId: string, languageCode: string, questionsRequested?: number }} opts
 */
export async function createQuickPracticeAssessment({
  employeeId,
  languageCode,
  questionsRequested = 10,
}) {
  return apiFetch("/client/improvement/quick-practice", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(
      improvementBody(employeeId, languageCode, {
        questions_requested: questionsRequested,
      })
    ),
  });
}

export {
  fetchCertificateShareMetadata,
  fetchCertificateVerification,
} from "./certificateApi.js";
