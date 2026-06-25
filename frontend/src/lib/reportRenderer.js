/** Escape text for safe HTML insertion. */
function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatReportDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function typeLabel(type) {
  return { mcq: "MCQ", coding: "Coding", subjective: "Subjective" }[type] ?? type;
}

function renderQuestionBlock(q) {
  const status = q.correct ? "Correct" : "Incorrect";
  const statusClass = q.correct ? "ok" : "bad";
  const codeBlock = q.code
    ? `<pre class="code">${escapeHtml(q.code)}</pre>`
    : "";
  return `
    <article class="question">
      <header class="q-head">
        <span class="q-pos">Question ${q.position}</span>
        <span class="q-type">${escapeHtml(typeLabel(q.type))}</span>
        <span class="q-topic">${escapeHtml(q.topic_name)}</span>
        <span class="q-status ${statusClass}">${status} · ${q.score}/100</span>
      </header>
      <p class="q-text">${escapeHtml(q.question)}</p>
      ${codeBlock}
      <div class="q-answer">
        <strong>Your answer</strong>
        <pre>${escapeHtml(q.user_answer || "—")}</pre>
      </div>
      <div class="q-feedback">
        <strong>Feedback</strong>
        <p>${escapeHtml(q.feedback || "No feedback provided.")}</p>
      </div>
    </article>
  `;
}

function renderTopicSummaryRows(rows) {
  if (!rows?.length) {
    return `<tr><td colspan="4">No topic breakdown available.</td></tr>`;
  }
  return rows
    .map(
      (t) => `
    <tr>
      <td>${escapeHtml(t.topic_name)}</td>
      <td>${t.questions_count}</td>
      <td>${t.correct_count ?? t.total_score}/${t.questions_count ?? t.max_score}</td>
      <td>${t.percent}%</td>
    </tr>`
    )
    .join("");
}

/**
 * Build a self-contained HTML document for print / Save as PDF.
 * @param {object} report — payload from GET /assessment/{id}/report
 */
export function renderReportHtml(report) {
  const participant = report.participant || {};
  const name = participant.name || "Participant";
  const employeeId = participant.employee_id || "";
  const questionsHtml = (report.questions || []).map(renderQuestionBlock).join("");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Assessment Report — ${escapeHtml(name)}</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: "Segoe UI", system-ui, sans-serif;
      color: #1e293b;
      margin: 0;
      padding: 24px 28px;
      font-size: 13px;
      line-height: 1.45;
    }
    h1 { font-size: 1.35rem; margin: 0 0 0.25rem; }
    .meta { color: #64748b; margin-bottom: 1.25rem; }
    .summary {
      display: flex;
      gap: 2rem;
      margin-bottom: 1.5rem;
      padding: 1rem 1.1rem;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
    }
    .summary strong { display: block; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; color: #64748b; }
    .summary .big { font-size: 1.6rem; font-weight: 700; color: #0f172a; }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 1.75rem;
      font-size: 12px;
    }
    th, td {
      border: 1px solid #e2e8f0;
      padding: 0.45rem 0.55rem;
      text-align: left;
    }
    th { background: #f1f5f9; }
    .question {
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 0.85rem 1rem;
      margin-bottom: 1rem;
      page-break-inside: avoid;
    }
    .q-head {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem 0.75rem;
      align-items: center;
      margin-bottom: 0.5rem;
      font-size: 11px;
    }
    .q-pos { font-weight: 700; }
    .q-type, .q-topic { color: #64748b; }
    .q-status { margin-left: auto; font-weight: 700; }
    .q-status.ok { color: #15803d; }
    .q-status.bad { color: #b91c1c; }
    .q-text { margin: 0 0 0.5rem; }
    pre, .q-answer pre, .code {
      background: #0f172a;
      color: #e2e8f0;
      padding: 0.55rem 0.65rem;
      border-radius: 6px;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: "Consolas", "Fira Mono", monospace;
      font-size: 11px;
      margin: 0.35rem 0 0.65rem;
    }
    .q-answer pre { background: #f1f5f9; color: #334155; border: 1px solid #e2e8f0; }
    .q-feedback p { margin: 0.35rem 0 0; }
    .footnote { margin-top: 1.5rem; color: #94a3b8; font-size: 11px; }
    @media print {
      body { padding: 12mm; }
      .question { break-inside: avoid; }
    }
  </style>
</head>
<body>
  <h1>Assessment Report</h1>
  <p class="meta">
    ${escapeHtml(name)}${employeeId ? ` · ${escapeHtml(employeeId)}` : ""}
    · Assessment ${escapeHtml(report.assessment_id || "")}
    · Submitted ${escapeHtml(formatReportDate(report.submitted_at))}
  </p>

  <div class="summary">
    <div>
      <strong>Overall average</strong>
      <span class="big">${report.overall_score ?? "—"}</span> / 100
    </div>
    <div>
      <strong>Questions graded</strong>
      <span class="big">${report.questions_graded ?? 0}</span>
    </div>
  </div>

  <h2>Topic summary</h2>
  <table>
    <thead>
      <tr>
        <th>Topic</th>
        <th>Questions</th>
        <th>Score</th>
        <th>Average %</th>
      </tr>
    </thead>
    <tbody>
      ${renderTopicSummaryRows(report.topic_summary)}
    </tbody>
  </table>

  <h2>Question details</h2>
  ${questionsHtml || "<p>No questions in this report.</p>"}

  <p class="footnote">
    In-browser questions only (MCQ and Pyodide coding). Jupyter notebook items are not included in this report.
  </p>
</body>
</html>`;
}

/**
 * Print the report via a hidden iframe (avoids pop-up blockers after async fetch).
 * @param {object} report
 */
export function openReportPrintWindow(report) {
  const html = renderReportHtml(report);
  const iframe = document.createElement("iframe");
  iframe.setAttribute("title", "Assessment report");
  iframe.setAttribute(
    "style",
    "position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden"
  );
  document.body.appendChild(iframe);

  const win = iframe.contentWindow;
  if (!win) {
    iframe.remove();
    throw new Error("Could not prepare the report for printing.");
  }

  const cleanup = () => {
    if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
  };

  win.document.open();
  win.document.write(html);
  win.document.close();
  win.focus();

  // onafterprint is not reliable in all browsers; always remove the iframe eventually
  win.onafterprint = cleanup;
  setTimeout(cleanup, 60_000);

  setTimeout(() => {
    win.print();
  }, 300);
}
