import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import Pagination from "../components/Pagination.jsx";
import QuestionStem from "../components/QuestionStem.jsx";
import { usePagination } from "../hooks/usePagination.js";

function formatAddedAt(isoText) {
  if (!isoText) return "—";
  const d = new Date(isoText);
  if (!Number.isFinite(d.getTime())) return "—";
  return d.toLocaleString([], {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function LanguageCellSummary({ summary }) {
  const display =
    summary.language_name || summary.language_label || summary.language_code;
  const code = summary.language_code;
  if (!display) return <span className="muted">—</span>;
  let title;
  if (code && display !== code) title = `Code: ${code}`;
  return <span title={title}>{display}</span>;
}

function AssessmentQuestionPreview({ assessmentId, questionCount }) {
  const [phase, setPhase] = useState("idle"); // idle | loading | done | error
  const [payload, setPayload] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    if (phase === "loading" || phase === "done") return;
    setPhase("loading");
    setErr(null);
    try {
      const data = await apiFetch(`/admin/assessment/${encodeURIComponent(assessmentId)}`, {
        authRole: "admin",
      });
      setPayload(data);
      setPhase("done");
    } catch (e) {
      setErr(e.message);
      setPhase("error");
    }
  }, [assessmentId, phase]);

  return (
    <details
      className="admin-assessment-preview"
      onToggle={(e) => {
        if (e.currentTarget.open) void load();
      }}
    >
      <summary className="admin-assessment-preview-summary">
        Question preview
        <span className="muted admin-assessment-preview-meta">
          ({questionCount} {questionCount === 1 ? "question" : "questions"} — same view as participants)
        </span>
      </summary>
      <div className="admin-assessment-preview-body">
        {phase === "loading" && <p className="muted">Loading…</p>}
        {err && (
          <div className="error" role="alert">
            {err}
          </div>
        )}
        {phase === "done" && payload?.questions?.length > 0 && (
          <ol className="admin-q-list">
            {payload.questions.map((q) => (
              <li key={String(q.question_id)}>
                <div className="admin-q-head">
                  <span className="pill">{q.type}</span>
                  <span className="muted">Q{q.question_id}</span>
                </div>
                <QuestionStem
                  question={q.question}
                  code={q.code}
                  languageCode={payload?.language_code}
                  className="admin-q-stem-wrap"
                />
                {q.type === "mcq" && Array.isArray(q.options) && q.options.length > 0 && (
                  <ul className="admin-q-options muted">
                    {q.options.map((opt, idx) => (
                      <li key={`${q.question_id}-${idx}`}>
                        <span className="admin-q-opt-letter" aria-hidden="true">
                          {String.fromCharCode(65 + idx)}.
                        </span>{" "}
                        {opt}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ol>
        )}
        {phase === "done" && (!payload?.questions || payload.questions.length === 0) && (
          <p className="muted">No questions in file for this ID.</p>
        )}
      </div>
    </details>
  );
}

export default function AdminAssessmentsPage() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  // Filters & sort
  const [idFilter, setIdFilter] = useState("");
  const [langFilter, setLangFilter] = useState("");
  const [dateSort, setDateSort] = useState("desc"); // "asc" | "desc"

  /** All unique language labels available in the loaded data. */
  const languageOptions = useMemo(() => {
    const seen = new Set();
    const opts = [];
    for (const r of rows) {
      const label = r.language_name || r.language_label || r.language_code || "";
      if (label && !seen.has(label)) {
        seen.add(label);
        opts.push(label);
      }
    }
    return opts.sort((a, b) => a.localeCompare(b));
  }, [rows]);

  const visibleRows = useMemo(() => {
    let filtered = rows;
    if (idFilter.trim()) {
      const q = idFilter.trim().toLowerCase();
      filtered = filtered.filter((r) => r.assessment_id.toLowerCase().includes(q));
    }
    if (langFilter) {
      filtered = filtered.filter((r) => {
        const label = r.language_name || r.language_label || r.language_code || "";
        return label === langFilter;
      });
    }
    return [...filtered].sort((a, b) => {
      const ta = a.created_at || "";
      const tb = b.created_at || "";
      return dateSort === "desc" ? tb.localeCompare(ta) : ta.localeCompare(tb);
    });
  }, [rows, idFilter, langFilter, dateSort]);

  const filterResetKey = `${idFilter}|${langFilter}|${dateSort}`;
  const {
    page,
    setPage,
    pageSize,
    totalItems,
    totalPages,
    paginatedItems,
  } = usePagination(visibleRows, { resetKey: filterResetKey });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setError(null);
      try {
        const data = await apiFetch("/admin/assessments", { authRole: "admin" });
        if (!cancelled) setRows(data.assessments ?? []);
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

  const handleDelete = async (r) => {
    const id = r.assessment_id;
    if (
      !window.confirm(
        `Delete assessment ${id}?\n\nAll questions and submission history for this assessment will be removed. This cannot be undone.`
      )
    ) {
      return;
    }
    setActionError(null);
    setDeletingId(id);
    try {
      await apiFetch(`/admin/assessments/${encodeURIComponent(id)}`, {
        method: "DELETE",
        authRole: "admin",
      });
      setRows((prev) => prev.filter((x) => x.assessment_id !== id));
    } catch (e) {
      setActionError(e.message);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="page page--wide">
      <header className="header">
        <p className="page-eyebrow">Admin · Data</p>
        <h1>Assessments</h1>
        <p className="muted">
          Per-client and shared (<code>common</code>) assessments on the server. Expand a row to see the
          question list (preview only — no answers).
        </p>
      </header>

      <section className="card">
        {loading && <p className="muted">Loading…</p>}
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {actionError && (
          <div className="error" role="alert">
            {actionError}
          </div>
        )}
        {!loading && !error && (
          <>
          <div className="submissions-toolbar">
            <label className="submissions-toolbar-field">
              <span className="submissions-toolbar-label">Assessment ID</span>
              <input
                className="submissions-toolbar-input"
                type="search"
                placeholder="Search by ID…"
                value={idFilter}
                onChange={(e) => setIdFilter(e.target.value)}
              />
            </label>
            <label className="submissions-toolbar-field">
              <span className="submissions-toolbar-label">Language</span>
              <select
                className="submissions-toolbar-select"
                value={langFilter}
                onChange={(e) => setLangFilter(e.target.value)}
              >
                <option value="">All languages</option>
                {languageOptions.map((l) => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
            </label>
            <label className="submissions-toolbar-field">
              <span className="submissions-toolbar-label">Sort by date</span>
              <select
                className="submissions-toolbar-select"
                value={dateSort}
                onChange={(e) => setDateSort(e.target.value)}
              >
                <option value="desc">Newest first</option>
                <option value="asc">Oldest first</option>
              </select>
            </label>
            <span className="submissions-toolbar-count muted">
              {visibleRows.length} / {rows.length}
            </span>
          </div>
          <Pagination
            page={page}
            totalPages={totalPages}
            totalItems={totalItems}
            pageSize={pageSize}
            onPageChange={setPage}
            itemLabel="assessments"
          />
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Assessment ID</th>
                  <th>Scope</th>
                  <th>Added</th>
                  <th>Language</th>
                  <th>Topics</th>
                  <th>Question count</th>
                  <th>Source</th>
                  <th className="cell-nowrap">Actions</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.length === 0 ? (
                  <tr>
                    <td colSpan={8}>
                      <div className="empty-state">
                        {rows.length === 0 ? "No assessments yet." : "No assessments match the filters."}
                      </div>
                    </td>
                  </tr>
                ) : (
                  paginatedItems.map((r) => (
                    <Fragment key={r.assessment_id}>
                      <tr>
                        <td>
                          <code className="cell-id">{r.assessment_id}</code>
                        </td>
                        <td>{r.client_id}</td>
                        <td className="cell-nowrap">{formatAddedAt(r.created_at)}</td>
                        <td className="cell-nowrap">
                          <LanguageCellSummary summary={r} />
                        </td>
                        <td>
                          {Array.isArray(r.topic_names) && r.topic_names.length > 0 ? (
                            <ul className="admin-assessment-topic-list muted">
                              {r.topic_names.map((name, i) => (
                                <li key={`${r.assessment_id}-topic-${i}`}>{name}</li>
                              ))}
                            </ul>
                          ) : (
                            <span className="muted">—</span>
                          )}
                        </td>
                        <td>
                          {r.question_count}
                          {r.is_timed ? (
                            <div className="muted small-print" style={{ marginTop: "4px" }}>
                              <span className="pill" style={{ fontSize: "0.72rem" }}>
                                Timed {r.duration_minutes}m
                                {r.notebook_grace_minutes
                                  ? ` (+${r.notebook_grace_minutes}m notebook)`
                                  : ""}
                              </span>
                            </div>
                          ) : null}
                        </td>
                        <td>{r.source}</td>
                        <td className="cell-actions">
                          <div className="cell-actions-btns">
                            <button
                              type="button"
                              className="btn-table-danger"
                              onClick={() => void handleDelete(r)}
                              disabled={deletingId === r.assessment_id}
                            >
                              {deletingId === r.assessment_id ? "…" : "Delete"}
                            </button>
                          </div>
                        </td>
                      </tr>
                      <tr className="admin-assessment-detail">
                        <td colSpan={8}>
                          <AssessmentQuestionPreview
                            assessmentId={r.assessment_id}
                            questionCount={r.question_count}
                          />
                        </td>
                      </tr>
                    </Fragment>
                  ))
                )}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            totalPages={totalPages}
            totalItems={totalItems}
            pageSize={pageSize}
            onPageChange={setPage}
            itemLabel="assessments"
          />
          </>
        )}
      </section>

      <p className="muted footer-hint">
        <Link to="/admin">Generate</Link>
        {" · "}
        <Link to="/admin/catalog">Catalog</Link>
        {" · "}
        <Link to="/admin/submissions">Submissions</Link>
      </p>
    </div>
  );
}
