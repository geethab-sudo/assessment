export default function AssessmentTimerBar({
  mainLabel,
  notebookLabel,
  mainTone,
  inNotebookGrace,
  durationMinutes,
  notebookGraceMinutes,
}) {
  if (!mainLabel) return null;

  return (
    <div
      className={`assessment-timer assessment-timer--${mainTone}${inNotebookGrace ? " assessment-timer--grace" : ""}`}
      role="timer"
      aria-live="polite"
    >
      <div className="assessment-timer-main">
        <span className="assessment-timer-title">
          {inNotebookGrace ? "Main time ended" : "Time remaining"}
        </span>
        <span className="assessment-timer-value">{inNotebookGrace ? "0:00" : mainLabel}</span>
        {!inNotebookGrace && durationMinutes ? (
          <span className="assessment-timer-meta muted small-print">
            of {durationMinutes} min
          </span>
        ) : null}
      </div>
      {inNotebookGrace && notebookLabel ? (
        <div className="assessment-timer-grace">
          <span className="assessment-timer-title">Notebook upload</span>
          <span className="assessment-timer-value">{notebookLabel}</span>
          {notebookGraceMinutes ? (
            <span className="assessment-timer-meta muted small-print">
              +{notebookGraceMinutes} min grace
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
