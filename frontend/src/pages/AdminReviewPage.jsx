import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Returns a human-readable label for a question type badge. */
function typeLabel(type) {
  return { mcq: "MCQ", coding: "Coding", subjective: "Subjective" }[type] ?? type;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function OptionRow({ option, index, isCorrect, disabled, onTextChange, onMarkCorrect }) {
  const letter = String.fromCharCode(65 + index); // A, B, C, D
  return (
    <div className={`review-option${isCorrect ? " review-option--correct" : ""}`}>
      <label className="review-option-radio" title="Mark as correct answer">
        <input
          type="radio"
          checked={isCorrect}
          onChange={onMarkCorrect}
          disabled={disabled}
          aria-label={`Mark option ${letter} as correct`}
        />
        <span className="review-option-letter">{letter}</span>
      </label>
      <textarea
        className="review-option-text"
        value={option}
        onChange={(e) => onTextChange(e.target.value)}
        disabled={disabled}
        rows={2}
        aria-label={`Option ${letter} text`}
      />
      {isCorrect && <span className="review-option-badge">Correct</span>}
    </div>
  );
}

/** Insert 4 spaces at the cursor position instead of moving focus away. */
function handleTabKey(e) {
  if (e.key !== "Tab") return;
  e.preventDefault();
  const el = e.currentTarget;
  const start = el.selectionStart;
  const end = el.selectionEnd;
  const indent = "    "; // 4 spaces
  el.value = el.value.slice(0, start) + indent + el.value.slice(end);
  // Move caret after the inserted spaces; use nativeInputValueSetter if available
  el.selectionStart = el.selectionEnd = start + indent.length;
  // Fire React's onChange so state stays in sync
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

function QuestionCard({ question, index, total, onChange }) {
  const isMcq = question.type === "mcq";
  const isCoding = question.type === "coding";

  function updateField(field, value) {
    onChange({ ...question, [field]: value });
  }

  function updateOption(optIndex, value) {
    const next = [...(question.options ?? [])];
    next[optIndex] = value;
    onChange({ ...question, options: next });
  }

  function markCorrect(optIndex) {
    const correctText = (question.options ?? [])[optIndex] ?? "";
    onChange({ ...question, correct_answer: correctText });
  }

  return (
    <article className="review-card">
      <header className="review-card-header">
        <span className={`review-card-type review-card-type--${question.type}`}>
          {typeLabel(question.type)}
        </span>
        {question.topic_name && (
          <span className="review-card-topic">{question.topic_name}</span>
        )}
        <span className="review-card-counter muted small-print">
          {index + 1} / {total}
        </span>
      </header>

      <div className="review-card-body">
        {/* Question prose */}
        <label className="review-field">
          <span className="review-field-label">Question</span>
          <textarea
            className="review-field-textarea"
            value={question.question}
            onChange={(e) => updateField("question", e.target.value)}
            rows={3}
          />
        </label>

        {/* Code snippet — only for MCQ and subjective; coding questions never have one */}
        {!isCoding && (
          <label className="review-field">
            <span className="review-field-label">
              Code snippet
              <span className="review-field-hint muted small-print">
                {" "}— optional; leave blank if none. Use Tab for 4-space indent.
              </span>
            </span>
            <textarea
              className="review-field-textarea review-field-textarea--code"
              value={question.code_snippet ?? ""}
              onChange={(e) => updateField("code_snippet", e.target.value)}
              onKeyDown={handleTabKey}
              rows={5}
              spellCheck={false}
            />
          </label>
        )}

        {/* MCQ options + correct answer picker */}
        {isMcq && (
          <div className="review-options">
            <span className="review-field-label">
              Options — select the radio button next to the correct answer
            </span>
            {(question.options ?? []).map((opt, i) => (
              <OptionRow
                key={i}
                index={i}
                option={opt}
                isCorrect={opt !== "" && opt === question.correct_answer}
                onTextChange={(val) => {
                  // If this option was the correct one, update correct_answer too
                  const wasCorrect = opt === question.correct_answer;
                  updateOption(i, val);
                  if (wasCorrect) updateField("correct_answer", val);
                }}
                onMarkCorrect={() => markCorrect(i)}
              />
            ))}
            {/* Fallback: show correct_answer as plain text if no options array */}
            {(question.options ?? []).length === 0 && (
              <label className="review-field">
                <span className="review-field-label">Correct answer</span>
                <input
                  type="text"
                  className="review-field-input"
                  value={question.correct_answer ?? ""}
                  onChange={(e) => updateField("correct_answer", e.target.value)}
                />
              </label>
            )}
          </div>
        )}

        {/* Coding / subjective reference answer */}
        {!isMcq && (
          <label className="review-field">
            <span className="review-field-label">Reference answer</span>
            <textarea
              className="review-field-textarea"
              value={question.correct_answer ?? ""}
              onChange={(e) => updateField("correct_answer", e.target.value)}
              rows={4}
            />
          </label>
        )}
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminReviewPage() {
  const location = useLocation();
  const navigate = useNavigate();

  const initialQuestions = location.state?.questions ?? [];
  const confirmPayload = location.state?.confirmPayload ?? null;
  const previewMeta = location.state?.previewMeta ?? null;

  const [questions, setQuestions] = useState(initialQuestions);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [savedId, setSavedId] = useState(null);
  const [savedStats, setSavedStats] = useState(null);

  // Guard: if navigated here directly without state, redirect back
  if (!confirmPayload) {
    return (
      <div className="page">
        <header className="header">
          <h1>No draft to review</h1>
          <p className="muted">Generate an assessment first.</p>
        </header>
        <Link to="/admin" className="button">
          Back to Generate
        </Link>
      </div>
    );
  }

  function updateQuestion(index, updated) {
    setQuestions((prev) => {
      const next = [...prev];
      next[index] = updated;
      return next;
    });
  }

  async function handleConfirm() {
    setError(null);
    setSaving(true);
    try {
      const body = {
        ...confirmPayload,
        questions: questions.map((q) => ({
          question_id: String(q.question_id),
          type: q.type,
          question: q.question,
          code_snippet: q.code_snippet ?? "",
          options: q.options ?? [],
          correct_answer: q.correct_answer ?? "",
          topic_name: q.topic_name ?? "",
          ...(q.bank_question_id != null ? { bank_question_id: q.bank_question_id } : {}),
        })),
      };
      const data = await apiFetch("/admin/confirm-assessment", {
        method: "POST",
        authRole: "admin",
        body: JSON.stringify(body),
      });
      setSavedId(data.assessment_id);
      setSavedStats({
        bank: data.bank_sourced_count ?? 0,
        llm: data.llm_generated_count ?? 0,
        messages: data.shortage_messages ?? [],
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (savedId) {
    return (
      <div className="page">
        <header className="header">
          <p className="page-eyebrow">Administrator</p>
          <h1>Assessment saved</h1>
          <p className="muted">The reviewed questions have been saved to the database.</p>
        </header>
        <section className="card">
          <p>
            <strong>Assessment ID:</strong>{" "}
            <code className="cell-id">{savedId}</code>
          </p>
          {savedStats && (savedStats.bank > 0 || savedStats.llm > 0) && (
            <p className="muted">
              Questions: <strong>{savedStats.bank}</strong> from bank ·{" "}
              <strong>{savedStats.llm}</strong> newly generated
            </p>
          )}
          <div className="review-saved-actions">
            <Link
              to="/client"
              state={{ assessmentId: savedId }}
              className="button primary"
            >
              Open as participant
            </Link>
          </div>
        </section>
        <p className="muted footer-hint">
          <Link to="/admin/assessments">Assessments</Link>
          {" · "}
          <Link to="/admin/submissions">Submissions</Link>
        </p>
      </div>
    );
  }

  return (
    <div className="page page--wide">
      <header className="header">
        <p className="page-eyebrow">Administrator · Review</p>
        <h1>Review generated questions</h1>
        <p className="muted">
          Check every question below. For MCQ questions, select the radio button next to the
          correct option. Edit any text, code snippet, or option as needed, then click{" "}
          <strong>Confirm &amp; save</strong> to publish the assessment.
        </p>
        {previewMeta &&
          (previewMeta.bank_sourced_count > 0 || previewMeta.llm_generated_count > 0) && (
            <p className="muted" style={{ marginTop: "0.5rem" }}>
              Draft mix: <strong>{previewMeta.bank_sourced_count}</strong> from question bank ·{" "}
              <strong>{previewMeta.llm_generated_count}</strong> new via LLM
              {previewMeta.shortage_messages?.length > 0 && (
                <>
                  <br />
                  {previewMeta.shortage_messages.map((msg) => (
                    <span key={msg}>
                      {msg}
                      <br />
                    </span>
                  ))}
                </>
              )}
            </p>
          )}
      </header>

      <div className="review-questions">
        {questions.map((q, i) => (
          <QuestionCard
            key={q.question_id}
            question={q}
            index={i}
            total={questions.length}
            onChange={(updated) => updateQuestion(i, updated)}
          />
        ))}
      </div>

      <div className="review-actions">
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <div className="review-actions-row">
          <button
            type="button"
            onClick={() => navigate("/admin")}
            className="button"
            disabled={saving}
          >
            ← Regenerate
          </button>
          <button
            type="button"
            className="button primary"
            onClick={handleConfirm}
            disabled={saving}
          >
            {saving ? "Saving…" : `Confirm & save (${questions.length} questions)`}
          </button>
        </div>
        <p className="muted small-print review-actions-hint">
          Clicking <em>Regenerate</em> discards this draft and returns to the form without saving anything.
        </p>
      </div>

      <p className="muted footer-hint">
        <Link to="/admin">Generate</Link>
        {" · "}
        <Link to="/admin/assessments">Assessments</Link>
        {" · "}
        <Link to="/admin/submissions">Submissions</Link>
      </p>
    </div>
  );
}
