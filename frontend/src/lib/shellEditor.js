/** Catalog / API values for terminal-style coding topics. */
export const SHELL_EDITOR_CODES = ["shell", "powershell"];

/**
 * @param {string | null | undefined} codingEditorLanguage
 * @returns {boolean}
 */
export function isShellCodingTopic(codingEditorLanguage) {
  const k = (codingEditorLanguage || "").trim().toLowerCase();
  return SHELL_EDITOR_CODES.includes(k);
}

/**
 * Resolve catalog code for Monaco / editor (shell topics only).
 * @param {string | null | undefined} overrideCode from per-question language picker
 * @param {string | null | undefined} topicDefault from API coding_editor_language
 * @returns {"shell" | "powershell"}
 */
export function resolveShellEditorCode(overrideCode, topicDefault) {
  const o = (overrideCode || "").trim().toLowerCase();
  if (SHELL_EDITOR_CODES.includes(o)) return o;
  const t = (topicDefault || "shell").trim().toLowerCase();
  return t === "powershell" ? "powershell" : "shell";
}
