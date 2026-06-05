/**
 * Banner shown during the notebook grace period after main time expires.
 * Visible only when the assessment is timed, notebook is expected, and
 * notebook has not yet been submitted.
 */
export default function TimerExpiredBanner({ timeExpiredBanner, inNotebookGrace, notebookLabel }) {
  if (!timeExpiredBanner && !inNotebookGrace) return null;

  return (
    <p
      className="assessment-timer-banner"
      role="status"
      style={{
        margin: "0 0 1rem 0",
        padding: "0.75rem 1rem",
        borderRadius: "8px",
        background: "var(--brand-orange-soft)",
        border: "1px solid var(--brand-orange-border)",
        fontSize: "0.9rem",
      }}
    >
      {timeExpiredBanner
        ? "Time expired — your in-browser answers were submitted. "
        : ""}
      {inNotebookGrace
        ? `Upload your Jupyter notebook (${notebookLabel} left) — it will be graded automatically when you select the file or when grace ends.`
        : null}
    </p>
  );
}
