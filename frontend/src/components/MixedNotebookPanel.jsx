/**
 * Compact notebook download + file-picker panel shown in mixed-routing assessments
 * (routing_flag === "mixed"). Rendered below the in-browser questions, before the
 * submit button.
 */
const API_BASE = import.meta.env.VITE_API_URL || "/api";

export default function MixedNotebookPanel({
  assessmentId,
  jupyterTopicNames,
  notebookFile,
  notebookResult,
  notebookUploadEnabled,
  onFileChange,
}) {
  const templateUrl = `${API_BASE}/assessment/${encodeURIComponent(assessmentId)}/template`;

  return (
    <div
      style={{
        marginTop: "32px",
        padding: "20px 24px",
        background: "var(--brand-orange-soft)",
        border: "1px solid var(--brand-orange-border)",
        borderRadius: "10px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
        <span
          className="pill"
          style={{
            background: "var(--brand-orange)",
            color: "#fff",
            fontWeight: "bold",
            fontSize: "0.78rem",
          }}
        >
          Jupyter Notebook
        </span>
        <span style={{ fontWeight: "600", fontSize: "0.95rem" }}>
          Upload your completed notebook
        </span>
      </div>

      <p className="muted small-print" style={{ margin: "0 0 14px 0" }}>
        Select your completed <code>.ipynb</code> file below — it is graded automatically on
        submit or during the grace period after time expires.
      </p>

      <div
        style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}
      >
        <input
          type="file"
          accept=".ipynb"
          id="mixed-notebook-input"
          style={{ display: "none" }}
          disabled={!notebookUploadEnabled}
          onChange={(e) => {
            if (e.target.files?.[0]) onFileChange(e.target.files[0]);
          }}
        />
        <label
          htmlFor="mixed-notebook-input"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "8px",
            padding: "9px 16px",
            borderRadius: "7px",
            cursor: notebookResult ? "not-allowed" : "pointer",
            background: "rgba(0,0,0,0.06)",
            fontWeight: "500",
            fontSize: "0.9rem",
            border: "1px solid rgba(0,0,0,0.12)",
            opacity: notebookResult ? 0.5 : 1,
          }}
        >
          <svg
            width="15"
            height="15"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            viewBox="0 0 24 24"
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12" />
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
  );
}

/**
 * Banner shown for topics that require a Jupyter Notebook submission (mixed routing).
 * Displayed above the question list.
 */
export function JupyterRequiredBanner({ assessmentId, jupyterTopicNames }) {
  const templateUrl = `${API_BASE}/assessment/${encodeURIComponent(assessmentId)}/template`;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: "16px",
        background: "var(--brand-orange-soft)",
        border: "1px solid var(--brand-orange-border)",
        borderRadius: "10px",
        padding: "16px 20px",
        marginBottom: "24px",
        flexWrap: "wrap",
      }}
    >
      <div style={{ flex: 1, minWidth: "200px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
          <span
            className="pill"
            style={{
              background: "var(--brand-orange)",
              color: "#fff",
              fontWeight: "bold",
              fontSize: "0.78rem",
            }}
          >
            Jupyter Required
          </span>
        </div>
        <p style={{ margin: "0 0 6px 0", fontWeight: "600", fontSize: "0.95rem" }}>
          The following topics must be completed in a Jupyter Notebook:
        </p>
        <ul style={{ margin: "0 0 0 16px", padding: 0, fontSize: "0.88rem" }}>
          {jupyterTopicNames.map((name) => (
            <li key={name} style={{ marginBottom: "2px" }}>
              {name}
            </li>
          ))}
        </ul>
      </div>
      <a
        href={templateUrl}
        download={`assessment_${assessmentId}.ipynb`}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "8px",
          padding: "10px 18px",
          borderRadius: "8px",
          background: "var(--brand-orange)",
          color: "#fff",
          fontWeight: "600",
          fontSize: "0.9rem",
          textDecoration: "none",
          whiteSpace: "nowrap",
          alignSelf: "center",
        }}
      >
        <svg
          width="15"
          height="15"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          viewBox="0 0 24 24"
        >
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
        </svg>
        Download .ipynb
      </a>
    </div>
  );
}
