import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";

function parseScore(s) {
  const n = parseFloat(String(s ?? ""), 10);
  return Number.isFinite(n) ? n : null;
}

/** Format an ISO datetime string into a short, readable local time. */
function formatDate(iso) {
  if (!iso || iso === "—") return "—";
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

/** Extract the employee ID portion from "empid | Full Name" labels. */
function extractEmployeeId(userId) {
  if (!userId) return "";
  const pipe = userId.indexOf("|");
  return pipe === -1 ? userId.trim() : userId.slice(0, pipe).trim();
}

/**
 * Group flat submission rows by (client_id, assessment_id), then by (user_id, timestamp)
 * per submit session. Returns groups sorted by their most recent attempt (newest first).
 */
function groupSubmissions(rows) {
  const byClientAssessment = new Map();
  for (const r of rows) {
    const key = JSON.stringify([r.client_id ?? "", r.assessment_id ?? ""]);
    if (!byClientAssessment.has(key)) {
      byClientAssessment.set(key, []);
    }
    byClientAssessment.get(key).push(r);
  }

  const groups = [];
  for (const [caKey, list] of byClientAssessment) {
    const [client_id, assessment_id] = JSON.parse(caKey);
    const byAttempt = new Map();
    for (const r of list) {
      const ak = JSON.stringify([r.user_id ?? "", r.timestamp ?? ""]);
      if (!byAttempt.has(ak)) {
        byAttempt.set(ak, []);
      }
      byAttempt.get(ak).push(r);
    }

    const attempts = [];
    for (const [ak, qrows] of byAttempt) {
      const [user_id, timestamp] = JSON.parse(ak);
      const scores = qrows.map((x) => parseScore(x.score)).filter((n) => n != null);
      const avg =
        scores.length > 0
          ? Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 100) / 100
          : null;
      const sortedRows = [...qrows].sort((a, b) =>
        String(a.question_id).localeCompare(String(b.question_id), undefined, { numeric: true })
      );
      attempts.push({
        user_id: user_id || "—",
        timestamp: timestamp || "—",
        avgScore: avg,
        questionCount: qrows.length,
        rows: sortedRows,
      });
    }
    attempts.sort((a, b) => String(b.timestamp).localeCompare(String(a.timestamp)));
    const latestTimestamp = attempts[0]?.timestamp ?? "";
    groups.push({
      client_id: client_id || "—",
      assessment_id: assessment_id || "—",
      latestTimestamp,
      attempts,
    });
  }

  // Sort groups by the most recent attempt within each group (newest first by default)
  groups.sort(
    (a, b) =>
      String(b.latestTimestamp).localeCompare(String(a.latestTimestamp)) ||
      a.assessment_id.localeCompare(b.assessment_id)
  );
  return groups;
}

export default function AdminSubmissionsPage() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [employeeFilter, setEmployeeFilter] = useState("");
  const [assessmentFilter, setAssessmentFilter] = useState("");
  const [dateSort, setDateSort] = useState("desc"); // "desc" | "asc"

  const filteredRows = useMemo(() => {
    const empQ = employeeFilter.trim().toLowerCase();
    const assQ = assessmentFilter.trim().toLowerCase();
    return rows.filter((r) => {
      if (empQ && !extractEmployeeId(r.user_id).toLowerCase().includes(empQ)) return false;
      if (assQ && !(r.assessment_id ?? "").toLowerCase().includes(assQ)) return false;
      return true;
    });
  }, [rows, employeeFilter, assessmentFilter]);

  const groups = useMemo(() => {
    const gs = groupSubmissions(filteredRows);
    if (dateSort === "asc") {
      gs.sort(
        (a, b) =>
          String(a.latestTimestamp).localeCompare(String(b.latestTimestamp)) ||
          a.assessment_id.localeCompare(b.assessment_id)
      );
    }
    return gs;
  }, [filteredRows, dateSort]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setError(null);
      try {
        const data = await apiFetch("/admin/submissions", { authRole: "admin" });
        if (!cancelled) setRows(data.submissions ?? []);
      } catch (e) {
        if (!cancelled) setError(e.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="page page--wide">
      <header className="header">
        <p className="page-eyebrow">Admin · Data</p>
        <h1>Submissions</h1>
        <p className="muted">
          Results are grouped by <strong>client</strong> and <strong>assessment</strong>. Each expandable
          row is one submit session (user + time) with average score; open it for per-question detail.
        </p>
      </header>

      <section className="card">
        {loading && <p className="muted">Loading…</p>}
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {!loading && !error && rows.length === 0 && (
          <div className="empty-state">No submissions yet.</div>
        )}
        {!loading && !error && rows.length > 0 && (
          <>
            <div className="submissions-toolbar">
              <label className="submissions-toolbar-field">
                <span className="submissions-toolbar-label">Employee ID</span>
                <input
                  type="search"
                  placeholder="Filter by employee ID…"
                  value={employeeFilter}
                  onChange={(e) => setEmployeeFilter(e.target.value)}
                  className="submissions-toolbar-input"
                />
              </label>
              <label className="submissions-toolbar-field">
                <span className="submissions-toolbar-label">Assessment ID</span>
                <input
                  type="search"
                  placeholder="Filter by assessment ID…"
                  value={assessmentFilter}
                  onChange={(e) => setAssessmentFilter(e.target.value)}
                  className="submissions-toolbar-input"
                />
              </label>
              <label className="submissions-toolbar-field">
                <span className="submissions-toolbar-label">Sort by date</span>
                <select
                  value={dateSort}
                  onChange={(e) => setDateSort(e.target.value)}
                  className="submissions-toolbar-select"
                >
                  <option value="desc">Newest first</option>
                  <option value="asc">Oldest first</option>
                </select>
              </label>
              {(employeeFilter || assessmentFilter) && (
                <span className="submissions-toolbar-count muted small-print">
                  {groups.reduce((n, g) => n + g.attempts.length, 0)} session
                  {groups.reduce((n, g) => n + g.attempts.length, 0) !== 1 ? "s" : ""} matching
                </span>
              )}
            </div>

            {groups.length === 0 ? (
              <div className="empty-state">No submissions match the current filters.</div>
            ) : (
          <div className="submission-groups">
            {groups.map((g) => (
              <article
                className="submission-group"
                key={`${g.client_id}-${g.assessment_id}`}
              >
                <header className="submission-group-header">
                  <div className="submission-group-field">
                    <span className="submission-group-label">Client</span>
                    <span className="submission-group-value">{g.client_id}</span>
                  </div>
                  <div className="submission-group-field submission-group-field--grow">
                    <span className="submission-group-label">Assessment ID</span>
                    <code className="cell-id submission-group-code">{g.assessment_id}</code>
                  </div>
                  <div className="submission-group-field">
                    <span className="submission-group-label">Latest submission</span>
                    <span className="submission-group-value submission-group-date">
                      {formatDate(g.latestTimestamp)}
                    </span>
                  </div>
                  <div className="submission-group-badge">
                    {g.attempts.length} session{g.attempts.length !== 1 ? "s" : ""}
                  </div>
                </header>

                <div className="submission-attempts">
                  {g.attempts.map((att, idx) => (
                    <details
                      key={`${g.assessment_id}-${att.user_id}-${att.timestamp}-${idx}`}
                      className="submission-attempt"
                    >
                      <summary className="submission-attempt-summary">
                        <span className="attempt-pill">User</span>
                        <span className="attempt-user">{att.user_id}</span>
                        <span className="attempt-pill">Date</span>
                        <span className="attempt-time">{formatDate(att.timestamp)}</span>
                        <span className="attempt-result">
                          Avg score <strong>{att.avgScore ?? "—"}</strong>
                          <span className="attempt-result-muted">/ 100</span>
                        </span>
                        <span className="attempt-qcount">{att.questionCount} questions</span>
                      </summary>
                      <div className="table-wrap table-wrap--nested">
                        <table className="data-table data-table--nested">
                          <thead>
                            <tr>
                              <th>Q</th>
                              <th>Score</th>
                              <th>Answer</th>
                              <th>Feedback</th>
                            </tr>
                          </thead>
                          <tbody>
                            {att.rows.map((r, i) => (
                              <tr key={`${r.question_id}-${i}`}>
                                <td>{r.question_id}</td>
                                <td>{r.score}</td>
                                <td className="cell-clamp" title={r.user_answer}>
                                  {r.user_answer}
                                </td>
                                <td className="cell-clamp" title={r.feedback}>
                                  {r.feedback}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  ))}
              </div>
            </article>
            ))}
          </div>
            )}
          </>
        )}
      </section>

      <p className="muted footer-hint">
        <Link to="/admin">Generate</Link>
        {" · "}
        <Link to="/admin/assessments">Assessments</Link>
        {" · "}
        <Link to="/admin/catalog">Catalog</Link>
      </p>
    </div>
  );
}
