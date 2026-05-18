/**
 * Map catalog `languages.code` to Monaco `language` prop (built-in IDs).
 * Unknown codes default to "python" for a sensible highlight baseline.
 */
const BY_CODE = new Map(
  Object.entries({
    py: "python",
    python: "python",
    js: "javascript",
    javascript: "javascript",
    mjs: "javascript",
    ts: "typescript",
    typescript: "typescript",
    jsx: "javascript",
    tsx: "typescript",
    java: "java",
    kotlin: "kotlin",
    kt: "kotlin",
    go: "go",
    golang: "go",
    rs: "rust",
    rust: "rust",
    c: "c",
    cpp: "cpp",
    "c++": "cpp",
    cxx: "cpp",
    cs: "csharp",
    csharp: "csharp",
    rb: "ruby",
    ruby: "ruby",
    php: "php",
    swift: "swift",
    sh: "shell",
    bash: "shell",
    zsh: "shell",
    sql: "sql",
    r: "r",
    dart: "dart",
    lua: "lua",
    pl: "perl",
    perl: "perl",
    ps1: "powershell",
    ps: "powershell",
    scala: "scala",
    html: "html",
    css: "css",
    scss: "scss",
    less: "less",
    json: "json",
    md: "markdown",
    yaml: "yaml",
    yml: "yaml",
  })
);

export const DEFAULT_CODE_EDITOR = "python";

/**
 * @param {string | null | undefined} catalogCode
 * @returns {string} Monaco language id
 */
export function catalogCodeToMonaco(catalogCode) {
  if (catalogCode == null || String(catalogCode).trim() === "") {
    return DEFAULT_CODE_EDITOR;
  }
  const k = String(catalogCode).trim().toLowerCase();
  if (BY_CODE.has(k)) return /** @type {string} */ (BY_CODE.get(k));
  // If admin used a code that matches a Monaco id directly (e.g. "hcl", "dockerfile" — limited set)
  if (/^[a-z0-9+#\-_]+$/i.test(k) && k.length < 32) {
    return k;
  }
  return DEFAULT_CODE_EDITOR;
}
