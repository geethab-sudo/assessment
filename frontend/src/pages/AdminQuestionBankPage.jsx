import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import Pagination from "../components/Pagination.jsx";
import { usePagination } from "../hooks/usePagination.js";
import { fetchQuestionBank } from "../lib/questionBankApi.js";

const DIFFICULTIES = [
  { value: "", label: "All levels" },
  { value: "beginner", label: "Beginner" },
  { value: "intermediate", label: "Intermediate" },
  { value: "advanced", label: "Advanced" },
];

const QUESTION_TYPES = [
  { value: "", label: "All types" },
  { value: "mcq", label: "MCQ" },
  { value: "coding", label: "Coding" },
  { value: "subjective", label: "Subjective" },
];

const SORT_OPTIONS = [
  { value: "percent_wrong", label: "% wrong (highest first)" },
  { value: "percent_correct", label: "% correct (highest first)" },
  { value: "times_used", label: "Times used (highest first)" },
];

function typeLabel(type) {
  return { mcq: "MCQ", coding: "Coding", subjective: "Subjective" }[type] ?? type;
}

function truncate(text, max = 140) {
  const t = (text || "").trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max)}…`;
}

function formatPercent(value, attempts) {
  if (!attempts) return "—";
  return `${Number(value).toFixed(1)}%`;
}

export default function AdminQuestionBankPage() {
  const [languages, setLanguages] = useState([]);
  const [questions, setQuestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortBy, setSortBy] = useState("percent_wrong");

  const [languageCode, setLanguageCode] = useState("");
  const [topicName, setTopicName] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [questionType, setQuestionType] = useState("");

  const loadLanguages = useCallback(async () => {
    try {
      const data = await apiFetch("/admin/languages", { authRole: "admin" });
      setLanguages(data.languages ?? []);
    } catch {
      setLanguages([]);
    }
  }, []);

  const loadBank = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchQuestionBank({
        language_code: languageCode || undefined,
        topic_name: topicName || undefined,
        difficulty: difficulty || undefined,
        question_type: questionType || undefined,
      });
      setQuestions(data.questions ?? []);
    } catch (e) {
      setQuestions([]);
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [languageCode, topicName, difficulty, questionType]);

  useEffect(() => {
    void loadLanguages();
  }, [loadLanguages]);

  useEffect(() => {
    void loadBank();
  }, [loadBank]);

  const sortedQuestions = useMemo(() => {
    const list = [...questions];
    list.sort((a, b) => {
      if (sortBy === "times_used") {
        return (b.times_used ?? 0) - (a.times_used ?? 0) || (b.id ?? 0) - (a.id ?? 0);
      }
      if (sortBy === "percent_correct") {
        const correctDiff = (b.percent_correct ?? 0) - (a.percent_correct ?? 0);
        if (correctDiff !== 0) return correctDiff;
        return (b.times_used ?? 0) - (a.times_used ?? 0) || (b.id ?? 0) - (a.id ?? 0);
      }
      const wrongDiff = (b.percent_wrong ?? 0) - (a.percent_wrong ?? 0);
      if (wrongDiff !== 0) return wrongDiff;
      return (b.times_used ?? 0) - (a.times_used ?? 0) || (b.id ?? 0) - (a.id ?? 0);
    });
    return list;
  }, [questions, sortBy]);

  const filterKey = JSON.stringify({
    languageCode,
    topicName,
    difficulty,
    questionType,
    sortBy,
  });

  const {
    page,
    setPage,
    pageSize,
    totalItems,
    totalPages,
    paginatedItems,
  } = usePagination(sortedQuestions, { resetKey: filterKey, pageSize: 20 });

  return (
    <div className="page page--wide">
      <header className="header">
        <p className="page-eyebrow">Administrator</p>
        <h1>Question bank</h1>
        <p className="muted">
          Browse reusable questions with usage and correctness stats. Sort by failure rate to find
          tricky items. Topic filter matches the full catalog topic name exactly.
        </p>
        <p className="muted" style={{ marginTop: "0.65rem" }}>
          <Link to="/admin">Generate</Link>
          {" · "}
          <Link to="/admin/assessments">Assessments</Link>
          {" · "}
          <Link to="/admin/catalog">Catalog</Link>
          {" · "}
          <Link to="/admin/submissions">Submissions</Link>
        </p>
      </header>

      <section className="card">
        <div className="submissions-toolbar">
          <label className="submissions-toolbar-field">
            <span className="submissions-toolbar-label">Language</span>
            <select
              className="submissions-toolbar-select"
              value={languageCode}
              onChange={(e) => setLanguageCode(e.target.value)}
            >
              <option value="">All languages</option>
              {languages.map((lang) => (
                <option key={lang.id} value={lang.code}>
                  {lang.name} ({lang.code})
                </option>
              ))}
            </select>
          </label>
          <label className="submissions-toolbar-field">
            <span className="submissions-toolbar-label">Difficulty</span>
            <select
              className="submissions-toolbar-select"
              value={difficulty}
              onChange={(e) => setDifficulty(e.target.value)}
            >
              {DIFFICULTIES.map((d) => (
                <option key={d.value || "all"} value={d.value}>
                  {d.label}
                </option>
              ))}
            </select>
          </label>
          <label className="submissions-toolbar-field">
            <span className="submissions-toolbar-label">Type</span>
            <select
              className="submissions-toolbar-select"
              value={questionType}
              onChange={(e) => setQuestionType(e.target.value)}
            >
              {QUESTION_TYPES.map((t) => (
                <option key={t.value || "all"} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label className="submissions-toolbar-field submissions-toolbar-field--grow">
            <span className="submissions-toolbar-label">Topic (exact name)</span>
            <input
              type="text"
              className="submissions-toolbar-input"
              value={topicName}
              onChange={(e) => setTopicName(e.target.value)}
              placeholder="e.g. Tier 1 - Data Structures…"
            />
          </label>
          <label className="submissions-toolbar-field">
            <span className="submissions-toolbar-label">Sort by</span>
            <select
              className="submissions-toolbar-select"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
            >
              {SORT_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <span className="submissions-toolbar-count muted small-print">
            {loading ? "Loading…" : `${totalItems} question${totalItems === 1 ? "" : "s"}`}
          </span>
        </div>

        {error && (
          <div className="error" role="alert" style={{ marginTop: "1rem" }}>
            {error}
          </div>
        )}

        {!loading && !error && totalItems === 0 && (
          <div className="empty-state" style={{ marginTop: "1.25rem" }}>
            No questions match these filters. Generate and confirm assessments to populate the bank,
            or clear filters.
          </div>
        )}

        {totalItems > 0 && (
          <>
            <Pagination
              page={page}
              totalPages={totalPages}
              totalItems={totalItems}
              pageSize={pageSize}
              onPageChange={setPage}
              itemLabel="questions"
            />
            <div className="table-wrap" style={{ marginTop: "1rem" }}>
              <table className="data-table question-bank-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Topic</th>
                    <th>Level</th>
                    <th>Type</th>
                    <th>Lang</th>
                    <th>Used</th>
                    <th>% correct</th>
                    <th>% wrong</th>
                    <th>Question</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedItems.map((row) => {
                    const attempts = (row.times_correct ?? 0) + (row.times_wrong ?? 0);
                    const highWrong = attempts > 0 && (row.percent_wrong ?? 0) >= 50;
                    return (
                      <tr
                        key={row.id}
                        className={highWrong ? "question-bank-row--tricky" : undefined}
                      >
                        <td className="cell-id">{row.id}</td>
                        <td className="cell-clamp question-bank-topic" title={row.topic_name}>
                          {row.topic_name || "—"}
                        </td>
                        <td>{row.difficulty || "—"}</td>
                        <td>
                          <span className={`pill pill--${row.type}`}>{typeLabel(row.type)}</span>
                        </td>
                        <td>{row.language_code || "—"}</td>
                        <td>{row.times_used ?? 0}</td>
                        <td>{formatPercent(row.percent_correct, attempts)}</td>
                        <td className={highWrong ? "question-bank-pct-wrong" : undefined}>
                          {formatPercent(row.percent_wrong, attempts)}
                        </td>
                        <td className="cell-clamp question-bank-preview" title={row.question_text}>
                          {truncate(row.question_text)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination
              page={page}
              totalPages={totalPages}
              totalItems={totalItems}
              pageSize={pageSize}
              onPageChange={setPage}
              itemLabel="questions"
            />
          </>
        )}
      </section>
    </div>
  );
}
