/**
 * Full-screen Jupyter Notebook assessment panel shown when routing_flag === "jupyter".
 * Guides the participant through: download template → solve locally → upload solved file.
 */
const API_BASE = import.meta.env.VITE_API_URL || "/api";

const StepCircle = ({ n }) => (
  <div
    style={{
      width: "28px",
      height: "28px",
      borderRadius: "50%",
      background: "var(--primary-color, #1a73e8)",
      color: "#fff",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontWeight: "bold",
      fontSize: "0.9rem",
    }}
  >
    {n}
  </div>
);

const StepCard = ({ children }) => (
  <div
    className="step-card"
    style={{
      background: "rgba(255,255,255,0.05)",
      border: "1px solid rgba(0,0,0,0.08)",
      borderRadius: "12px",
      padding: "24px",
      display: "flex",
      flexDirection: "column",
      gap: "12px",
    }}
  >
    {children}
  </div>
);

export default function JupyterWorkspacePanel({
  assessmentId,
  notebookFile,
  notebookUploadEnabled,
  notebookResult,
  loading,
  autoSubmitting,
  result,
  timerState,
  onFileChange,
  onSubmit,
}) {
  const templateUrl = `${API_BASE}/assessment/${encodeURIComponent(assessmentId)}/template`;

  return (
    <div className="jupyter-workspace-panel" style={{ padding: "10px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px" }}>
        <span
          className="pill"
          style={{ background: "var(--brand-orange)", color: "#fff", fontWeight: "bold" }}
        >
          Jupyter Sandbox
        </span>
        <span className="muted">Assessment ID: {assessmentId}</span>
      </div>

      <h2 style={{ fontSize: "1.5rem", marginBottom: "8px", fontWeight: "700" }}>
        Jupyter Notebook Assessment
      </h2>
      <p className="muted" style={{ marginBottom: "24px", lineHeight: "1.6" }}>
        This assessment is conducted in a Jupyter Notebook environment. Download the template
        below, open and solve it in your local Jupyter workspace, then upload the solved file here.
      </p>

      <div
        className="steps-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: "20px",
          marginBottom: "32px",
        }}
      >
        {/* Step 1 — Download */}
        <StepCard>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <StepCircle n={1} />
            <h3 style={{ fontSize: "1.1rem", margin: 0, fontWeight: "600" }}>
              Download Template
            </h3>
          </div>
          <p className="muted small-print" style={{ margin: 0, lineHeight: "1.5" }}>
            Obtain the official notebook template containing all questions and guidelines.
          </p>
          <a
            href={templateUrl}
            download={`assessment_${assessmentId}.ipynb`}
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
              transition: "background 0.2s",
            }}
          >
            <svg
              width="16"
              height="16"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              viewBox="0 0 24 24"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
            </svg>
            Download .ipynb Template
          </a>
        </StepCard>

        {/* Step 2 — Upload */}
        <StepCard>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <StepCircle n={2} />
            <h3 style={{ fontSize: "1.1rem", margin: 0, fontWeight: "600" }}>
              Upload Solved Notebook
            </h3>
          </div>
          <p className="muted small-print" style={{ margin: 0, lineHeight: "1.5" }}>
            Upload your completed Jupyter Notebook file (.ipynb) containing your solutions.
          </p>

          <div
            className="file-upload-zone"
            style={{
              border: "2px dashed var(--border, #ccc)",
              borderRadius: "8px",
              padding: "16px",
              textAlign: "center",
              marginTop: "auto",
              background: "rgba(0,0,0,0.02)",
              cursor: "pointer",
              transition: "border-color 0.2s, background-color 0.2s",
            }}
          >
            <input
              type="file"
              accept=".ipynb"
              id="notebook-file-input"
              style={{ display: "none" }}
              disabled={!notebookUploadEnabled}
              onChange={(e) => {
                if (e.target.files?.[0]) onFileChange(e.target.files[0]);
              }}
            />
            <label
              htmlFor="notebook-file-input"
              style={{
                cursor: notebookUploadEnabled ? "pointer" : "not-allowed",
                display: "block",
              }}
            >
              <svg
                width="24"
                height="24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                viewBox="0 0 24 24"
                style={{ margin: "0 auto 8px auto", opacity: 0.7 }}
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" />
              </svg>
              {notebookFile ? (
                <div className="file-info" style={{ wordBreak: "break-all" }}>
                  <strong style={{ fontSize: "0.95rem" }}>{notebookFile.name}</strong>
                  <p className="muted small-print" style={{ margin: "4px 0 0 0" }}>
                    {(notebookFile.size / 1024).toFixed(1)} KB
                  </p>
                </div>
              ) : (
                <span className="muted" style={{ fontSize: "0.9rem" }}>
                  Select solved notebook file
                </span>
              )}
            </label>
          </div>
        </StepCard>
      </div>

      <div style={{ marginTop: "16px" }}>
        <button
          type="button"
          className="primary"
          onClick={onSubmit}
          disabled={
            loading ||
            autoSubmitting ||
            !!result ||
            (timerState.isTimed &&
              !timerState.inMainWindow &&
              !(timerState.inNotebookGrace && notebookFile))
          }
          style={{
            width: "100%",
            padding: "12px 24px",
            fontSize: "1rem",
            fontWeight: "600",
            borderRadius: "8px",
          }}
        >
          {result ? "Submitted" : loading ? "Submitting…" : "Submit notebook"}
        </button>
      </div>
    </div>
  );
}
