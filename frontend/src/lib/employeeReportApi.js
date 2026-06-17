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
