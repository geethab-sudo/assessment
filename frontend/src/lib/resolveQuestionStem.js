import { catalogCodeToMonaco } from "./monacoLanguageMap.js";

/**
 * Map API question fields to display-ready values.
 *
 * The backend (assessment_service.get_assessment_for_user) already splits
 * each question stem into `question` (prose) and `code` (formatted snippet)
 * via split_stem_for_display / prettify_inline_code. This function just
 * passes those through and maps the catalog language code to a Monaco id.
 *
 * @param {string} question  Prose text returned by the API.
 * @param {string | null | undefined} codeField  Code snippet returned by the API (field "code").
 * @param {string | null | undefined} languageCode  Catalog language code (e.g. "py").
 * @returns {{ prose: string, code: string | null, highlightLanguage: string }}
 */
export function resolveQuestionStem(question, codeField, languageCode) {
  const prose = (question || "").trim();
  const code = (codeField || "").trim() || null;
  const highlightLanguage = catalogCodeToMonaco(languageCode);
  return { prose, code, highlightLanguage };
}
