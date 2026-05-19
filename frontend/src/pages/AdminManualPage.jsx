import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import SearchableLanguageSelect from "../components/SearchableLanguageSelect.jsx";

const emptyMcqDraft = () => ({
  type: "mcq",
  question: "",
  options: ["", ""],
  correct_answer: "",
});

const emptyCodingDraft = () => ({
  type: "coding",
  question: "",
  options: [],
  correct_answer: "",
});

const emptySubjectiveDraft = () => ({
  type: "subjective",
  question: "",
  options: [],
  correct_answer: "",
});

const TYPE_LABELS = {
  mcq: "Multiple choice",
  coding: "Coding",
  subjective: "Subjective",
};

export default function AdminManualPage() {
  const [languages, setLanguages] = useState([]);
  const [languageId, setLanguageId] = useState("");
  const [topics, setTopics] = useState([]);
  const [selectedTopicIds, setSelectedTopicIds] = useState([]);
  const [customTopic, setCustomTopic] = useState("");
  const [loadingLanguages, setLoadingLanguages] = useState(true);
  const [loadingTopics, setLoadingTopics] = useState(false);

  const [draftType, setDraftType] = useState("mcq");
  const [mcqDraft, setMcqDraft] = useState(emptyMcqDraft);
  const [codingDraft, setCodingDraft] = useState(emptyCodingDraft);
  const [subjectiveDraft, setSubjectiveDraft] = useState(emptySubjectiveDraft);
  const [questions, setQuestions] = useState([]);

  const [createdId, setCreatedId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [formError, setFormError] = useState(null);

  const topicById = useMemo(
    () => Object.fromEntries(topics.map((t) => [String(t.id), t])),
    [topics]
  );

  const topicNamesForSave = useMemo(() => {
    const fromCatalog = selectedTopicIds
      .map((id) => topicById[String(id)]?.name?.trim())
      .filter(Boolean);
    if (fromCatalog.length > 0) return fromCatalog;
    const t = customTopic.trim();
    return t ? [t.length > 200 ? `${t.slice(0, 200)}…` : t] : [];
  }, [selectedTopicIds, topicById, customTopic]);

  const languageCodeForSave = useMemo(() => {
    if (!languageId) return null;
    const l = languages.find((x) => String(x.id) === String(languageId));
    return l?.code ? String(l.code).trim() : null;
  }, [languageId, languages]);

  const languageNameForSave = useMemo(() => {
    if (!languageId) return null;
    const l = languages.find((x) => String(x.id) === String(languageId));
    return l?.name ? String(l.name).trim() : null;
  }, [languageId, languages]);

  const hasCodingInList = useMemo(
    () => questions.some((q) => q.type === "coding"),
    [questions]
  );

  const loadLanguages = useCallback(async () => {
    setLoadingLanguages(true);
    try {
      const data = await apiFetch("/admin/languages", { authRole: "admin" });
      setLanguages(data.languages ?? []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoadingLanguages(false);
    }
  }, []);

  const loadTopicsForLanguage = useCallback(async (lid) => {
    if (!lid) {
      setTopics([]);
      setSelectedTopicIds([]);
      return;
    }
    setLoadingTopics(true);
    setSelectedTopicIds([]);
    try {
      const data = await apiFetch(
        `/admin/topics?language_id=${encodeURIComponent(lid)}`,
        { authRole: "admin" }
      );
      setTopics(data.topics ?? []);
    } catch (e) {
      setTopics([]);
      setError(e.message);
    } finally {
      setLoadingTopics(false);
    }
  }, []);

  useEffect(() => {
    void loadLanguages();
  }, [loadLanguages]);

  useEffect(() => {
    if (!languageId) {
      setTopics([]);
      setSelectedTopicIds([]);
      return;
    }
    void loadTopicsForLanguage(languageId);
  }, [languageId, loadTopicsForLanguage]);

  const toggleTopic = (id) => {
    const sid = String(id);
    setSelectedTopicIds((prev) =>
      prev.includes(sid) ? prev.filter((x) => x !== sid) : [...prev, sid]
    );
  };

  const appendQuestion = () => {
    setFormError(null);
    if (draftType === "coding" && !languageCodeForSave) {
      setFormError("Select a catalog language before adding coding questions.");
      return;
    }

    if (draftType === "mcq") {
      const stem = (mcqDraft.question || "").trim();
      if (!stem) {
        setFormError("Enter the question text.");
        return;
      }
      const options = (mcqDraft.options || []).map((o) => String(o).trim()).filter(Boolean);
      if (options.length < 2) {
        setFormError("MCQ needs at least two answer options.");
        return;
      }
      const correct = (mcqDraft.correct_answer || "").trim();
      if (!correct) {
        setFormError("Select the correct MCQ answer.");
        return;
      }
      if (!options.some((o) => o === correct)) {
        setFormError("Correct answer must match one of the options exactly.");
        return;
      }
      setQuestions((prev) => [
        ...prev,
        { type: "mcq", question: stem, options, correct_answer: correct },
      ]);
      setMcqDraft(emptyMcqDraft());
      return;
    }

    if (draftType === "coding") {
      const stem = (codingDraft.question || "").trim();
      if (!stem) {
        setFormError("Enter the coding prompt.");
        return;
      }
      setQuestions((prev) => [
        ...prev,
        {
          type: "coding",
          question: stem,
          options: [],
          correct_answer: (codingDraft.correct_answer || "").trim(),
        },
      ]);
      setCodingDraft(emptyCodingDraft());
      return;
    }

    const stem = (subjectiveDraft.question || "").trim();
    if (!stem) {
      setFormError("Enter the question text.");
      return;
    }
    setQuestions((prev) => [
      ...prev,
      {
        type: "subjective",
        question: stem,
        options: [],
        correct_answer: (subjectiveDraft.correct_answer || "").trim(),
      },
    ]);
    setSubjectiveDraft(emptySubjectiveDraft());
  };

  const removeQuestion = (index) => {
    setQuestions((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSave = async () => {
    setError(null);
    setFormError(null);
    if (topicNamesForSave.length === 0) {
      setFormError("Select at least one catalog topic or enter a custom topic label.");
      return;
    }
    if (questions.length === 0) {
      setFormError("Add at least one question before saving.");
      return;
    }
    if (hasCodingInList && !languageCodeForSave) {
      setFormError("Select a catalog language for coding questions.");
      return;
    }
    setLoading(true);
    try {
      const data = await apiFetch("/admin/assessments/manual", {
        method: "POST",
        authRole: "admin",
        body: JSON.stringify({
          questions,
          topic_names: topicNamesForSave,
          ...(languageCodeForSave ? { language_code: languageCodeForSave } : {}),
          ...(languageNameForSave ? { language_label: languageNameForSave } : {}),
        }),
      });
      setCreatedId(data.assessment_id);
      setQuestions([]);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const mcqOptions = mcqDraft.options || [];
  const selectedLangName = languageNameForSave || "—";

  return (
    <div className="page page--wide manual-layout">
      <header className="header">
        <p className="page-eyebrow">Administrator · Manual</p>
        <h1>Create manual assessment</h1>
        <p className="muted">
          Add MCQ, coding, and subjective questions. Saved assessments appear in{" "}
          <Link to="/admin/assessments">Assessments</Link> as <strong>manual</strong>.
        </p>
        <p className="muted" style={{ marginTop: "0.65rem" }}>
          <Link to="/admin">AI generate</Link>
          {" · "}
          <Link to="/admin/assessments">Browse assessments</Link>
        </p>
      </header>

      <section className="card">
        <h2 className="manual-section-head">Topics &amp; language</h2>
        <div className="manual-form-grid">
          <SearchableLanguageSelect
            label="Language"
            inputId="manual-form-lang"
            languages={languages}
            value={languageId}
            onChange={setLanguageId}
            disabled={loadingLanguages}
            hint="Required for coding questions (editor syntax). Shown on the assessments list."
          />
          {languageId && !loadingTopics && topics.length > 0 && (
            <div>
              <p className="muted" style={{ margin: "0 0 0.5rem" }}>
                Catalog topics (select one or more):
              </p>
              <ul className="topic-pick-list">
                {topics.map((t) => {
                  const idStr = String(t.id);
                  const on = selectedTopicIds.includes(idStr);
                  return (
                    <li key={t.id}>
                      <label
                        className={
                          on ? "topic-pick-item topic-pick-item--on" : "topic-pick-item"
                        }
                      >
                        <input
                          className="topic-pick-item__input"
                          type="checkbox"
                          checked={on}
                          onChange={() => toggleTopic(t.id)}
                        />
                        <span className="topic-pick-item__name">{t.name}</span>
                      </label>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
          <label>
            Custom topic label (if none selected above)
            <input
              type="text"
              value={customTopic}
              onChange={(e) => setCustomTopic(e.target.value)}
              placeholder="e.g. Python basics"
            />
          </label>
        </div>
        {(draftType === "coding" || hasCodingInList) && !languageCodeForSave && (
          <p className="manual-lang-required">Select a language for coding questions.</p>
        )}
      </section>

      <section className="card">
        <h2 className="manual-section-head">Add question</h2>

        <div className="manual-type-row" role="tablist" aria-label="Question type">
          {(["mcq", "coding", "subjective"]).map((t) => (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={draftType === t}
              className={
                draftType === t ? "manual-type-btn manual-type-btn--active" : "manual-type-btn"
              }
              onClick={() => {
                setDraftType(t);
                setFormError(null);
              }}
            >
              {TYPE_LABELS[t]}
            </button>
          ))}
        </div>

        {draftType === "mcq" && (
          <div className="manual-form-grid">
            <label>
              Question
              <textarea
                rows={3}
                value={mcqDraft.question}
                onChange={(e) => setMcqDraft((d) => ({ ...d, question: e.target.value }))}
              />
            </label>
            <div>
              <p className="muted" style={{ margin: "0 0 0.5rem" }}>
                Answer options
              </p>
              <div className="manual-form-grid--mcq-options">
                {mcqOptions.map((opt, idx) => (
                  <div key={`opt-${idx}`} className="manual-option-row">
                    <span className="manual-option-letter" aria-hidden>
                      {String.fromCharCode(65 + idx)}
                    </span>
                    <input
                      type="text"
                      value={opt}
                      placeholder={`Option ${String.fromCharCode(65 + idx)}`}
                      onChange={(e) => {
                        const next = [...mcqOptions];
                        next[idx] = e.target.value;
                        setMcqDraft((d) => ({ ...d, options: next }));
                      }}
                    />
                    {mcqOptions.length > 2 && (
                      <button
                        type="button"
                        className="btn-table-danger"
                        onClick={() =>
                          setMcqDraft((d) => ({
                            ...d,
                            options: d.options.filter((_, i) => i !== idx),
                          }))
                        }
                      >
                        Remove
                      </button>
                    )}
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="btn-table-secondary"
                style={{ marginTop: "0.5rem" }}
                onClick={() =>
                  setMcqDraft((d) => ({ ...d, options: [...(d.options || []), ""] }))
                }
              >
                + Add option
              </button>
            </div>
            <label>
              Correct answer
              <select
                value={mcqDraft.correct_answer}
                onChange={(e) => setMcqDraft((d) => ({ ...d, correct_answer: e.target.value }))}
              >
                <option value="">— Select —</option>
                {mcqOptions
                  .map((o) => o.trim())
                  .filter(Boolean)
                  .map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
              </select>
            </label>
          </div>
        )}

        {draftType === "coding" && (
          <div className="manual-form-grid">
            <p className="manual-coding-hint">
              Participants get a code editor using language: <strong>{selectedLangName}</strong>.
              Add a reference solution or rubric below for LLM grading (optional).
            </p>
            <label>
              Coding prompt
              <textarea
                rows={4}
                value={codingDraft.question}
                onChange={(e) => setCodingDraft((d) => ({ ...d, question: e.target.value }))}
                placeholder="Describe the task, constraints, and expected behaviour…"
              />
            </label>
            <label>
              Reference solution / rubric (optional)
              <textarea
                rows={6}
                className="code-font"
                value={codingDraft.correct_answer}
                onChange={(e) =>
                  setCodingDraft((d) => ({ ...d, correct_answer: e.target.value }))
                }
                placeholder="# Example solution or grading notes"
                spellCheck={false}
              />
            </label>
          </div>
        )}

        {draftType === "subjective" && (
          <div className="manual-form-grid">
            <label>
              Question
              <textarea
                rows={3}
                value={subjectiveDraft.question}
                onChange={(e) =>
                  setSubjectiveDraft((d) => ({ ...d, question: e.target.value }))
                }
              />
            </label>
            <label>
              Reference answer (optional, for grading)
              <textarea
                rows={3}
                value={subjectiveDraft.correct_answer}
                onChange={(e) =>
                  setSubjectiveDraft((d) => ({ ...d, correct_answer: e.target.value }))
                }
              />
            </label>
          </div>
        )}

        {formError && (
          <div className="error" role="alert" style={{ marginTop: "1rem" }}>
            {formError}
          </div>
        )}

        <div className="manual-form-actions">
          <button type="button" className="primary" onClick={appendQuestion}>
            Append question
          </button>
          <span className="muted">
            {questions.length} question{questions.length === 1 ? "" : "s"} queued
          </span>
        </div>
      </section>

      {questions.length > 0 && (
        <section className="card manual-questions-card">
          <h2 className="manual-section-head">Questions ({questions.length})</h2>
          <ol className="admin-q-list">
            {questions.map((q, i) => (
              <li key={`draft-q-${i}`}>
                <div className="admin-q-head">
                  <span className="pill">{q.type}</span>
                  <button
                    type="button"
                    className="btn-table-danger"
                    onClick={() => removeQuestion(i)}
                  >
                    Remove
                  </button>
                </div>
                <p className="admin-q-stem">{q.question}</p>
                {q.type === "mcq" && (
                  <ul className="admin-q-options muted">
                    {q.options.map((opt, j) => (
                      <li key={j}>
                        {opt}
                        {opt === q.correct_answer ? " ✓" : ""}
                      </li>
                    ))}
                  </ul>
                )}
                {q.type === "coding" && q.correct_answer && (
                  <pre className="manual-code-preview muted">{q.correct_answer}</pre>
                )}
                {q.type === "subjective" && q.correct_answer && (
                  <p className="muted" style={{ margin: "0.35rem 0 0", fontSize: "0.85rem" }}>
                    Reference: {q.correct_answer}
                  </p>
                )}
              </li>
            ))}
          </ol>
          <div className="manual-form-actions">
            <button
              type="button"
              className="primary"
              disabled={loading}
              onClick={() => void handleSave()}
            >
              {loading ? "Saving…" : "Save assessment"}
            </button>
          </div>
        </section>
      )}

      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}

      {createdId && (
        <section className="card card--success">
          <p>
            Assessment saved: <code>{createdId}</code>
          </p>
          <p className="muted">
            <Link to="/admin/assessments">View in assessments list</Link>
            {" · "}
            <Link to="/client" state={{ assessmentId: createdId }}>
              Open participant view
            </Link>
          </p>
        </section>
      )}
    </div>
  );
}
