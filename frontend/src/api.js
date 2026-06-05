/**
 * Base URL for FastAPI. In dev, Vite proxies `/api` to the backend.
 */
import { notifyAuthChange } from "./authEvents";

const API_BASE = import.meta.env.VITE_API_URL || "/api";

export const STORAGE_ADMIN_TOKEN = "ai_assessment_admin_token";
export const STORAGE_CLIENT_TOKEN = "ai_assessment_client_token";

// sessionStorage is used intentionally:
// - Tokens are scoped to the browser tab, not persisted across sessions.
// - XSS cannot reach tokens from other tabs (unlike localStorage which is shared).
// - Logging out by closing the tab is expected behaviour for this app.

export function getAdminToken() {
  return sessionStorage.getItem(STORAGE_ADMIN_TOKEN);
}

export function getClientToken() {
  return sessionStorage.getItem(STORAGE_CLIENT_TOKEN);
}

export function setAdminToken(token) {
  if (token) {
    sessionStorage.setItem(STORAGE_ADMIN_TOKEN, token);
  } else {
    sessionStorage.removeItem(STORAGE_ADMIN_TOKEN);
  }
  notifyAuthChange();
}

export function setClientToken(token) {
  if (token) {
    sessionStorage.setItem(STORAGE_CLIENT_TOKEN, token);
  } else {
    sessionStorage.removeItem(STORAGE_CLIENT_TOKEN);
  }
  notifyAuthChange();
}

export function logoutAdmin() {
  sessionStorage.removeItem(STORAGE_ADMIN_TOKEN);
  notifyAuthChange();
}

export function logoutClient() {
  sessionStorage.removeItem(STORAGE_CLIENT_TOKEN);
  notifyAuthChange();
}

/**
 * @param {string} path
 * @param {RequestInit & { authRole?: "admin" | "client" }} options Omitted or undefined authRole: no Authorization header (public GET /assessment, POST /submit-assessment).
 */
export async function apiFetch(path, options = {}) {
  const { authRole, ...rest } = options;
  const headers = {
    ...rest.headers,
  };
  if (!(rest.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (authRole === "admin") {
    const t = getAdminToken();
    if (t) headers.Authorization = `Bearer ${t}`;
  } else if (authRole === "client") {
    const t = getClientToken();
    if (t) headers.Authorization = `Bearer ${t}`;
  }

  const url = `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    ...rest,
    headers,
  });
  const text = await res.text();
  let data;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text || "Invalid JSON from server" };
  }
  if (!res.ok) {
    const msg = data?.detail ?? res.statusText;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}
