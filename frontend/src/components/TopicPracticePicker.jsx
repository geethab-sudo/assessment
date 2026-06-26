import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  DEFAULT_QUICK_PRACTICE_QUESTIONS,
  MAX_QUESTIONS,
  MAX_TOPICS,
} from "../lib/improvementConstants.js";

/**
 * Full-page or embedded topic + question-count picker for bank-only practice.
 */
export default function TopicPracticePicker({
  title,
  subtitle,
  topics = [],
  maxTopics = MAX_TOPICS,
  defaultQuestions = DEFAULT_QUICK_PRACTICE_QUESTIONS,
  initialSelected = [],
  employeeId,
  languageLabel,
  backTo,
  backLabel = "← Back to report",
  onStart,
  starting = false,
  error = null,
  layout = "page",
}) {
  const [selected, setSelected] = useState(() => new Set());
  const [questionCount, setQuestionCount] = useState(defaultQuestions);

  useEffect(() => {
    setSelected(new Set(initialSelected));
    setQuestionCount(defaultQuestions);
  }, [initialSelected, defaultQuestions, title, topics]);

  const selectedCount = selected.size;
  const atTopicCap = selectedCount >= maxTopics;

  const sortedTopics = useMemo(() => {
    return [...topics].sort((a, b) => (a.name || "").localeCompare(b.name || ""));
  }, [topics]);

  const toggle = (name) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else if (next.size < maxTopics) next.add(name);
      return next;
    });
  };

  const clearAll = () => setSelected(new Set());

  const handleStart = () => onStart([...selected], questionCount);

  const rootClass =
    layout === "page" ? "topic-practice-page" : "topic-practice-panel";

  return (
    <div className={rootClass}>
      {layout === "page" && (
        <header className="topic-practice-page-header">
          <div>
            {backTo && (
              <Link to={backTo} className="topic-practice-back link-button">
                {backLabel}
              </Link>
            )}
            <p className="page-eyebrow">Guided practice</p>
            <h1>{title}</h1>
            {subtitle && <p className="muted topic-practice-subtitle">{subtitle}</p>}
            {(employeeId || languageLabel) && (
              <p className="muted small-print topic-practice-meta">
                {employeeId && <span>Employee {employeeId}</span>}
                {employeeId && languageLabel && " · "}
                {languageLabel && <span>{languageLabel}</span>}
              </p>
            )}
          </div>
        </header>
      )}

      <section className="card topic-practice-card">
        {layout !== "page" && <h2 className="topic-practice-card-title">{title}</h2>}

        <div className="topic-practice-intro">
          <p>
            Choose up to <strong>{maxTopics}</strong> topics and how many questions you want
            (max <strong>{MAX_QUESTIONS}</strong> per session).
          </p>
          <div className="topic-practice-toolbar">
            <span className="topic-practice-selection-count" aria-live="polite">
              {selectedCount} of {maxTopics} topics selected
            </span>
            <div className="topic-practice-toolbar-actions">
              <button
                type="button"
                className="link-button"
                onClick={clearAll}
                disabled={selectedCount === 0}
              >
                Clear
              </button>
            </div>
          </div>
        </div>

        {sortedTopics.length === 0 ? (
          <p className="muted">No topics available for this selection.</p>
        ) : (
          <ul className="topic-practice-grid" role="list">
            {sortedTopics.map((topic) => {
              const name = topic.name;
              const checked = selected.has(name);
              const disabled = !checked && atTopicCap;
              return (
                <li key={name}>
                  <label
                    className={`topic-practice-tile${checked ? " topic-practice-tile--selected" : ""}${
                      disabled ? " topic-practice-tile--disabled" : ""
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="topic-practice-tile-check"
                      checked={checked}
                      disabled={disabled}
                      onChange={() => toggle(name)}
                    />
                    <span className="topic-practice-tile-body">
                      <span className="topic-practice-tile-name">{name}</span>
                      {topic.hint && (
                        <span className="topic-practice-tile-hint">{topic.hint}</span>
                      )}
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}

        <div className="topic-practice-footer">
          <label className="topic-practice-count">
            <span className="topic-practice-count-label">Number of questions</span>
            <input
              type="number"
              min={1}
              max={MAX_QUESTIONS}
              value={questionCount}
              onChange={(e) =>
                setQuestionCount(
                  Math.min(MAX_QUESTIONS, Math.max(1, Number(e.target.value) || 1))
                )
              }
            />
          </label>

          {error && (
            <p className="error topic-practice-error" role="alert">
              {error}
            </p>
          )}

          <div className="topic-practice-actions">
            {backTo && layout === "page" && (
              <Link to={backTo} className="secondary topic-practice-cancel">
                Cancel
              </Link>
            )}
            <button
              type="button"
              className="primary topic-practice-start"
              onClick={handleStart}
              disabled={starting || selectedCount === 0}
            >
              {starting ? "Creating practice…" : "Start practice"}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
