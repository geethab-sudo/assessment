import { formatUnitScore, formatCorrectTotal, countCorrectResults } from "../lib/scoreDisplay.js";

/**
 * Shown at the end of the participant test after in-browser submit (MCQ + Pyodide coding).
 * Includes overall score and the printable feedback report download action.
 */
export default function InBrowserResultsPanel({
  result,
  routingFlag,
  reportLoading,
  reportError,
  onDownload,
  sectionRef,
}) {
  if (!result?.question_results?.length) return null;

  return (
    <section ref={sectionRef} className="result-card result-card--end" aria-label="Assessment results">
      <h2 className="result-card-title">
        Your results{routingFlag === "mixed" ? " — In-browser questions" : ""}
      </h2>
      <div className="result-summary">
        <div className="result-score-block">
          <span className="result-score-label">Total score</span>
          <div className="result-score-row">
            <span className="result-score-value">
              {formatCorrectTotal(
                countCorrectResults(result.question_results),
                result.questions_graded ?? result.question_results?.length
              )}
            </span>
          </div>
          {result.max_total > 0 && (
            <span className="muted small-print result-score-percent">
              Average {formatUnitScore(result.score)} / 1.0
            </span>
          )}
        </div>
        <div className="result-meta">
          <span className="result-meta-label">Questions graded</span>
          <span className="result-meta-value">{result.questions_graded}</span>
        </div>
      </div>
      <p className="muted small-print result-feedback-hint">
        Per-question feedback appears above. Download a full summary report below.
      </p>
      <div className="result-report-actions">
        <button
          type="button"
          className="primary"
          onClick={onDownload}
          disabled={reportLoading}
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
  );
}
