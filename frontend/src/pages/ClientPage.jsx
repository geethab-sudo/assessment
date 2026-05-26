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
  const [notebookFile, setNotebookFile] = useState(null);

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
      setNotebookFile(null);
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
    if (!assessment) {
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

    if (assessment.routing_flag === "jupyter") {
      if (!notebookFile) {
        setError("Please select a Jupyter notebook (.ipynb) file to upload.");
        return;
      }
      setLoading(true);
      try {
        const formData = new FormData();
        formData.append("assessment_id", assessment.assessment_id);
        formData.append("user_id", `${empid} | ${name}`);
        formData.append("file", notebookFile);

        const data = await apiFetch("/submit-notebook-assessment", {
          method: "POST",
          body: formData,
        });
        setResult(data);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
      return;
    }

    if (!assessment.questions?.length) {
      setError("No questions found in this assessment.");
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

      {assessment && (assessment.routing_flag === "jupyter" || assessment.questions?.length > 0) && (
        <section className={`card${result ? " card-after-submit" : ""}`}>
          {assessment.routing_flag === "jupyter" ? (
            <div className="jupyter-workspace-panel" style={{ padding: "10px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px" }}>
                <span className="pill" style={{ background: "#f37021", color: "#fff", fontWeight: "bold" }}>Jupyter Sandbox</span>
                <span className="muted">Assessment ID: {assessment.assessment_id}</span>
              </div>
              <h2 style={{ fontSize: "1.5rem", marginBottom: "8px", fontWeight: "700" }}>Jupyter Notebook Assessment</h2>
              <p className="muted" style={{ marginBottom: "24px", lineHeight: "1.6" }}>
                This assessment is conducted in a Jupyter Notebook environment. Download the template below, open and solve it in your local Jupyter workspace, then upload the solved file here.
              </p>

              <div className="steps-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "20px", marginBottom: "32px" }}>
                {/* Step 1 */}
                <div className="step-card" style={{
                  background: "rgba(255,255,255,0.05)",
                  border: "1px solid rgba(0,0,0,0.08)",
                  borderRadius: "12px",
                  padding: "24px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "12px"
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <div style={{
                      width: "28px",
                      height: "28px",
                      borderRadius: "50%",
                      background: "var(--primary-color, #1a73e8)",
                      color: "#fff",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontWeight: "bold",
                      fontSize: "0.9rem"
                    }}>1</div>
                    <h3 style={{ fontSize: "1.1rem", margin: 0, fontWeight: "600" }}>Download Template</h3>
                  </div>
                  <p className="muted small-print" style={{ margin: 0, lineHeight: "1.5" }}>
                    Obtain the official notebook template containing all questions and guidelines.
                  </p>
                  <a
                    href={`${import.meta.env.VITE_API_URL || "/api"}/assessment/${encodeURIComponent(assessment.assessment_id)}/template`}
                    download={`assessment_${assessment.assessment_id}.ipynb`}
                    className="button secondary download-btn"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      textDecoration: "none",
                      gap: "8px",
                      marginTop: "auto",
                      padding: "10px 16px",
                      borderRadius: "8px",
                      background: "rgba(0,0,0,0.05)",
                      color: "inherit",
                      fontWeight: "500",
                      transition: "background 0.2s"
                    }}
                  >
                    <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"></path></svg>
                    Download .ipynb Template
                  </a>
                </div>

                {/* Step 2 */}
                <div className="step-card" style={{
                  background: "rgba(255,255,255,0.05)",
                  border: "1px solid rgba(0,0,0,0.08)",
                  borderRadius: "12px",
                  padding: "24px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "12px"
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <div style={{
                      width: "28px",
                      height: "28px",
                      borderRadius: "50%",
                      background: "var(--primary-color, #1a73e8)",
                      color: "#fff",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontWeight: "bold",
                      fontSize: "0.9rem"
                    }}>2</div>
                    <h3 style={{ fontSize: "1.1rem", margin: 0, fontWeight: "600" }}>Upload Solved Notebook</h3>
                  </div>
                  <p className="muted small-print" style={{ margin: 0, lineHeight: "1.5" }}>
                    Upload your completed Jupyter Notebook file (.ipynb) containing your solutions.
                  </p>
                  
                  <div className="file-upload-zone" style={{
                    border: "2px dashed var(--border, #ccc)",
                    borderRadius: "8px",
                    padding: "16px",
                    textAlign: "center",
                    marginTop: "auto",
                    background: "rgba(0,0,0,0.02)",
                    cursor: "pointer",
                    transition: "border-color 0.2s, background-color 0.2s"
                  }}>
                    <input
                      type="file"
                      accept=".ipynb"
                      id="notebook-file-input"
                      style={{ display: "none" }}
                      disabled={!!result}
                      onChange={(e) => {
                        if (e.target.files?.[0]) {
                          setNotebookFile(e.target.files[0]);
                        }
                      }}
                    />
                    <label htmlFor="notebook-file-input" style={{ cursor: "pointer", display: "block" }}>
                      <svg width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" style={{ margin: "0 auto 8px auto", opacity: 0.7 }}><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"></path></svg>
                      {notebookFile ? (
                        <div className="file-info" style={{ wordBreak: "break-all" }}>
                          <strong style={{ fontSize: "0.95rem" }}>{notebookFile.name}</strong>
                          <p className="muted small-print" style={{ margin: "4px 0 0 0" }}>{(notebookFile.size / 1024).toFixed(1)} KB</p>
                        </div>
                      ) : (
                        <span className="muted" style={{ fontSize: "0.9rem" }}>Select solved notebook file</span>
                      )}
                    </label>
                  </div>
                </div>
              </div>

              <div style={{ marginTop: "16px" }}>
                <button
                  type="button"
                  className="primary"
                  onClick={handleSubmit}
                  disabled={loading || !!result}
                  style={{ width: "100%", padding: "12px 24px", fontSize: "1rem", fontWeight: "600", borderRadius: "8px" }}
                >
                  {result ? "Submitted" : loading ? "Submitting…" : "Submit notebook"}
                </button>
              </div>
            </div>
          ) : (
            <>
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
            </>
          )}
          {result && (
            <p className="muted submit-locked-hint" role="status">
              This assessment has been submitted. Load a different assessment ID to take another test.
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
