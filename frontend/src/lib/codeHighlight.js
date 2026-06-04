export function escapeHtml(code) {
  return code
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function highlightPython(code) {
  if (!code) return "";
  let html = escapeHtml(code);
  const tokenRegex = /(#[^\n]*)|(f?(?:"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'))|(\b(def|class|return|if|else|elif|import|from|as|for|while|in|try|except|finally|raise|assert|with|lambda|pass|break|continue|global|nonlocal|del|yield|and|or|not|is)\b)|(\b(None|True|False)\b)|(\b(print|len|range|str|int|float|list|dict|set|tuple|open|type|enumerate|zip|sum|min|max|any|all|map|filter)\b)|(@[a-zA-Z_][a-zA-Z0-9_]*)/g;
  html = html.replace(tokenRegex, (match, comment, string, keyword, _kw, constant, _c, builtin, _b, decorator) => {
    if (comment) return `<span class="token-comment">${comment}</span>`;
    if (string) return `<span class="token-string">${string}</span>`;
    if (keyword) return `<span class="token-keyword">${keyword}</span>`;
    if (constant) return `<span class="token-constant">${constant}</span>`;
    if (builtin) return `<span class="token-builtin">${builtin}</span>`;
    if (decorator) return `<span class="token-decorator">${decorator}</span>`;
    return match;
  });
  return html;
}

function highlightShell(code) {
  if (!code) return "";
  let html = escapeHtml(code);
  const tokenRegex = /(#[^\n]*)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(\b(?:python3?|pip3?|source|export|cd|ls|mkdir|rm|chmod|venv|activate|deactivate|sudo|apt|brew)\b)|(\$[A-Za-z_][A-Za-z0-9_]*)|(\b\d+\b)/g;
  html = html.replace(tokenRegex, (match, comment, string, keyword, variable, number) => {
    if (comment) return `<span class="token-comment">${comment}</span>`;
    if (string) return `<span class="token-string">${string}</span>`;
    if (keyword) return `<span class="token-keyword">${keyword}</span>`;
    if (variable) return `<span class="token-builtin">${variable}</span>`;
    if (number) return `<span class="token-constant">${number}</span>`;
    return match;
  });
  return html;
}

function highlightPowerShell(code) {
  if (!code) return "";
  let html = escapeHtml(code);
  const tokenRegex = /(#[^\n]*)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(\b(?:python|pip|cd|Set-Location|New-Item|Remove-Item|venv|Activate|deactivate|Import-Module)\b)|(\$[A-Za-z_][A-Za-z0-9_]*)|(\b\d+\b)/gi;
  html = html.replace(tokenRegex, (match, comment, string, keyword, variable, number) => {
    if (comment) return `<span class="token-comment">${comment}</span>`;
    if (string) return `<span class="token-string">${string}</span>`;
    if (keyword) return `<span class="token-keyword">${keyword}</span>`;
    if (variable) return `<span class="token-builtin">${variable}</span>`;
    if (number) return `<span class="token-constant">${number}</span>`;
    return match;
  });
  return html;
}

export function highlightForLanguage(code, language) {
  const lang = (language || "python").toLowerCase();
  if (lang === "shell" || lang === "sh" || lang === "bash") return highlightShell(code);
  if (lang === "powershell" || lang === "ps1") return highlightPowerShell(code);
  return highlightPython(code);
}

export function defaultEditorPlaceholder(language) {
  const lang = (language || "python").toLowerCase();
  if (lang === "shell" || lang === "sh" || lang === "bash" || lang === "powershell" || lang === "ps1") {
    return "";
  }
  return "Type or paste your code here…";
}
