import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  isBankQuestion,
  partitionReviewQuestions,
} from "../lib/assessmentConfirm.js";
import {
  createReviewDraft,
  deleteReviewQuestion,
  loadReviewBundle,
  markQuestionDirty,
  metadataFromConfirmPayload,
  patchAssessmentAlias,
  publishReview,
  regenerateReviewQuestion,
  saveReviewQuestion,
} from "../lib/assessmentReviewApi.js";
import { applyTabIndent } from "../lib/tabIndent.js";
import { mentionsExternalFile } from "../lib/scoreDisplay.js";

function typeLabel(type) {
  return { mcq: "MCQ", coding: "Coding", subjective: "Subjective" }[type] ?? type;
}

function OptionRow({ option, index, isCorrect, disabled, onTextChange, onMarkCorrect }) {
  const letter = String.fromCharCode(65 + index);
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

function TestCasesEditor({ cases, disabled, onChange }) {
  const rows = cases ?? [];

  function updateRow(index, field, value) {
    const next = rows.map((row, i) =>
      i === index ? { ...row, [field]: value } : row
    );
    onChange(next);
  }

  function addRow() {
    onChange([...rows, { input: "", expected_output: "", label: "" }]);
  }

  function removeRow(index) {
    onChange(rows.filter((_, i) => i !== index));
  }

  return (
    <div className="review-test-cases">
      <span className="review-field-label">Sample test cases (function/class coding)</span>
      <p className="muted small-print review-test-cases-hint">
        Representative input → expected output only. Participants are reminded to consider
        additional edge cases beyond these examples.
      </p>
      {rows.length === 0 && (
        <p className="muted small-print">No test cases — add rows or leave empty.</p>
      )}
      {rows.map((row, i) => (
        <div key={i} className="review-test-case-row">
          <label className="review-field">
            <span className="review-field-label">Input</span>
            <textarea
              className="review-field-textarea review-field-textarea--code"
              value={row.input ?? ""}
              onChange={(e) => updateRow(i, "input", e.target.value)}
              onKeyDown={(e) =>
                applyTabIndent(e, row.input ?? "", (next) => updateRow(i, "input", next))
              }
              rows={2}
              spellCheck={false}
              disabled={disabled}
            />
          </label>
          <label className="review-field">
            <span className="review-field-label">Expected output</span>
            <textarea
              className="review-field-textarea review-field-textarea--code"
              value={row.expected_output ?? ""}
              onChange={(e) => updateRow(i, "expected_output", e.target.value)}
              onKeyDown={(e) =>
                applyTabIndent(e, row.expected_output ?? "", (next) =>
                  updateRow(i, "expected_output", next)
                )
              }
              rows={2}
              spellCheck={false}
              disabled={disabled}
            />
          </label>
          <label className="review-field">
            <span className="review-field-label">Label (optional)</span>
            <input
              type="text"
              className="review-field-input"
              value={row.label ?? ""}
              onChange={(e) => updateRow(i, "label", e.target.value)}
              disabled={disabled}
            />
          </label>
          {!disabled && (
            <button type="button" className="secondary review-test-case-remove" onClick={() => removeRow(i)}>
              Remove
            </button>
          )}
        </div>
      ))}
      {!disabled && (
        <button type="button" className="secondary" onClick={addRow}>
          Add test case
        </button>
      )}
    </div>
  );
}

function RegenerateModal({ question, metadata, onClose, onApply }) {
  const [preference, setPreference] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const item = await regenerateReviewQuestion({
        level: metadata.level,
        language_code: metadata.language_code,
        topic_name: question.topic_name || "",
        question_type: question.type,
        reference_question: question,
        admin_preference: preference.trim() || null,
        include_sample_test_cases: metadata.include_sample_test_cases,
        include_beginner_coding_hints: metadata.include_beginner_coding_hints,
        generation_provider: metadata.generation_provider || "grok",
      });
      onApply(item);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="review-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="review-modal card"
        role="dialog"
        aria-labelledby="regen-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="regen-title">Regenerate question</h2>
        <p className="muted small-print">
          The LLM will produce a replacement {typeLabel(question.type)} question for topic{" "}
          <strong>{question.topic_name || "general"}</strong>. Your edits are not saved until you
          click &ldquo;This question is good, save it&rdquo;.
        </p>
        <form onSubmit={(e) => void handleSubmit(e)}>
          <label className="review-field">
            <span className="review-field-label">Admin preference (optional)</span>
            <textarea
              className="review-field-textarea"
              value={preference}
              onChange={(e) => setPreference(e.target.value)}
              rows={3}
              placeholder="e.g. focus on list comprehensions, avoid recursion"
              disabled={loading}
            />
          </label>
          {error && (
            <div className="error" role="alert">
              {error}
            </div>
          )}
          <div className="review-modal-actions">
            <button type="button" className="button" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button type="submit" className="button primary" disabled={loading}>
              {loading ? "Generating…" : "Regenerate"}
            </button>
          </div>
        </form>
      </div>
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
  onSave,
  onDelete,
  onRegenerate,
  saving = false,
}) {
  const isMcq = question.type === "mcq";
  const isCoding = question.type === "coding";
  const locked = readOnly;
  const isSaved = Boolean(question.saved_at) && !question.is_dirty;
  const externalFileWarning =
    isCoding && mentionsExternalFile(question.question);

  function updateField(field, value) {
    if (locked) return;
    onChange(markQuestionDirty({ ...question, [field]: value }));
  }

  function updateOption(optIndex, value) {
    if (locked) return;
    const next = [...(question.options ?? [])];
    next[optIndex] = value;
    const updated = markQuestionDirty({ ...question, options: next });
    if ((question.options ?? [])[optIndex] === question.correct_answer) {
      updated.correct_answer = value;
    }
    onChange(updated);
  }

  function markCorrect(optIndex) {
    if (locked) return;
    const correctText = (question.options ?? [])[optIndex] ?? "";
    onChange(markQuestionDirty({ ...question, correct_answer: correctText }));
  }

  return (
    <article className={`review-card${locked ? " review-card--readonly" : ""}`}>
      <header className="review-card-header">
        <span className={`review-card-type review-card-type--${question.type}`}>
          {typeLabel(question.type)}
        </span>
        {showSourceBadge &&
          (fromBank ? (
            <span className="review-card-source-badge review-card-source-badge--bank">Bank</span>
          ) : (
            <span className="review-card-source-badge review-card-source-badge--new">New</span>
          ))}
        {isSaved && (
          <span className="review-card-saved-badge" title={`Saved at ${question.saved_at}`}>
            Saved
          </span>
        )}
        {question.is_dirty && question.saved_at && (
          <span className="review-card-dirty-badge">Unsaved edits</span>
        )}
        {question.topic_name && (
          <span className="review-card-topic">{question.topic_name}</span>
        )}
        <span className="review-card-counter muted small-print">
          {index + 1} / {total}
        </span>
        {!locked && (
          <div className="review-card-toolbar">
            <button
              type="button"
              className="review-icon-btn"
              title="Regenerate this question"
              aria-label="Regenerate question"
              onClick={() => onRegenerate(question)}
              disabled={saving}
            >
              ♻️
            </button>
            <button
              type="button"
              className="review-icon-btn review-icon-btn--danger"
              title="Remove question"
              aria-label="Delete question"
              onClick={() => onDelete(question)}
              disabled={saving}
            >
              🗑️
            </button>
          </div>
        )}
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

        {externalFileWarning && (
          <p className="review-external-file-warn" role="alert">
            This coding question mentions external files. Pyodide cannot read files from disk —
            rewrite so the exercise is self-contained in the terminal.
          </p>
        )}

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

        {isCoding && (
          <TestCasesEditor
            cases={question.sample_test_cases}
            disabled={locked}
            onChange={(next) => updateField("sample_test_cases", next)}
          />
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
                onTextChange={(val) => updateOption(i, val)}
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

        {isCoding && (
          <label className="review-field">
            <span className="review-field-label">
              Hint
              <span className="review-field-hint muted small-print">
                {" "}— optional nudge for beginners; must not reveal the full solution
              </span>
            </span>
            <textarea
              className="review-field-textarea"
              value={question.coding_hint ?? ""}
              onChange={(e) => updateField("coding_hint", e.target.value)}
              rows={2}
              placeholder="e.g. consider using a loop to visit each element"
              readOnly={locked}
              disabled={locked}
            />
          </label>
        )}

        {!locked && (
          <div className="review-card-save-row">
            <button
              type="button"
              className="button primary"
              onClick={() => onSave(question)}
              disabled={saving}
            >
              {saving ? "Saving…" : "This question is good, save it"}
            </button>
          </div>
        )}
      </div>
    </article>
  );
}

function ReviewHeader({ isReReview, isRecycleMode, bankCount, llmCount }) {
  if (isReReview) {
    return (
      <>
        <h1>Re-review assessment</h1>
        <p className="muted">
          Edit questions below and save each one individually. When finished, click{" "}
          <strong>Publish assessment</strong> so participants see your changes.
        </p>
      </>
    );
  }

  if (isRecycleMode && bankCount > 0 && llmCount > 0) {
    return (
      <>
        <h1>
          Review {llmCount} new question{llmCount === 1 ? "" : "s"} ({bankCount} recycled)
        </h1>
        <p className="muted">
          Save each question when it looks good. Bank-sourced and new questions can both be edited.
          Publish when every question is saved.
        </p>
      </>
    );
  }

  return (
    <>
      <h1>Review generated questions</h1>
      <p className="muted">
        Check every question. Save each one with <strong>This question is good, save it</strong>, then{" "}
        <strong>Publish assessment</strong> when all are saved.
      </p>
    </>
  );
}

export default function AdminReviewPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const initialQuestions = location.state?.questions ?? [];
  const confirmPayload = location.state?.confirmPayload ?? null;
  const previewMeta = location.state?.previewMeta ?? null;
  const recycledOnly = Boolean(location.state?.recycledOnly);

  const [assessmentId, setAssessmentId] = useState(
    searchParams.get("assessmentId") || location.state?.assessmentId || null
  );
  const [reviewMetadata, setReviewMetadata] = useState(null);
  const [alias, setAlias] = useState("");
  const [questions, setQuestions] = useState(
    initialQuestions.map((q) => ({ ...q, saved_at: q.saved_at ?? null, is_dirty: false }))
  );
  const [initLoading, setInitLoading] = useState(Boolean(searchParams.get("assessmentId")));
  const [initError, setInitError] = useState(null);
  const [showRecycled, setShowRecycled] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [savingQuestionId, setSavingQuestionId] = useState(null);
  const [error, setError] = useState(null);
  const [savedId, setSavedId] = useState(location.state?.savedId ?? null);
  const [savedStats, setSavedStats] = useState(location.state?.savedStats ?? null);
  const [regenTarget, setRegenTarget] = useState(null);

  const isReReview = Boolean(assessmentId && !confirmPayload && !recycledOnly && initialQuestions.length === 0);
  const isRecycleMode =
    (confirmPayload?.question_source || reviewMetadata?.question_source) ===
    "recycle_then_generate";
  const { bankQuestions, llmQuestions } = partitionReviewQuestions(questions);
  const bankCount = previewMeta?.bank_sourced_count ?? bankQuestions.length;
  const llmCount = previewMeta?.llm_generated_count ?? llmQuestions.length;

  const savedCount = useMemo(
    () => questions.filter((q) => q.saved_at && !q.is_dirty).length,
    [questions]
  );

  const reviewMeta = useMemo(() => {
    if (reviewMetadata) return reviewMetadata;
    if (!confirmPayload) return { level: "beginner", generation_provider: "grok" };
    return {
      level: confirmPayload.level,
      language_code: confirmPayload.language_code,
      include_sample_test_cases: confirmPayload.include_sample_test_cases,
      include_beginner_coding_hints: confirmPayload.include_beginner_coding_hints,
      generation_provider: confirmPayload.generation_provider,
    };
  }, [reviewMetadata, confirmPayload]);

  const applyBundle = useCallback((bundle) => {
    setAssessmentId(bundle.assessment_id);
    setAlias(bundle.alias || "");
    setReviewMetadata({
      topic: bundle.topic,
      level: bundle.level,
      language_code: bundle.language_code,
      language_label: bundle.language_label,
      topic_names: bundle.topic_names,
      per_topic_config: bundle.per_topic_config,
      is_timed: bundle.is_timed,
      duration_minutes: bundle.duration_minutes,
      notebook_grace_minutes: bundle.notebook_grace_minutes,
      allow_pyodide_paste: bundle.allow_pyodide_paste,
      certificate_enabled: bundle.certificate_enabled,
      question_source: bundle.question_source,
      include_sample_test_cases: bundle.include_sample_test_cases,
      include_beginner_coding_hints: bundle.include_beginner_coding_hints,
      generation_provider: bundle.generation_provider,
    });
    setQuestions(
      (bundle.questions ?? []).map((q) => ({
        ...q,
        saved_at: q.saved_at ?? null,
        is_dirty: false,
      }))
    );
  }, []);

  useEffect(() => {
    if (savedId) return undefined;

    const urlId = searchParams.get("assessmentId");
    if (urlId && !assessmentId) {
      setAssessmentId(urlId);
    }

    // Fresh generate flow: questions live in navigation state until individually
    // saved. After createReviewDraft adds ?assessmentId= to the URL, do not reload
    // from the API — the draft row exists but has no questions yet.
    const isFreshGenerateDraft =
      Boolean(confirmPayload) && initialQuestions.length > 0;

    if (urlId && !isFreshGenerateDraft) {
      let cancelled = false;
      setInitLoading(true);
      setInitError(null);
      loadReviewBundle(urlId)
        .then((bundle) => {
          if (!cancelled) applyBundle(bundle);
        })
        .catch((e) => {
          if (!cancelled) setInitError(e.message);
        })
        .finally(() => {
          if (!cancelled) setInitLoading(false);
        });
      return () => {
        cancelled = true;
      };
    }

    if (confirmPayload && initialQuestions.length > 0 && !assessmentId) {
      let cancelled = false;
      setInitLoading(true);
      setInitError(null);
      const meta = metadataFromConfirmPayload(confirmPayload, confirmPayload.alias);
      createReviewDraft(meta)
        .then((draft) => {
          if (cancelled) return;
          setAssessmentId(draft.assessment_id);
          setSearchParams({ assessmentId: draft.assessment_id }, { replace: true });
          setReviewMetadata(meta);
          if (confirmPayload.alias) setAlias(confirmPayload.alias);
        })
        .catch((e) => {
          if (!cancelled) setInitError(e.message);
        })
        .finally(() => {
          if (!cancelled) setInitLoading(false);
        });
      return () => {
        cancelled = true;
      };
    }

    return undefined;
  }, [
    applyBundle,
    assessmentId,
    confirmPayload,
    initialQuestions.length,
    savedId,
    searchParams,
    setSearchParams,
  ]);

  function replaceQuestion(oldId, updated) {
    setQuestions((prev) =>
      prev.map((q) => (String(q.question_id) === String(oldId) ? updated : q))
    );
  }

  function updateQuestion(questionId, updated) {
    replaceQuestion(questionId, updated);
  }

  async function handleSaveQuestion(question) {
    if (!assessmentId) return;
    setError(null);
    setSavingQuestionId(question.question_id);
    try {
      const result = await saveReviewQuestion(assessmentId, question.question_id, question);
      const next = {
        ...question,
        question_id: result.question_id,
        bank_question_id: result.bank_question_id ?? question.bank_question_id,
        saved_at: result.saved_at,
        is_dirty: false,
      };
      if (String(result.question_id) !== String(question.question_id)) {
        setQuestions((prev) =>
          prev
            .filter((q) => String(q.question_id) !== String(question.question_id))
            .concat(next)
        );
      } else {
        replaceQuestion(question.question_id, next);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setSavingQuestionId(null);
    }
  }

  async function handleDeleteQuestion(question) {
    if (!window.confirm(`Remove question ${question.question_id} from this assessment?`)) {
      return;
    }
    setError(null);
    if (question.saved_at && assessmentId) {
      try {
        await deleteReviewQuestion(assessmentId, question.question_id);
      } catch (e) {
        setError(e.message);
        return;
      }
    }
    setQuestions((prev) =>
      prev.filter((q) => String(q.question_id) !== String(question.question_id))
    );
  }

  function handleRegenerateApply(item) {
    replaceQuestion(item.question_id, {
      ...item,
      saved_at: null,
      is_dirty: true,
    });
  }

  async function handleAliasBlur() {
    if (!assessmentId) return;
    const trimmed = alias.trim();
    try {
      await patchAssessmentAlias(assessmentId, trimmed || null);
    } catch (e) {
      setError(e.message);
    }
  }

  async function handlePublish() {
    if (!assessmentId) return;
    setError(null);
    setPublishing(true);
    try {
      const meta = reviewMetadata || metadataFromConfirmPayload(confirmPayload, alias.trim() || null);
      const result = await publishReview(assessmentId, questions, meta);
      setSavedId(result.assessment_id);
      setSavedStats({ question_count: result.question_count });
    } catch (e) {
      setError(e.message);
    } finally {
      setPublishing(false);
    }
  }

  const hasDraft =
    Boolean(assessmentId) ||
    Boolean(confirmPayload) ||
    Boolean(savedId) ||
    Boolean(searchParams.get("assessmentId"));

  if (!hasDraft) {
    return (
      <div className="page">
        <header className="header">
          <h1>No draft to review</h1>
          <p className="muted">Generate an assessment or open Re-review from the assessments list.</p>
        </header>
        <Link to="/admin" className="button">
          Back to Generate
        </Link>
      </div>
    );
  }

  if (initLoading) {
    return (
      <div className="page">
        <header className="header">
          <h1>Loading review…</h1>
          <p className="muted">Fetching assessment draft.</p>
        </header>
      </div>
    );
  }

  if (initError) {
    return (
      <div className="page">
        <header className="header">
          <h1>Could not load review</h1>
          <div className="error" role="alert">
            {initError}
          </div>
        </header>
        <Link to="/admin/assessments" className="button">
          Back to Assessments
        </Link>
      </div>
    );
  }

  if (savedId) {
    return (
      <div className="page">
        <header className="header">
          <p className="page-eyebrow">Administrator</p>
          <h1>Assessment published</h1>
          <p className="muted">
            {recycledOnly
              ? "All questions were recycled from the question bank and saved without manual review."
              : "The assessment is published and visible to participants."}
          </p>
        </header>
        <section className="card">
          <p>
            <strong>Assessment ID:</strong>{" "}
            <code className="cell-id">{savedId}</code>
          </p>
          {savedStats?.question_count != null && (
            <p className="muted">
              <strong>{savedStats.question_count}</strong> question
              {savedStats.question_count === 1 ? "" : "s"} published
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

  const allSaved = questions.length > 0 && savedCount === questions.length;

  return (
    <div className="page page--wide">
      <header className="header">
        <p className="page-eyebrow">Administrator · Review</p>
        <ReviewHeader
          isReReview={isReReview}
          isRecycleMode={isRecycleMode}
          bankCount={bankCount}
          llmCount={llmCount}
        />
        {assessmentId && (
          <p className="muted small-print" style={{ marginTop: "0.5rem" }}>
            Assessment ID: <code className="cell-id">{assessmentId}</code>
            {" · "}
            Progress: <strong>{savedCount}</strong> / {questions.length} saved
          </p>
        )}
        <label className="review-alias-field">
          <span className="review-field-label">Alias (optional)</span>
          <input
            type="text"
            className="review-field-input"
            value={alias}
            onChange={(e) => setAlias(e.target.value)}
            onBlur={() => void handleAliasBlur()}
            placeholder="e.g. Python beginner exam for Maria June 25th"
            maxLength={120}
          />
        </label>
        {previewMeta?.generation_provider && (
          <p className="muted" style={{ marginTop: "0.5rem" }}>
            Generated with{" "}
            <strong>
              {previewMeta.generation_provider === "gemini" ? "Gemini" : "Groq"}
            </strong>
          </p>
        )}
      </header>

      {isRecycleMode && bankCount > 0 && (
        <section className="review-recycled-summary card">
          <p>
            <strong>{bankCount}</strong> question{bankCount === 1 ? "" : "s"} from the question bank
            · <strong>{llmCount}</strong> newly generated. All appear in the list below for editing
            and saving.
          </p>
        </section>
      )}

      <div className="review-questions">
        {questions.length === 0 ? (
          <p className="muted">No questions in this assessment.</p>
        ) : (
          questions.map((q, i) => (
            <QuestionCard
              key={q.question_id}
              question={q}
              index={i}
              total={questions.length}
              fromBank={isBankQuestion(q)}
              showSourceBadge={isRecycleMode}
              saving={savingQuestionId === q.question_id}
              onSave={handleSaveQuestion}
              onDelete={handleDeleteQuestion}
              onRegenerate={setRegenTarget}
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
            onClick={() => navigate(isReReview ? "/admin/assessments" : "/admin")}
            className="button"
            disabled={publishing}
          >
            {isReReview ? "← Back to assessments" : "← Regenerate"}
          </button>
          <button
            type="button"
            className="button primary"
            onClick={() => void handlePublish()}
            disabled={publishing || questions.length === 0}
            title={allSaved ? undefined : "You can publish anytime; unsaved edits will be persisted on publish"}
          >
            {publishing
              ? "Publishing…"
              : `Publish assessment (${questions.length} question${questions.length === 1 ? "" : "s"})`}
          </button>
        </div>
        {!allSaved && questions.length > 0 && (
          <p className="muted small-print review-actions-hint">
            {savedCount} of {questions.length} questions individually saved. Publish will save any
            remaining edits.
          </p>
        )}
      </div>

      {regenTarget && (
        <RegenerateModal
          question={regenTarget}
          metadata={reviewMeta}
          onClose={() => setRegenTarget(null)}
          onApply={handleRegenerateApply}
        />
      )}

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
