import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { fetchEmployeeReport } from "../lib/employeeReportApi.js";

function formatDate(iso) {
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

function formatDuration(totalSeconds) {
  const s = Math.max(0, Number(totalSeconds) || 0);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m`;
  return `${s}s`;
}

function topicChipClass(percent) {
  if (percent >= 75) return "emp-report-chip emp-report-chip--good";
  if (percent >= 50) return "emp-report-chip emp-report-chip--mid";
  return "emp-report-chip emp-report-chip--low";
}

function trendGlyph(trend) {
  if (trend === "up") return "↑";
  if (trend === "down") return "↓";
  if (trend === "flat") return "→";
  return "";
}

const UNEXPLORED_TOPIC_MAX_LEN = 30;

function truncateTopicName(name, maxLen = UNEXPLORED_TOPIC_MAX_LEN) {
  const s = String(name || "");
  if (s.length <= maxLen) return s;
  return `${s.slice(0, maxLen - 1)}…`;
}

function groupTopicsByTier(topics) {
  const groups = new Map();
  for (const name of topics || []) {
    const m = /^Tier\s*(\d+)/i.exec(name);
    const label = m ? `Tier ${m[1]}` : "Other";
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(name);
  }
  return [...groups.entries()].sort((a, b) => {
    const tierNum = (label) => {
      const m = /^Tier\s*(\d+)/i.exec(label);
      return m ? Number.parseInt(m[1], 10) : 999;
    };
    return tierNum(a[0]) - tierNum(b[0]);
  });
}

function ScoreRing({ percent, label }) {
  const r = 42;
  const c = 2 * Math.PI * r;
  const clamped = Math.min(100, Math.max(0, percent));
  const offset = c - (clamped / 100) * c;
  return (
    <div className="emp-report-ring" aria-label={`${label}: ${Math.round(clamped)} percent`}>
      <svg viewBox="0 0 100 100" width="120" height="120" role="img">
        <circle cx="50" cy="50" r={r} fill="none" stroke="rgba(0,0,0,0.08)" strokeWidth="9" />
        <circle
          cx="50"
          cy="50"
          r={r}
          fill="none"
          stroke="var(--emp-report-accent, #2563eb)"
          strokeWidth="9"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          transform="rotate(-90 50 50)"
        />
        <text x="50" y="48" textAnchor="middle" className="emp-report-ring-value">
          {Math.round(clamped)}%
        </text>
        <text x="50" y="62" textAnchor="middle" className="emp-report-ring-label">
          {label}
        </text>
      </svg>
    </div>
  );
}

function LineChart({ points }) {
  if (!points?.length) {
    return <p className="muted small-print">No score history yet.</p>;
  }
  if (points.length === 1) {
    const p = points[0];
    return (
      <div className="emp-report-line-chart-single">
        <p className="muted small-print">
          One assessment so far — complete more to see a trend line.
        </p>
        <p>
          <strong>{Math.round(p.percent)}%</strong>
          <span className="muted"> · {p.assessment_id}</span>
        </p>
      </div>
    );
  }
  const width = 360;
  const height = 140;
  const pad = 24;
  const xs = points.map((_, i) => i);
  const ys = points.map((p) => p.percent);
  const minY = Math.min(...ys, 0);
  const maxY = Math.max(...ys, 100);
  const spanY = maxY - minY || 1;
  const coords = points.map((p, i) => {
    const x = pad + (i / Math.max(points.length - 1, 1)) * (width - pad * 2);
    const y = height - pad - ((p.percent - minY) / spanY) * (height - pad * 2);
    return { x, y, ...p };
  });
  const poly = coords.map((c) => `${c.x},${c.y}`).join(" ");
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="emp-report-line-chart" role="img">
      <polyline
        fill="none"
        stroke="var(--emp-report-accent, #2563eb)"
        strokeWidth="2.5"
        points={poly}
      />
      {coords.map((c) => (
        <circle key={c.assessment_id} cx={c.x} cy={c.y} r="4" fill="#2563eb">
          <title>{`${c.assessment_id}: ${c.percent}%`}</title>
        </circle>
      ))}
    </svg>
  );
}

function TypeDonut({ breakdown }) {
  const entries = Object.entries(breakdown || {});
  if (!entries.length) {
    return <p className="muted small-print">No question-type data.</p>;
  }
  const total = entries.reduce((n, [, v]) => n + (v.count || 0), 0) || 1;
  const colors = { mcq: "#2563eb", coding: "#7c3aed", subjective: "#059669" };
  let angle = 0;
  const slices = entries.map(([type, data]) => {
    const frac = (data.count || 0) / total;
    const start = angle;
    angle += frac * 360;
    return { type, data, start, end: angle, color: colors[type] || "#64748b" };
  });
  const r = 40;
  const cx = 50;
  const cy = 50;
  function arc(startDeg, endDeg) {
    const s = (startDeg - 90) * (Math.PI / 180);
    const e = (endDeg - 90) * (Math.PI / 180);
    const x1 = cx + r * Math.cos(s);
    const y1 = cy + r * Math.sin(s);
    const x2 = cx + r * Math.cos(e);
    const y2 = cy + r * Math.sin(e);
    const large = endDeg - startDeg > 180 ? 1 : 0;
    return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`;
  }
  return (
    <div className="emp-report-donut-wrap">
      <svg viewBox="0 0 100 100" width="140" height="140" role="img">
        {slices.map((sl) => (
          <path key={sl.type} d={arc(sl.start, sl.end)} fill={sl.color} opacity="0.9">
            <title>{`${sl.type}: ${sl.data.count} questions`}</title>
          </path>
        ))}
        <circle cx={cx} cy={cy} r="22" fill="var(--card-bg, #fff)" />
        <text x={cx} y={cy + 4} textAnchor="middle" fontSize="11" fontWeight="600">
          {total}
        </text>
      </svg>
      <ul className="emp-report-donut-legend">
        {slices.map((sl) => (
          <li key={sl.type}>
            <span className="emp-report-legend-swatch" style={{ background: sl.color }} />
            {sl.type.toUpperCase()} — {sl.data.count} ({Math.round(sl.data.percent_correct)}%)
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function EmployeeReportPage({ mode = "client" }) {
  const { employeeId: routeEmployeeId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialEmployee =
    routeEmployeeId?.trim() ||
    searchParams.get("employee_id")?.trim() ||
    "";
  const initialPeriod = searchParams.get("period") || "all_time";

  const [employeeIdInput, setEmployeeIdInput] = useState(initialEmployee);
  const [period, setPeriod] = useState(initialPeriod);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (routeEmployeeId?.trim()) {
      setEmployeeIdInput(routeEmployeeId.trim());
    }
  }, [routeEmployeeId]);

  const authRole = mode === "admin" ? "admin" : undefined;

  const loadReport = useCallback(async () => {
    const eid = employeeIdInput.trim();
    if (!eid) {
      setError("Employee ID is required.");
      setReport(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchEmployeeReport({
        employeeId: eid,
        period,
        authRole,
      });
      setReport(data);
      if (mode === "client") {
        setSearchParams({ employee_id: eid, period }, { replace: true });
      }
    } catch (e) {
      setReport(null);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [employeeIdInput, period, authRole, mode, setSearchParams]);

  useEffect(() => {
    if (initialEmployee) {
      loadReport();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hasData = (report?.summary?.assessments_completed ?? 0) > 0;

  const languageColors = useMemo(() => {
    const palette = ["#2563eb", "#7c3aed", "#059669", "#d97706", "#dc2626"];
    const map = {};
    (report?.languages || []).forEach((lang, i) => {
      map[lang.language_code] = palette[i % palette.length];
    });
    return map;
  }, [report?.languages]);

  function handlePrint() {
    window.print();
  }

  return (
    <div className={`page emp-report-page emp-report-page--${mode}`}>
      <header className="emp-report-header no-print">
        <div>
          <p className="page-eyebrow">Stage 4 — Skills analytics</p>
          <h1>{report?.title || "Skills Progress Report"}</h1>
          {mode === "admin" ? (
            <p className="muted">
              <Link to="/admin/submissions">← Submissions</Link>
            </p>
          ) : (
            <p className="muted">
              <Link to="/client">← Take test</Link>
              {employeeIdInput.trim() && (
                <>
                  {" · "}
                  <Link
                    to={`/client/improve?employee_id=${encodeURIComponent(employeeIdInput.trim())}`}
                  >
                    Help me improve →
                  </Link>
                </>
              )}
            </p>
          )}
        </div>
        <div className="emp-report-controls">
          <label>
            Employee ID
            <input
              value={employeeIdInput}
              onChange={(e) => setEmployeeIdInput(e.target.value)}
              placeholder="e.g. E1001"
            />
          </label>
          <label>
            Period
            <select value={period} onChange={(e) => setPeriod(e.target.value)}>
              <option value="all_time">All time</option>
              <option value="last_90_days">Last 90 days</option>
            </select>
          </label>
          <button type="button" className="primary" onClick={loadReport} disabled={loading}>
            {loading ? "Loading…" : "Load report"}
          </button>
          {hasData && (
            <button type="button" className="secondary" onClick={handlePrint}>
              Download PDF / Print
            </button>
          )}
        </div>
      </header>

      {error && (
        <div className="error no-print" role="alert">
          {error}
        </div>
      )}

      {report && !hasData && (
        <div className="card emp-report-empty">
          <h2>No submissions yet</h2>
          <p className="muted">
            Complete your first assessment to see progress, topic breakdowns, and charts here.
          </p>
        </div>
      )}

      {report && hasData && (
        <article className="emp-report-document">
          <section className="emp-report-hero card">
            <div className="emp-report-hero-main">
              <h2 className="emp-report-hero-title">
                {report.display_name || report.employee_id}
              </h2>
              <p className="muted emp-report-meta">
                <span>ID: {report.employee_id}</span>
                <span>Generated {formatDate(report.report_generated_at)}</span>
                <span>Period: {period === "last_90_days" ? "Last 90 days" : "All time"}</span>
              </p>
              <div className="emp-report-hero-stats">
                <div>
                  <strong>{report.summary.assessments_completed}</strong>
                  <span className="muted">Assessments</span>
                </div>
                <div>
                  <strong>{report.summary.questions_answered}</strong>
                  <span className="muted">Questions</span>
                </div>
                <div>
                  <strong>{formatDuration(report.summary.total_time_seconds)}</strong>
                  <span className="muted">Time on platform</span>
                </div>
                <div>
                  <strong>{formatDuration(report.summary.avg_assessment_time_seconds)}</strong>
                  <span className="muted">Avg / assessment</span>
                </div>
              </div>
              <p className="emp-report-proficiency">
                Progress at <strong>{report.summary.assessed_level_label || "Beginner"}</strong>{" "}
                level: <strong>{report.summary.proficiency_label}</strong>
              </p>
            </div>
            <ScoreRing
              percent={report.summary.overall_percent_correct}
              label="Score"
            />
          </section>

          <section className="emp-report-grid card">
            <div>
              <h3>Languages evaluated</h3>
              <div className="emp-report-lang-cards">
                {(report.languages || []).map((lang) => (
                  <div
                    key={lang.language_code}
                    className="emp-report-lang-card"
                    style={{
                      borderLeftColor: languageColors[lang.language_code] || "#2563eb",
                    }}
                  >
                    <strong>{lang.language_label}</strong>
                    <span>
                      {lang.topics_covered}/{lang.topics_in_catalog || "—"} topics
                    </span>
                    <span>{lang.questions_count} questions</span>
                    <span>
                      {Math.round(lang.percent_correct)}% · {lang.assessed_level_label || "Beginner"} ·{" "}
                      {lang.proficiency_label}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <h3>Mastery</h3>
              <p>
                <strong>{report.mastery.mastered_count}</strong> questions mastered
              </p>
              <p>
                <strong>{report.mastery.needs_practice_count}</strong> need more practice
                (wrong 2+ times)
              </p>
            </div>
          </section>

          <section className="emp-report-charts card">
            <div className="emp-report-chart-block">
              <h3>Score trend</h3>
              <LineChart points={report.score_timeline} />
            </div>
            <div className="emp-report-chart-block">
              <h3>Question types</h3>
              <TypeDonut breakdown={report.question_type_breakdown} />
            </div>
          </section>

          {(report.languages || []).map((lang) => (
            <section key={lang.language_code} className="card emp-report-topics">
              <h3>
                {lang.language_label} — topics covered
              </h3>
              <div className="table-wrap">
                <table className="data-table emp-report-topic-table">
                  <thead>
                    <tr>
                      <th>Topic</th>
                      <th>Questions</th>
                      <th>Mastered</th>
                      <th>% correct</th>
                      <th>Level</th>
                      <th>Trend</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(lang.topics || []).map((topic) => (
                      <tr key={topic.topic_name}>
                        <td>
                          <span className={topicChipClass(topic.percent_correct)}>
                            {topic.topic_name}
                          </span>
                        </td>
                        <td>{topic.questions_count}</td>
                        <td>{topic.mastered_count}</td>
                        <td>{Math.round(topic.percent_correct)}%</td>
                        <td>{topic.last_difficulty || "—"}</td>
                        <td aria-label={`Trend ${topic.trend || "none"}`}>
                          {trendGlyph(topic.trend)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}

          <section className="card emp-report-insights">
            <h3>Strengths & focus areas</h3>
            <div className="emp-report-insights-grid">
              <div>
                <h4>Strengths</h4>
                {(report.insights.strengths || []).length ? (
                  <ul>
                    {report.insights.strengths.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted small-print">No standout strengths yet (need ≥80% on 5+ questions).</p>
                )}
              </div>
              <div>
                <h4>Focus areas (last 3 assessments)</h4>
                {(report.insights.focus_areas || []).length ? (
                  <ul>
                    {report.insights.focus_areas.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted small-print">No weak topics below 70% in recent assessments.</p>
                )}
              </div>
            </div>
            <div className="emp-report-unexplored">
              <h4>Unexplored topics (your languages)</h4>
              {(report.insights.unexplored_topics || []).length ? (
                groupTopicsByTier(report.insights.unexplored_topics).map(([tier, names]) => (
                  <div key={tier} className="emp-report-unexplored-tier">
                    <h5 className="emp-report-unexplored-tier-label">{tier}</h5>
                    <ul className="emp-report-unexplored-list">
                      {names.map((t) => (
                        <li key={t}>
                          <span className="emp-report-unexplored-chip" title={t}>
                            {truncateTopicName(t)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))
              ) : (
                <p className="muted small-print">
                  All catalog topics covered for languages you have been assessed in.
                </p>
              )}
            </div>
            {(report.insights.recommendations || []).length > 0 && (
              <div className="emp-report-recommendations">
                <h4>Recommendations</h4>
                <ul>
                  {report.insights.recommendations.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>

          <footer className="emp-report-footer muted small-print">
            <p>
              Scores reflect platform assessments only. Help me improve practice flows
              (Stage 5+) will use this profile data.
            </p>
            <p>Report version {report.report_version}</p>
          </footer>
        </article>
      )}
    </div>
  );
}
