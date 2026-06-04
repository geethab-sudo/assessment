import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { apiFetch } from "../api";
import SimpleCodeEditor from "../components/SimpleCodeEditor.jsx";
import QuestionStem from "../components/QuestionStem.jsx";
import PythonRunPanel from "../components/PythonRunPanel.jsx";
import { catalogCodeToMonaco } from "../lib/monacoLanguageMap.js";
import { isShellCodingTopic, resolveShellEditorCode } from "../lib/shellEditor.js";
import { participantQuestionLabel } from "../lib/participantQuestionLabels.js";
import AssessmentTimerBar from "../components/AssessmentTimerBar.jsx";
import { useAssessmentTimer } from "../hooks/useAssessmentTimer.js";

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
  // Separate result state for the notebook upload path (used in mixed assessments)
  const [notebookResult, setNotebookResult] = useState(null);
  const [notebookFile, setNotebookFile] = useState(null);

  const [loading, setLoading] = useState(false);
  const [autoSubmitting, setAutoSubmitting] = useState(false);
  const [timeExpiredBanner, setTimeExpiredBanner] = useState(false);
  const [error, setError] = useState(null);
  const autoSubmitLock = useRef(false);
  const graceNotebookSubmitLock = useRef(false);
  const lastGraceSubmittedFile = useRef(null);

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
    setNotebookResult(null);
    setLoading(true);
    try {
      const id = assessmentIdInput.trim();
      const empid = employeeId.trim();
      if (!id) throw new Error("Enter an assessment ID.");
      if (!empid) throw new Error("Enter your employee ID before loading the test.");
      const params = new URLSearchParams({ employee_id: empid });
      const data = await apiFetch(
        `/assessment/${encodeURIComponent(id)}?${params.toString()}`
      );
      if (data.already_submitted) {
        setAssessment({ ...data, questions: [] });
        setError("You have already submitted this assessment.");
        return;
      }
      setAssessment(data);
      setAnswers({});
      setCodeLangByQid({});
      setNotebookFile(null);
      setTimeExpiredBanner(false);
      autoSubmitLock.current = false;
      graceNotebookSubmitLock.current = false;
      lastGraceSubmittedFile.current = null;
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

  const needsNotebook = assessment?.notebook_expected === true;

  const submitNotebook = useCallback(
    async (assessmentId, empid, name, file) => {
      const formData = new FormData();
      formData.append("assessment_id", assessmentId);
      formData.append("user_id", `${empid} | ${name}`);
      formData.append("file", file);
      return apiFetch("/submit-notebook-assessment", { method: "POST", body: formData });
    },
    []
  );

  const handleSubmit = useCallback(
    async (opts = {}) => {
      const { auto = false, skipNotebookConfirm = false, notebookOnly = false } = opts;

      if (result && !notebookOnly) return;
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

      if (notebookOnly) {
        if (!notebookFile) {
          setError("Select a Jupyter notebook file to upload.");
          return;
        }
        setLoading(true);
        try {
          const nbData = await submitNotebook(
            assessment.assessment_id,
            empid,
            name,
            notebookFile
          );
          setNotebookResult(nbData);
        } catch (e) {
          setError(e.message);
        } finally {
          setLoading(false);
        }
        return;
      }

      if (assessment.routing_flag === "jupyter" && needsNotebook) {
        if (!notebookFile) {
          if (auto) {
            setTimeExpiredBanner(true);
            return;
          }
          setError("Please select a Jupyter notebook (.ipynb) file to upload.");
          return;
        }
        setLoading(true);
        try {
          const data = await submitNotebook(
            assessment.assessment_id,
            empid,
            name,
            notebookFile
          );
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

      const isMixed = assessment.routing_flag === "mixed";

      if (
        needsNotebook &&
        !notebookFile &&
        !skipNotebookConfirm &&
        !auto
      ) {
        const proceed = window.confirm(
          "You haven't selected a Jupyter notebook file yet.\n\n" +
            "Your in-browser answers will be submitted now, but the Jupyter coding questions won't be graded.\n\n" +
            "Click OK to submit anyway, or Cancel to attach the notebook first."
        );
        if (!proceed) return;
      }

      setLoading(true);
      try {
        const id = assessment.assessment_id;
        const payload = {
          assessment_id: id,
          employee_id: empid,
          participant_name: name,
          answers: assessment.questions
            .filter(
              (q) =>
                !(isMixed && q.type === "coding" && q.topic_modality === "jupyter")
            )
            .map((q) => ({
              question_id: q.question_id,
              answer: answers[String(q.question_id)] ?? "",
            })),
        };
        const inBrowserData = await apiFetch("/submit-assessment", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        setResult(inBrowserData);
        if (auto) setTimeExpiredBanner(true);

        if (isMixed && notebookFile) {
          const nbData = await submitNotebook(id, empid, name, notebookFile);
          setNotebookResult(nbData);
        }
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    },
    [result, assessment, employeeId, participantName, notebookFile, answers, submitNotebook, needsNotebook]
  );

  const onMainExpire = useCallback(() => {
    if (autoSubmitLock.current || result) return;
    autoSubmitLock.current = true;
    setAutoSubmitting(true);
    handleSubmit({ auto: true, skipNotebookConfirm: true })
      .finally(() => setAutoSubmitting(false));
  }, [handleSubmit, result]);

  const onNotebookGraceEnd = useCallback(() => {
    if (!needsNotebook || notebookResult || !notebookFile) return;
    if (graceNotebookSubmitLock.current) return;
    if (lastGraceSubmittedFile.current === notebookFile.name && notebookResult) return;
    graceNotebookSubmitLock.current = true;
    setAutoSubmitting(true);
    handleSubmit({ notebookOnly: true }).finally(() => {
      setAutoSubmitting(false);
      graceNotebookSubmitLock.current = false;
    });
  }, [needsNotebook, notebookResult, notebookFile, handleSubmit]);

  const timerState = useAssessmentTimer(assessment, {
    onMainExpire,
    onNotebookGraceEnd,
  });

  // Auto-grade notebook as soon as it is attached during the grace window
  useEffect(() => {
    if (!timerState.inNotebookGrace || !notebookFile || notebookResult || !result) return;
    if (lastGraceSubmittedFile.current === notebookFile.name) return;
    lastGraceSubmittedFile.current = notebookFile.name;
    graceNotebookSubmitLock.current = true;
    setAutoSubmitting(true);
    handleSubmit({ notebookOnly: true }).finally(() => {
      setAutoSubmitting(false);
      graceNotebookSubmitLock.current = false;
    });
  }, [
    timerState.inNotebookGrace,
    notebookFile,
    notebookResult,
    result,
    handleSubmit,
  ]);

  const formLocked =
    !!result || autoSubmitting || (timerState.isTimed && !timerState.inMainWindow);

  const notebookUploadEnabled =
    !notebookResult &&
    (!timerState.isTimed || timerState.inMainWindow || timerState.inNotebookGrace);

  const showFixedTimer = Boolean(assessment?.is_timed && assessment?.timer);

  return (
    <div className={`page${showFixedTimer ? " page--timed-assessment" : ""}`}>
      {showFixedTimer && (
        <div className="assessment-timer-fixed" role="region" aria-label="Assessment timer">
          <AssessmentTimerBar
            mainLabel={timerState.mainLabel}
            notebookLabel={timerState.notebookLabel}
            mainTone={timerState.mainTone}
            inNotebookGrace={timerState.inNotebookGrace}
            durationMinutes={assessment.duration_minutes}
            notebookGraceMinutes={assessment.notebook_grace_minutes}
          />
        </div>
      )}
      <header className="header">
        <p className="page-eyebrow">Participant</p>
        <h1>Take assessment</h1>
        <p className="muted">
          Enter your employee ID, name, and the assessment ID you were given, then load the test.
          Question and MCQ option order are personalized to your employee ID. After you submit,
          this attempt is locked. No sign-in is required.
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
          <button
            type="button"
            onClick={handleFetchAssessment}
            disabled={loading || !employeeId.trim()}
          >
            Load test
          </button>
        </div>
      </section>

      {assessment && (
        <section className={`card${result ? " card-after-submit" : ""}`}>
          {(timeExpiredBanner || timerState.inNotebookGrace) && needsNotebook && !notebookResult && (
            <p
              className="assessment-timer-banner"
              role="status"
              style={{
                margin: "0 0 1rem 0",
                padding: "0.75rem 1rem",
                borderRadius: "8px",
                background: "rgba(243,112,33,0.1)",
                border: "1px solid rgba(243,112,33,0.35)",
                fontSize: "0.9rem",
              }}
            >
              {timeExpiredBanner
                ? "Time expired — your in-browser answers were submitted. "
                : ""}
              {timerState.inNotebookGrace
                ? `Upload your Jupyter notebook (${timerState.notebookLabel} left) — it will be graded automatically when you select the file or when grace ends.`
                : null}
            </p>
          )}
        {assessment.routing_flag === "jupyter" && needsNotebook ? (
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
                      disabled={!notebookUploadEnabled}
                      onChange={(e) => {
                        if (e.target.files?.[0]) {
                          setNotebookFile(e.target.files[0]);
                        }
                      }}
                    />
                    <label htmlFor="notebook-file-input" style={{ cursor: notebookUploadEnabled ? "pointer" : "not-allowed", display: "block" }}>
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
                  onClick={() => handleSubmit()}
                  disabled={
                    loading ||
                    autoSubmitting ||
                    !!result ||
                    (timerState.isTimed &&
                      !timerState.inMainWindow &&
                      !(timerState.inNotebookGrace && notebookFile))
                  }
                  style={{ width: "100%", padding: "12px 24px", fontSize: "1rem", fontWeight: "600", borderRadius: "8px" }}
                >
                  {result ? "Submitted" : loading ? "Submitting…" : "Submit notebook"}
                </button>
              </div>
            </div>
          ) : (
            <>
              {needsNotebook && (
                <div style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "16px",
                  background: "rgba(243,112,33,0.08)",
                  border: "1px solid rgba(243,112,33,0.35)",
                  borderRadius: "10px",
                  padding: "16px 20px",
                  marginBottom: "24px",
                  flexWrap: "wrap",
                }}>
                  <div style={{ flex: 1, minWidth: "200px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
                      <span className="pill" style={{ background: "#f37021", color: "#fff", fontWeight: "bold", fontSize: "0.78rem" }}>
                        Jupyter Required
                      </span>
                    </div>
                    <p style={{ margin: "0 0 6px 0", fontWeight: "600", fontSize: "0.95rem" }}>
                      The following topics must be completed in a Jupyter Notebook:
                    </p>
                    <ul style={{ margin: "0 0 0 16px", padding: 0, fontSize: "0.88rem" }}>
                      {assessment.jupyter_topic_names.map((name) => (
                        <li key={name} style={{ marginBottom: "2px" }}>{name}</li>
                      ))}
                    </ul>
                  </div>
                  <a
                    href={`${import.meta.env.VITE_API_URL || "/api"}/assessment/${encodeURIComponent(assessment.assessment_id)}/template`}
                    download={`assessment_${assessment.assessment_id}.ipynb`}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "8px",
                      padding: "10px 18px",
                      borderRadius: "8px",
                      background: "#f37021",
                      color: "#fff",
                      fontWeight: "600",
                      fontSize: "0.9rem",
                      textDecoration: "none",
                      whiteSpace: "nowrap",
                      alignSelf: "center",
                    }}
                  >
                    <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
                    </svg>
                    Download .ipynb
                  </a>
                </div>
              )}
              {assessment.questions.map((q, questionIndex) => {
                const totalQuestions = assessment.questions.length;
                const displayLabel = participantQuestionLabel(
                  questionIndex + 1,
                  totalQuestions
                );
                const qr = resultByQid[String(q.question_id)];
                const qk = String(q.question_id);
                const shellTopic = q.type === "coding" && isShellCodingTopic(q.coding_editor_language);
                const effectiveCatalogCode = shellTopic
                  ? resolveShellEditorCode(
                      qk in codeLangByQid ? codeLangByQid[qk] : null,
                      q.coding_editor_language
                    )
                  : (qk in codeLangByQid ? codeLangByQid[qk] : null) || assessment?.language_code;
                const codingMonaco =
                  q.type === "coding" ? catalogCodeToMonaco(effectiveCatalogCode) : "python";
                const useShellTerminal =
                  shellTopic && (codingMonaco === "shell" || codingMonaco === "powershell");
                return (
                  <div key={String(q.question_id)} className="question">
                    <div className="qhead">
                      <span className="pill">{q.type}</span>
                      <span className="muted">{displayLabel}</span>
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
                    <QuestionStem
                      question={q.question}
                      code={q.code}
                      languageCode={assessment?.language_code}
                    />
                    {q.type === "mcq" && Array.isArray(q.options) ? (
                      <div className="options" role="group" aria-label={`${displayLabel} choices`}>
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
                              disabled={formLocked}
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
                    ) : q.type === "coding" && q.topic_modality === "jupyter" ? (
                      <div style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "12px",
                        padding: "16px 20px",
                        background: "rgba(243,112,33,0.07)",
                        border: "1px solid rgba(243,112,33,0.3)",
                        borderRadius: "8px",
                        fontSize: "0.9rem",
                      }}>
                        <svg width="20" height="20" fill="none" stroke="#f37021" strokeWidth="2" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
                          <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                        </svg>
                        <span>
                          Complete this question in the <strong>Jupyter Notebook</strong> — download it from the panel above.
                        </span>
                      </div>
                    ) : q.type === "coding" ? (
                      <div
                        className={`code-playground${useShellTerminal ? " code-playground--shell" : ""}`}
                        aria-label={useShellTerminal ? "Shell commands editor" : "Code playground"}
                      >
                        <header className="code-playground-chrome">
                          <div className="code-playground-chrome-top">
                            <span className="code-playground-chrome-title">
                              {useShellTerminal ? "Shell commands" : "Code playground"}
                            </span>
                            <span
                              className="code-playground-chrome-pill"
                              title={
                                useShellTerminal
                                  ? "Shell mode — commands are graded on submit"
                                  : "Language mode (Execute uses Python)"
                              }
                            >
                              {useShellTerminal
                                ? codingMonaco === "powershell"
                                  ? "PowerShell"
                                  : "Bash"
                                : codingMonaco}
                            </span>
                            <span className="code-playground-chrome-pill" style={{ opacity: 0.6, fontSize: "0.72rem", fontFamily: "monospace" }} title="Toggle comment on selected lines">
                              Ctrl+/
                            </span>
                          </div>
                          {shellTopic ? (
                            <div className="code-playground-lang">
                              <label className="code-playground-lang-label">
                                <span className="code-playground-lang-text">Shell</span>
                                <select
                                  value={qk in codeLangByQid ? (codeLangByQid[qk] || "") : ""}
                                  onChange={(e) => setCodeLanguageForQuestion(q.question_id, e.target.value)}
                                  disabled={formLocked}
                                >
                                  <option value="">
                                    {q.coding_editor_language === "powershell"
                                      ? "Default (PowerShell)"
                                      : "Default (Bash)"}
                                  </option>
                                  <option value="shell">Bash / sh</option>
                                  <option value="powershell">PowerShell</option>
                                </select>
                              </label>
                            </div>
                          ) : catalogLanguages.length > 0 ? (
                            <div className="code-playground-lang">
                              <label className="code-playground-lang-label">
                                <span className="code-playground-lang-text">Language</span>
                                <select
                                  value={qk in codeLangByQid ? (codeLangByQid[qk] || "") : ""}
                                  onChange={(e) => setCodeLanguageForQuestion(q.question_id, e.target.value)}
                                  disabled={formLocked}
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
                          ) : null}
                        </header>
                        {useShellTerminal ? (
                          <div className="code-playground-editor-only">
                            <SimpleCodeEditor
                              value={answers[qk] ?? ""}
                              onChange={(v) => setAnswer(q.question_id, v)}
                              readOnly={formLocked}
                              minHeight={320}
                              language={codingMonaco}
                            />
                          </div>
                        ) : (
                          <div className="code-playground-split">
                            <section className="code-playground-pane code-playground-pane--editor">
                              <div className="code-playground-pane-tab" aria-hidden="true">
                                Editor
                              </div>
                              <div className="code-playground-editor-wrap">
                                <SimpleCodeEditor
                                  value={answers[qk] ?? ""}
                                  onChange={(v) => setAnswer(q.question_id, v)}
                                  readOnly={formLocked}
                                  minHeight={320}
                                  language={codingMonaco}
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
                                  disabled={formLocked}
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
                        )}
                      </div>
                    ) : (
                      <textarea
                        rows={5}
                        placeholder="Your answer here…"
                        value={answers[String(q.question_id)] ?? ""}
                        onChange={(e) => setAnswer(q.question_id, e.target.value)}
                        readOnly={formLocked}
                        autoComplete="off"
                        spellCheck={false}
                      />
                    )}
                    {result && qr != null && (
                      <div
                        className={`question-feedback${qr.correct ? " question-feedback--correct" : " question-feedback--wrong"}`}
                        role="status"
                      >
                        <div className="question-feedback-header">
                          <span className="question-feedback-label">Feedback</span>
                          <span className="question-feedback-score">{qr.score}/100</span>
                        </div>
                        {qr.feedback ? (
                          <p className="question-feedback-body">{qr.feedback}</p>
                        ) : (
                          <p className="question-feedback-body muted">No feedback for this question.</p>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
              <button
                type="button"
                className="primary"
                onClick={() =>
                  timerState.inNotebookGrace && notebookFile && needsNotebook
                    ? handleSubmit({ notebookOnly: true })
                    : handleSubmit()
                }
                disabled={
                  loading ||
                  autoSubmitting ||
                  !!result ||
                  (timerState.isTimed && !timerState.inMainWindow && !(timerState.inNotebookGrace && notebookFile && needsNotebook))
                }
              >
                {result
                  ? "Submitted"
                  : autoSubmitting
                    ? "Submitting…"
                    : loading
                      ? "Submitting…"
                      : timerState.inNotebookGrace && notebookFile && needsNotebook
                        ? "Upload notebook"
                        : "Submit answers"}
              </button>

              {needsNotebook && (
                <div style={{
                  marginTop: "32px",
                  padding: "20px 24px",
                  background: "rgba(243,112,33,0.07)",
                  border: "1px solid rgba(243,112,33,0.3)",
                  borderRadius: "10px",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
                    <span className="pill" style={{ background: "#f37021", color: "#fff", fontWeight: "bold", fontSize: "0.78rem" }}>
                      Jupyter Notebook
                    </span>
                    <span style={{ fontWeight: "600", fontSize: "0.95rem" }}>Upload your completed notebook</span>
                  </div>
                  <p className="muted small-print" style={{ margin: "0 0 14px 0" }}>
                    Select your completed <code>.ipynb</code> file below — it is graded automatically on submit or during the grace period after time expires.
                  </p>
                  <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
                    <input
                      type="file"
                      accept=".ipynb"
                      id="mixed-notebook-input"
                      style={{ display: "none" }}
                      disabled={!notebookUploadEnabled}
                      onChange={(e) => { if (e.target.files?.[0]) setNotebookFile(e.target.files[0]); }}
                    />
                    <label htmlFor="mixed-notebook-input" style={{
                      display: "inline-flex", alignItems: "center", gap: "8px",
                      padding: "9px 16px", borderRadius: "7px", cursor: notebookResult ? "not-allowed" : "pointer",
                      background: "rgba(0,0,0,0.06)", fontWeight: "500", fontSize: "0.9rem",
                      border: "1px solid rgba(0,0,0,0.12)",
                      opacity: notebookResult ? 0.5 : 1,
                    }}>
                      <svg width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>
                      </svg>
                      {notebookFile ? notebookFile.name : "Choose .ipynb file"}
                    </label>
                    {notebookFile && (
                      <span style={{ fontSize: "0.85rem", color: "#2a7a2a", fontWeight: "500" }}>
                        ✓ Ready — will be submitted with your answers
                      </span>
                    )}
                  </div>
                </div>
              )}
            </>
          )}
          {result && assessment?.routing_flag !== "mixed" && (
            <p className="muted submit-locked-hint" role="status">
              This assessment has been submitted. Load a different assessment ID to take another test.
            </p>
          )}
          {result && assessment?.routing_flag === "mixed" && notebookResult && (
            <p className="muted submit-locked-hint" role="status">
              All sections submitted. Load a different assessment ID to take another test.
            </p>
          )}
          {result && assessment?.routing_flag === "mixed" && !notebookResult && (
            <p className="muted submit-locked-hint" role="status">
              In-browser questions submitted. Jupyter notebook was not included — load a new assessment ID to retry.
            </p>
          )}
        </section>
      )}

      {result && (
        <section className="card result-card">
          <h2 className="result-card-title">
            Results{assessment?.routing_flag === "mixed" ? " — In-browser questions" : ""}
          </h2>
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
          <p className="muted small-print result-feedback-hint">
            See feedback under each question above.
          </p>
        </section>
      )}

      {notebookResult && (
        <section className="card result-card">
          <h2 className="result-card-title">Results — Jupyter notebook</h2>
          <div className="result-summary">
            <div className="result-score-block">
              <span className="result-score-label">Average score</span>
              <div className="result-score-row">
                <span className="result-score-value">{notebookResult.score}</span>
                <span className="result-score-suffix">/ 100</span>
              </div>
            </div>
            <div className="result-meta">
              <span className="result-meta-label">Questions graded</span>
              <span className="result-meta-value">{notebookResult.questions_graded}</span>
            </div>
          </div>
          <div className="result-feedback">
            <h3 className="result-feedback-title">Feedback</h3>
            <pre className="result-feedback-body">{notebookResult.feedback}</pre>
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
