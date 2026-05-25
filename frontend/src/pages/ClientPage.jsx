import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiFetch } from "../api";
import SimpleCodeEditor from "../components/SimpleCodeEditor.jsx";
import PythonRunPanel from "../components/PythonRunPanel.jsx";
import { catalogCodeToMonaco } from "../lib/monacoLanguageMap.js";

export default function ClientPage() {
  const location = useLocation();
  const initialId =
    typeof location.state?.assessmentId === "string"
      ? location.state.assessmentId
      : "";

  const [assessmentIdInput, setAssessmentIdInput] = useState(initialId);
  const [employeeId, setEmployeeId] = useState("");
  const [participantName, setParticipantName] = useState("");

  const [assessment, setAssessment] = useState(null);
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  /** @type {Array<{ id: number, code: string, name: string }>} */
  const [catalogLanguages, setCatalogLanguages] = useState([]);
  /** Per-question override: catalog language `code` for syntax mode */
  const [codeLangByQid, setCodeLangByQid] = useState({});

  // When navigating from Admin with state, sync the input once
  useEffect(() => {
    if (initialId) {
      setAssessmentIdInput(initialId);
    }
  }, [initialId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await apiFetch("/catalog/languages");
        const list = data.languages ?? [];
        if (!cancelled) setCatalogLanguages(Array.isArray(list) ? list : []);
      } catch {
        if (!cancelled) setCatalogLanguages([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setAnswer = (qid, value) => {
    setAnswers((prev) => ({ ...prev, [String(qid)]: value }));
  };


  const setCodeLanguageForQuestion = useCallback((qid, catalogCode) => {
    const k = String(qid);
    setCodeLangByQid((prev) => {
      if (!catalogCode) {
        if (!(k in prev)) return prev;
        const next = { ...prev };
        delete next[k];
        return next;
      }
      if (prev[k] === catalogCode) return prev;
      return { ...prev, [k]: catalogCode };
    });
  }, []);

  const handleFetchAssessment = async () => {
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const id = assessmentIdInput.trim();
      if (!id) throw new Error("Enter an assessment ID.");
      const data = await apiFetch(`/assessment/${encodeURIComponent(id)}`);
      setAssessment(data);
      setAnswers({});
      setCodeLangByQid({});
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const resultByQid = useMemo(() => {
    if (!result?.question_results?.length) return {};
    return Object.fromEntries(
      result.question_results.map((r) => [String(r.question_id), r])
    );
  }, [result]);

  const handleSubmit = async () => {
    if (result) {
      return;
    }
    setError(null);
    if (!assessment?.questions?.length) {
      setError("Load an assessment first.");
      return;
    }
    const empid = employeeId.trim();
    const name = participantName.trim();
    if (!empid) {
      setError("Enter your employee ID.");
      return;
    }
    if (!name) {
      setError("Enter your name.");
      return;
    }
    setLoading(true);
    try {
      const id = assessment.assessment_id;
      const payload = {
        assessment_id: id,
        employee_id: empid,
        participant_name: name,
        answers: assessment.questions.map((q) => ({
          question_id: q.question_id,
          answer: answers[String(q.question_id)] ?? "",
        })),
      };
      const data = await apiFetch("/submit-assessment", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <header className="header">
        <p className="page-eyebrow">Participant</p>
        <h1>Take assessment</h1>
        <p className="muted">
          Enter your employee ID, name, and the assessment ID you were given, then load the test.
          After you submit, this attempt is locked. No sign-in is required.
        </p>

      </header>

      <section className="card">
        <h2>Your details and assessment</h2>
        <div className="row">
          <label className="grow">
            Employee ID
            <input
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              placeholder="e.g. E1001"
              autoComplete="username"
            />
          </label>
          <label className="grow">
            Name
            <input
              value={participantName}
              onChange={(e) => setParticipantName(e.target.value)}
              placeholder="Full name"
              autoComplete="name"
            />
          </label>
        </div>
        <div className="row">
          <label className="grow">
            Assessment ID
            <input
              value={assessmentIdInput}
              onChange={(e) => setAssessmentIdInput(e.target.value)}
              placeholder="paste the assessment id"
            />
          </label>
          <button type="button" onClick={handleFetchAssessment} disabled={loading}>
            Load test
          </button>
        </div>
      </section>

      {assessment?.questions?.length > 0 && (
        <section className={`card${result ? " card-after-submit" : ""}`}>
          <h2>Questions{result ? " — your results" : ""}</h2>
          {assessment.questions.map((q) => {
            const qr = resultByQid[String(q.question_id)];
            const qk = String(q.question_id);
            const codingMonaco =
              q.type === "coding"
                ? catalogCodeToMonaco(
                    (qk in codeLangByQid ? codeLangByQid[qk] : null) || assessment?.language_code
                  )
                : "python";
            return (
            <div key={String(q.question_id)} className="question">
              <div className="qhead">
                <span className="pill">{q.type}</span>
                <span className="muted">Q{q.question_id}</span>
                {result && qr != null && (
                  <span
                    className={`result-tick ${qr.correct ? "correct" : "wrong"}`}
                    title={`Score ${qr.score}/100${qr.feedback ? ` — ${qr.feedback}` : ""}`}
                    role="img"
                    aria-label={qr.correct ? "Correct" : "Incorrect"}
                  >
                    {qr.correct ? "✓" : "✗"}
                  </span>
                )}
              </div>
              <p className="question-stem">{q.question}</p>
              {q.type === "mcq" && Array.isArray(q.options) ? (
                <div className="options" role="group" aria-label={`Question ${q.question_id} choices`}>
                  {q.options.map((opt, idx) => (
                    <label
                      key={`${q.question_id}-${idx}`}
                      className="opt"
                    >
                      <input
                        type="radio"
                        name={`mcq-${q.question_id}`}
                        value={opt}
                        checked={answers[String(q.question_id)] === opt}
                        onChange={() => setAnswer(q.question_id, opt)}
                        disabled={!!result}
                      />
                      <span className="opt-text">
                        <span className="opt-letter" aria-hidden="true">
                          {String.fromCharCode(65 + idx)}
                        </span>
                        <span className="opt-body">{opt}</span>
                      </span>
                    </label>
                  ))}
                </div>
              ) : q.type === "coding" ? (
                <div className="code-playground" aria-label="Code playground">
                  <header className="code-playground-chrome">
                    <div className="code-playground-chrome-top">
                      <span className="code-playground-chrome-title">Code playground</span>
                      <span className="code-playground-chrome-pill" title="Language mode (Execute uses Python)">
                        {codingMonaco}
                      </span>
                    </div>
                    {catalogLanguages.length > 0 && (
                      <div className="code-playground-lang">
                        <label className="code-playground-lang-label">
                          <span className="code-playground-lang-text">Language</span>
                          <select
                            value={qk in codeLangByQid ? (codeLangByQid[qk] || "") : ""}
                            onChange={(e) => setCodeLanguageForQuestion(q.question_id, e.target.value)}
                            disabled={!!result}
                          >
                            <option value="">
                              {assessment?.language_code
                                ? `Default (${assessment.language_code})`
                                : "Default (Python)"}
                            </option>
                            {catalogLanguages.map((lang) => (
                              <option key={lang.id} value={lang.code}>
                                {lang.name} ({lang.code})
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                    )}
                  </header>
                  <div className="code-playground-split">
                    <section className="code-playground-pane code-playground-pane--editor">
                      <div className="code-playground-pane-tab" aria-hidden="true">
                        Editor
                      </div>
                      <div className="code-playground-editor-wrap">
                        <SimpleCodeEditor
                          value={answers[qk] ?? ""}
                          onChange={(v) => setAnswer(q.question_id, v)}
                          readOnly={!!result}
                          minHeight={320}
                        />
                      </div>
                    </section>
                    <section className="code-playground-pane code-playground-pane--console">
                      <div className="code-playground-pane-tab" aria-hidden="true">
                        Console
                      </div>
                      {codingMonaco === "python" ? (
                        <PythonRunPanel
                          code={answers[qk] ?? ""}
                          disabled={!!result}
                          variant="playground"
                        />
                      ) : (
                        <div className="code-playground-console-fallback muted small-print">
                          In-browser <strong>Execute</strong> (Pyodide) needs the editor in{" "}
                          <strong>Python</strong> mode. Use the language control above, or pick an assessment whose
                          default maps to Python.
                        </div>
                      )}
                    </section>
                  </div>
                </div>
              ) : (
                <textarea
                  rows={5}
                  placeholder="Your answer here…"
                  value={answers[String(q.question_id)] ?? ""}
                  onChange={(e) => setAnswer(q.question_id, e.target.value)}
                  readOnly={!!result}
                  autoComplete="off"
                  spellCheck={false}
                />

              )}
            </div>
          );
          })}
          <button
            type="button"
            className="primary"
            onClick={handleSubmit}
            disabled={loading || !!result}
          >
            {result ? "Submitted" : loading ? "Submitting…" : "Submit answers"}
          </button>
          {result && (
            <p className="muted submit-locked-hint" role="status">
              This assessment has been submitted. Load a different assessment ID to take another
              test.
            </p>
          )}
        </section>
      )}

      {result && (
        <section className="card result-card">
          <h2 className="result-card-title">Results</h2>
          <div className="result-summary">
            <div className="result-score-block">
              <span className="result-score-label">Average score</span>
              <div className="result-score-row">
                <span className="result-score-value">{result.score}</span>
                <span className="result-score-suffix">/ 100</span>
              </div>
            </div>
            <div className="result-meta">
              <span className="result-meta-label">Questions graded</span>
              <span className="result-meta-value">{result.questions_graded}</span>
            </div>
          </div>
          <div className="result-feedback">
            <h3 className="result-feedback-title">Feedback</h3>
            <pre className="result-feedback-body">{result.feedback}</pre>
          </div>
        </section>
      )}

      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}

      <p className="muted footer-hint">
        <Link to="/login/admin">Admin login</Link> creates assessments.
      </p>
    </div>
  );
}
