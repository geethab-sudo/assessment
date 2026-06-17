import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { apiFetch } from "../api";
import {
  buildConfirmBody,
  isBankQuestion,
  partitionReviewQuestions,
} from "../lib/assessmentConfirm.js";
import { applyTabIndent } from "../lib/tabIndent.js";

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

function QuestionCard({
  question,
  index,
  total,
  onChange,
  readOnly = false,
  fromBank = false,
  showSourceBadge = false,
}) {
  const isMcq = question.type === "mcq";
  const isCoding = question.type === "coding";
  const locked = readOnly || fromBank;

  function updateField(field, value) {
    if (locked) return;
    onChange({ ...question, [field]: value });
  }

  function updateOption(optIndex, value) {
    if (locked) return;
    const next = [...(question.options ?? [])];
    next[optIndex] = value;
    onChange({ ...question, options: next });
  }

  function markCorrect(optIndex) {
    if (locked) return;
    const correctText = (question.options ?? [])[optIndex] ?? "";
    onChange({ ...question, correct_answer: correctText });
  }

  return (
    <article className={`review-card${locked ? " review-card--readonly" : ""}`}>
      <header className="review-card-header">
        <span className={`review-card-type review-card-type--${question.type}`}>
          {typeLabel(question.type)}
        </span>
        {showSourceBadge &&
          (fromBank ? (
            <span className="review-card-source-badge review-card-source-badge--bank">
              Bank
            </span>
          ) : (
            <span className="review-card-source-badge review-card-source-badge--new">
              New
            </span>
          ))}
        {question.topic_name && (
          <span className="review-card-topic">{question.topic_name}</span>
        )}
        <span className="review-card-counter muted small-print">
          {index + 1} / {total}
        </span>
      </header>

      <div className="review-card-body">
        <label className="review-field">
          <span className="review-field-label">Question</span>
          <textarea
            className="review-field-textarea"
            value={question.question}
            onChange={(e) => updateField("question", e.target.value)}
            rows={3}
            readOnly={locked}
            disabled={locked}
          />
        </label>

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
              onKeyDown={
                locked
                  ? undefined
                  : (e) =>
                      applyTabIndent(e, question.code_snippet ?? "", (next) =>
                        updateField("code_snippet", next)
                      )
              }
              rows={5}
              spellCheck={false}
              readOnly={locked}
              disabled={locked}
            />
          </label>
        )}

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
                disabled={locked}
                onTextChange={(val) => {
                  const wasCorrect = opt === question.correct_answer;
                  updateOption(i, val);
                  if (wasCorrect) updateField("correct_answer", val);
                }}
                onMarkCorrect={() => markCorrect(i)}
              />
            ))}
            {(question.options ?? []).length === 0 && (
              <label className="review-field">
                <span className="review-field-label">Correct answer</span>
                <input
                  type="text"
                  className="review-field-input"
                  value={question.correct_answer ?? ""}
                  onChange={(e) => updateField("correct_answer", e.target.value)}
                  readOnly={locked}
                  disabled={locked}
                />
              </label>
            )}
          </div>
        )}

        {!isMcq && (
          <label className="review-field">
            <span className="review-field-label">Reference answer</span>
            <textarea
              className="review-field-textarea"
              value={question.correct_answer ?? ""}
              onChange={(e) => updateField("correct_answer", e.target.value)}
              rows={4}
              readOnly={locked}
              disabled={locked}
            />
          </label>
        )}
      </div>
    </article>
  );
}

function ReviewHeader({ isRecycleMode, bankCount, llmCount }) {
  if (isRecycleMode && bankCount > 0 && llmCount > 0) {
    return (
      <>
        <h1>
          Review {llmCount} new question{llmCount === 1 ? "" : "s"} ({bankCount} recycled)
        </h1>
        <p className="muted">
          Recycled questions from the bank are pre-approved and included automatically.
          Review and edit only the <strong>{llmCount}</strong> newly generated question
          {llmCount === 1 ? "" : "s"} below, then save the full assessment.
        </p>
      </>
    );
  }

  if (isRecycleMode && bankCount > 0 && llmCount === 0) {
    return (
      <>
        <h1>Recycled assessment</h1>
        <p className="muted">
          All questions were pulled from the question bank and saved without manual review.
        </p>
      </>
    );
  }

  return (
    <>
      <h1>Review generated questions</h1>
      <p className="muted">
        Check every question below. For MCQ questions, select the radio button next to the
        correct option. Edit any text, code snippet, or option as needed, then click{" "}
        <strong>Confirm &amp; save</strong> to publish the assessment.
      </p>
    </>
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
  const recycledOnly = Boolean(location.state?.recycledOnly);

  const [questions, setQuestions] = useState(initialQuestions);
  const [showRecycled, setShowRecycled] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [savedId, setSavedId] = useState(location.state?.savedId ?? null);
  const [savedStats, setSavedStats] = useState(location.state?.savedStats ?? null);

  const isRecycleMode = confirmPayload?.question_source === "recycle_then_generate";
  const { bankQuestions, llmQuestions } = partitionReviewQuestions(questions);
  const bankCount = previewMeta?.bank_sourced_count ?? bankQuestions.length;
  const llmCount = previewMeta?.llm_generated_count ?? llmQuestions.length;
  const questionsToReview = isRecycleMode ? llmQuestions : questions;

  if (!confirmPayload && !savedId) {
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

  function updateQuestion(questionId, updated) {
    setQuestions((prev) =>
      prev.map((q) => (q.question_id === questionId ? updated : q))
    );
  }

  async function handleConfirm() {
    if (!confirmPayload) return;
    setError(null);
    setSaving(true);
    try {
      const data = await apiFetch("/admin/confirm-assessment", {
        method: "POST",
        authRole: "admin",
        body: JSON.stringify(buildConfirmBody(confirmPayload, questions)),
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
          <p className="muted">
            {recycledOnly
              ? "All questions were recycled from the question bank and saved without manual review."
              : "The reviewed questions have been saved to the database."}
          </p>
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
        <ReviewHeader
          isRecycleMode={isRecycleMode}
          bankCount={bankCount}
          llmCount={llmCount}
        />
        {previewMeta &&
          isRecycleMode &&
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

      {isRecycleMode && bankCount > 0 && (
        <section className="review-recycled-summary card">
          <p>
            <strong>{bankCount}</strong> question{bankCount === 1 ? "" : "s"} recycled from the
            question bank (pre-approved — included automatically).
          </p>
          <button
            type="button"
            className="button button--compact"
            onClick={() => setShowRecycled((v) => !v)}
          >
            {showRecycled ? "Hide recycled questions" : "View recycled questions"}
          </button>
          {showRecycled && (
            <div className="review-recycled-list">
              {bankQuestions.map((q, i) => (
                <QuestionCard
                  key={q.question_id}
                  question={q}
                  index={i}
                  total={bankQuestions.length}
                  readOnly
                  fromBank
                  showSourceBadge
                  onChange={() => {}}
                />
              ))}
            </div>
          )}
        </section>
      )}

      <div className="review-questions">
        {questionsToReview.length === 0 ? (
          <p className="muted">No new questions require review.</p>
        ) : (
          questionsToReview.map((q, i) => (
            <QuestionCard
              key={q.question_id}
              question={q}
              index={i}
              total={questionsToReview.length}
              fromBank={isBankQuestion(q)}
              showSourceBadge={isRecycleMode}
              onChange={(updated) => updateQuestion(q.question_id, updated)}
            />
          ))
        )}
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
            {saving
              ? "Saving…"
              : `Confirm & save (${questions.length} question${questions.length === 1 ? "" : "s"})`}
          </button>
        </div>
        <p className="muted small-print review-actions-hint">
          Clicking <em>Regenerate</em> discards this draft and returns to the form without saving
          anything.
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
