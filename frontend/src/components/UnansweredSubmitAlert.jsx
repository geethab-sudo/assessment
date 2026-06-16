/**
 * Shown when a participant tries to submit with blank answers while time remains.
 */
export default function UnansweredSubmitAlert({
  unansweredCount,
  totalCount,
  onConfirm,
  onCancel,
}) {
  const answeredCount = Math.max(0, totalCount - unansweredCount);

  return (
    <div className="unanswered-submit-alert" role="presentation">
      <div
        className="unanswered-submit-alert__panel"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="unanswered-submit-title"
        aria-describedby="unanswered-submit-desc"
      >
        <div className="unanswered-submit-alert__icon" aria-hidden="true">
          !
        </div>
        <h3 id="unanswered-submit-title" className="unanswered-submit-alert__title">
          You haven&apos;t answered all the questions
        </h3>
        <p id="unanswered-submit-desc" className="unanswered-submit-alert__body">
          <strong>{unansweredCount}</strong> of <strong>{totalCount}</strong> question
          {totalCount === 1 ? "" : "s"} still blank
          {answeredCount > 0 ? ` (${answeredCount} answered)` : ""}. Questions on other
          pages count too — are you sure you want to submit?
        </p>
        <div className="unanswered-submit-alert__actions">
          <button type="button" className="button unanswered-submit-alert__no" onClick={onCancel}>
            No, go back
          </button>
          <button
            type="button"
            className="button unanswered-submit-alert__yes"
            onClick={onConfirm}
          >
            Yes, submit anyway
          </button>
        </div>
      </div>
    </div>
  );
}
