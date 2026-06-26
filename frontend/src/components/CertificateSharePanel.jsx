import { useState } from "react";

function formatIssueDate(year, month) {
  if (!year || !month) return null;
  const d = new Date(year, month - 1, 1);
  return d.toLocaleString(undefined, { month: "long", year: "numeric" });
}

export default function CertificateSharePanel({ meta, compact = false }) {
  const [message, setMessage] = useState(null);

  if (!meta) return null;

  const issueLabel = formatIssueDate(meta.issue_year, meta.issue_month);
  const skills = meta.skills || [];

  const copyText = async (text, successMsg) => {
    try {
      await navigator.clipboard.writeText(text);
      setMessage(successMsg);
    } catch {
      setMessage("Could not copy to clipboard.");
    }
  };

  return (
    <div className={`certificate-share-panel${compact ? " certificate-share-panel--compact" : ""}`}>
      <div className="certificate-share-primary">
        <p className="certificate-share-lead">Share your achievement</p>
        {meta.organization_name && (
          <p className="muted small-print certificate-share-org">
            Issuing organization on LinkedIn: <strong>{meta.organization_name}</strong>
          </p>
        )}
        {issueLabel && (
          <p className="muted small-print certificate-share-hint">
            Issue date prefilled as <strong>{issueLabel}</strong>. Leave expiration blank on LinkedIn.
          </p>
        )}

        <div className="certificate-share-actions">
          <a
            href={meta.linkedin_url}
            className="button-link primary certificate-share-linkedin"
            target="_blank"
            rel="noopener noreferrer"
          >
            Add to LinkedIn profile
          </a>
          <button
            type="button"
            className="secondary"
            onClick={() =>
              copyText(meta.verification_url || meta.share_url, "Verification link copied.")
            }
          >
            Copy verification link
          </button>
          {meta.image_url && (
            <a
              href={meta.image_url}
              className="secondary"
              target="_blank"
              rel="noopener noreferrer"
              download
            >
              Download image
            </a>
          )}
        </div>
      </div>

      {skills.length > 0 && (
        <div className="certificate-share-card">
          <p className="certificate-share-card-title">Suggested LinkedIn skills</p>
          <ul className="certificate-share-skill-tags">
            {skills.map((skill) => (
              <li key={skill}>{skill}</li>
            ))}
          </ul>
          <button
            type="button"
            className="link-button"
            onClick={() => copyText(skills.join(", "), "Skills list copied.")}
          >
            Copy all skills
          </button>
        </div>
      )}

      {(meta.media_title || meta.media_description) && (
        <div className="certificate-share-card">
          <p className="certificate-share-card-title">LinkedIn media text</p>
          {meta.media_title && (
            <p className="certificate-share-media-row">
              <span className="certificate-share-media-key">Title</span>
              {meta.media_title}
            </p>
          )}
          {meta.media_description && (
            <p className="certificate-share-media-row muted small-print">
              <span className="certificate-share-media-key">Description</span>
              {meta.media_description}
            </p>
          )}
          <button
            type="button"
            className="link-button"
            onClick={() =>
              copyText(
                `Title: ${meta.media_title || ""}\n\nDescription: ${meta.media_description || ""}`,
                "Media title & description copied."
              )
            }
          >
            Copy media text
          </button>
          {meta.image_url && (
            <p className="muted small-print certificate-share-media-tip">
              Upload the certificate image when LinkedIn asks for media.
            </p>
          )}
        </div>
      )}

      {message && (
        <p className="certificate-share-toast muted small-print" role="status">
          {message}
        </p>
      )}
    </div>
  );
}
