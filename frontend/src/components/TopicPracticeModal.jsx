import { useEffect, useState } from "react";
import { MAX_QUESTIONS, MAX_TOPICS } from "../lib/improvementConstants.js";

/**
 * Modal for picking topics and question count before starting bank-only practice.
 */
export default function TopicPracticeModal({
  open,
  title,
  topics,
  maxTopics = MAX_TOPICS,
  defaultQuestions = 10,
  initialSelected = [],
  onClose,
  onStart,
  starting = false,
  error = null,
}) {
  const [selected, setSelected] = useState(() => new Set());
  const [questionCount, setQuestionCount] = useState(defaultQuestions);

  useEffect(() => {
    if (open) {
      setSelected(new Set(initialSelected));
      setQuestionCount(defaultQuestions);
    }
  }, [open, defaultQuestions, initialSelected, title]);

  if (!open) return null;

  const toggle = (name) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else if (next.size < maxTopics) {
        next.add(name);
      }
      return next;
    });
  };

  const handleStart = () => {
    onStart([...selected], questionCount);
  };

  return (
    <div className="topic-practice-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="card topic-practice-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="topic-practice-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="topic-practice-modal-title">{title}</h2>
        <p className="muted small-print">
          Select up to {maxTopics} topics. Max {MAX_QUESTIONS} questions per session.
        </p>
        <ul className="topic-practice-modal-list">
          {topics.map((topic) => {
            const name = topic.name;
            const checked = selected.has(name);
            const disabled = !checked && selected.size >= maxTopics;
            return (
              <li key={name}>
                <label className={`topic-practice-option${disabled ? " topic-practice-option--disabled" : ""}`}>
                  <input
                    type="checkbox"
                    checked={checked}
                    disabled={disabled}
                    onChange={() => toggle(name)}
                  />
                  <span className="topic-practice-option-body">
                    <span className="topic-practice-option-name">{name}</span>
                    {topic.hint && (
                      <span className="muted small-print topic-practice-option-hint">{topic.hint}</span>
                    )}
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
        <label className="topic-practice-count">
          Number of questions
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
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <div className="topic-practice-modal-actions">
          <button type="button" onClick={onClose} disabled={starting}>
            Cancel
          </button>
          <button
            type="button"
            className="primary"
            onClick={handleStart}
            disabled={starting || selected.size === 0}
          >
            {starting ? "Creating…" : "Start practice"}
          </button>
        </div>
      </div>
    </div>
  );
}
