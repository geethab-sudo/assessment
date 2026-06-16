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
import TimerExpiredBanner from "../components/TimerExpiredBanner.jsx";
import JupyterWorkspacePanel from "../components/JupyterWorkspacePanel.jsx";
import MixedNotebookPanel, { JupyterRequiredBanner } from "../components/MixedNotebookPanel.jsx";
import Pagination from "../components/Pagination.jsx";
import UnansweredSubmitAlert from "../components/UnansweredSubmitAlert.jsx";
import { usePagination } from "../hooks/usePagination.js";
import { countUnansweredQuestions } from "../lib/assessmentAnswers.js";
import { openReportPrintWindow } from "../lib/reportRenderer.js";

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
  const [reportLoading, setReportLoading] = useState(false);
  const [reportSummaryLoading, setReportSummaryLoading] = useState(false);
  const [reportData, setReportData] = useState(null);
  const [reportError, setReportError] = useState(null);
  const [unansweredWarning, setUnansweredWarning] = useState(null);
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
    setReportData(null);
    setReportError(null);
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
      setUnansweredWarning(null);
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

  const assessmentSubmitted = Boolean(result);

  const reportUrl = useMemo(() => {
    if (!assessment?.assessment_id || !employeeId.trim()) return null;
    return `/assessment/${encodeURIComponent(assessment.assessment_id)}/report?employee_id=${encodeURIComponent(employeeId.trim())}`;
  }, [assessment?.assessment_id, employeeId]);

  useEffect(() => {
    if (!result?.question_results?.length || !reportUrl) {
      setReportData(null);
      return undefined;
    }
    let cancelled = false;
    setReportSummaryLoading(true);
    setReportError(null);
    (async () => {
      try {
        const data = await apiFetch(reportUrl);
        if (!cancelled) setReportData(data);
      } catch (e) {
        if (!cancelled) setReportError(e.message);
      } finally {
        if (!cancelled) setReportSummaryLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [result, reportUrl]);

  const handleDownloadReport = useCallback(async () => {
    if (!reportUrl) return;
    setReportError(null);
    setReportLoading(true);
    try {
      const data = reportData ?? (await apiFetch(reportUrl));
      if (!reportData) setReportData(data);
      openReportPrintWindow(data);
    } catch (e) {
      setReportError(e.message);
    } finally {
      setReportLoading(false);
    }
  }, [reportUrl, reportData]);

  const timerState = useAssessmentTimer(assessment, {
    onMainExpire,
    onNotebookGraceEnd,
    paused: assessmentSubmitted,
  });

  // Auto-grade notebook when attached during grace (or after in-browser submit in mixed timed tests)
  useEffect(() => {
    const inNotebookUploadWindow =
      timerState.inNotebookGrace || (assessmentSubmitted && needsNotebook);
    if (!inNotebookUploadWindow || !notebookFile || notebookResult || !result) return;
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
    assessmentSubmitted,
    needsNotebook,
    notebookFile,
    notebookResult,
    result,
    handleSubmit,
  ]);

  const formLocked =
    !!result || autoSubmitting || (timerState.isTimed && !timerState.inMainWindow);

  const blockCodingPaste = formLocked || !assessment?.allow_pyodide_paste;

  const notebookUploadEnabled =
    !notebookResult &&
    (!timerState.isTimed ||
      timerState.inMainWindow ||
      timerState.inNotebookGrace ||
      (assessmentSubmitted && needsNotebook));

  const showFixedTimer = Boolean(
    assessment?.is_timed && assessment?.timer && !assessmentSubmitted
  );

  const questions = useMemo(() => assessment?.questions ?? [], [assessment?.questions]);
  const {
    page: questionPage,
    setPage: setQuestionPage,
    pageSize: questionPageSize,
    totalItems: totalQuestions,
    totalPages: questionTotalPages,
    paginatedItems: paginatedQuestions,
  } = usePagination(questions, { resetKey: assessment?.assessment_id });

  const handleQuestionPageChange = useCallback(
    (nextPage) => {
      setQuestionPage(nextPage);
      window.scrollTo({ top: 0, behavior: "smooth" });
    },
    [setQuestionPage]
  );

  const requestSubmit = useCallback(
    (opts = {}) => {
      if (opts.auto || opts.notebookOnly) {
        handleSubmit(opts);
        return;
      }

      if (assessment?.routing_flag === "jupyter" && needsNotebook) {
        handleSubmit(opts);
        return;
      }

      const { unanswered, total } = countUnansweredQuestions(assessment, answers);
      const timeAllowsWarning = !timerState.isTimed || timerState.inMainWindow;

      if (unanswered > 0 && timeAllowsWarning) {
        setUnansweredWarning({ opts, unanswered, total });
        return;
      }

      handleSubmit(opts);
    },
    [assessment, answers, needsNotebook, handleSubmit, timerState.isTimed, timerState.inMainWindow]
  );

  const handleConfirmUnansweredSubmit = useCallback(() => {
    const pending = unansweredWarning;
    setUnansweredWarning(null);
    if (pending) handleSubmit(pending.opts);
  }, [unansweredWarning, handleSubmit]);

  return (
    <div className={`page page--wide${showFixedTimer ? " page--timed-assessment" : ""}`}>
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
          {needsNotebook && !notebookResult && !assessmentSubmitted && (
            <TimerExpiredBanner
              timeExpiredBanner={timeExpiredBanner}
              inNotebookGrace={timerState.inNotebookGrace}
              notebookLabel={timerState.notebookLabel}
            />
          )}
        {assessment.routing_flag === "jupyter" && needsNotebook ? (
            <JupyterWorkspacePanel
              assessmentId={assessment.assessment_id}
              notebookFile={notebookFile}
              notebookUploadEnabled={notebookUploadEnabled}
              notebookResult={notebookResult}
              loading={loading}
              autoSubmitting={autoSubmitting}
              result={result}
              timerState={timerState}
              onFileChange={setNotebookFile}
              onSubmit={() => requestSubmit()}
            />
          ) : (
            <>
              {needsNotebook && (
                <JupyterRequiredBanner
                  assessmentId={assessment.assessment_id}
                  jupyterTopicNames={assessment.jupyter_topic_names}
                />
              )}
              <Pagination
                page={questionPage}
                totalPages={questionTotalPages}
                totalItems={totalQuestions}
                pageSize={questionPageSize}
                onPageChange={handleQuestionPageChange}
                itemLabel="questions"
              />
              {paginatedQuestions.map((q, questionIndex) => {
                const globalIndex = (questionPage - 1) * questionPageSize + questionIndex;
                const displayLabel = participantQuestionLabel(
                  globalIndex + 1,
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
                      protectCodeFromCopy
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
                        background: "var(--brand-orange-soft)",
                        border: "1px solid var(--brand-orange-border)",
                        borderRadius: "8px",
                        fontSize: "0.9rem",
                      }}>
                        <svg width="20" height="20" fill="none" stroke="var(--brand-orange)" strokeWidth="2" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
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
                              blockPaste={blockCodingPaste}
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
                                  blockPaste={blockCodingPaste}
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
              <Pagination
                page={questionPage}
                totalPages={questionTotalPages}
                totalItems={totalQuestions}
                pageSize={questionPageSize}
                onPageChange={handleQuestionPageChange}
                itemLabel="questions"
              />
              <button
                type="button"
                className="primary"
                onClick={() =>
                  timerState.inNotebookGrace && notebookFile && needsNotebook
                    ? requestSubmit({ notebookOnly: true })
                    : requestSubmit()
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
                <MixedNotebookPanel
                  assessmentId={assessment.assessment_id}
                  jupyterTopicNames={assessment.jupyter_topic_names}
                  notebookFile={notebookFile}
                  notebookResult={notebookResult}
                  notebookUploadEnabled={notebookUploadEnabled}
                  onFileChange={setNotebookFile}
                />
              )}

              {unansweredWarning && (
                <UnansweredSubmitAlert
                  unansweredCount={unansweredWarning.unanswered}
                  totalCount={unansweredWarning.total}
                  onConfirm={handleConfirmUnansweredSubmit}
                  onCancel={() => setUnansweredWarning(null)}
                />
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

          {reportSummaryLoading && (
            <p className="muted small-print">Loading topic summary…</p>
          )}
          {reportData?.topic_summary?.length > 0 && (
            <div className="report-topic-summary">
              <h3 className="result-feedback-title">Topic summary</h3>
              <div className="table-wrap">
                <table className="data-table report-topic-table">
                  <thead>
                    <tr>
                      <th>Topic</th>
                      <th>Questions</th>
                      <th>Score</th>
                      <th>Average %</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reportData.topic_summary.map((row) => (
                      <tr key={row.topic_name}>
                        <td>{row.topic_name}</td>
                        <td>{row.questions_count}</td>
                        <td>
                          {row.total_score} / {row.max_score}
                        </td>
                        <td>{row.percent}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div className="result-report-actions">
            <button
              type="button"
              className="primary"
              onClick={() => void handleDownloadReport()}
              disabled={reportLoading || reportSummaryLoading}
            >
              {reportLoading ? "Preparing report…" : "Download report (PDF)"}
            </button>
            <p className="muted small-print result-report-hint">
              Opens a printable summary (MCQ and in-browser coding). Jupyter items are not included yet.
            </p>
            {reportError && (
              <div className="error" role="alert">
                {reportError}
              </div>
            )}
          </div>
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
