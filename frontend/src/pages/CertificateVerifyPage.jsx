import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiFetch } from "../api";

function formatDate(iso, issueYear, issueMonth) {
  if (iso) {
    const d = new Date(iso);
    if (!Number.isNaN(d.getTime())) {
      return d.toLocaleDateString(undefined, {
        year: "numeric",
        month: "long",
        day: "numeric",
      });
    }
  }
  if (issueYear && issueMonth) {
    return new Date(issueYear, issueMonth - 1, 1).toLocaleDateString(undefined, {
      year: "numeric",
      month: "long",
    });
  }
  return "—";
}

function formatLevel(level) {
  if (!level) return "—";
  const s = String(level).trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export default function CertificateVerifyPage() {
  const { certificateId } = useParams();
  const [record, setRecord] = useState(null);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const branding = await apiFetch("/public/certificate/settings");
        if (!cancelled) setSettings(branding);
      } catch {
        if (!cancelled) setSettings(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await apiFetch(`/public/certificate/${certificateId}/verify`);
        if (!cancelled) setRecord(data);
      } catch (e) {
        if (!cancelled) {
          setRecord(null);
          setError(e.message || "Certificate not found.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [certificateId]);

  const orgName =
    record?.organization_name || settings?.organization_name || "Certificate verification";
  const intro =
    record?.verification_intro ||
    settings?.verification_intro ||
    "This page confirms that a certificate was issued by our platform. Share this URL or scan the QR code to prove authenticity.";
  const imageUrl = record?.image_url || `/api/public/certificate/${certificateId}/image`;
  const qrUrl = `/api/public/certificate/${certificateId}/qr`;

  return (
    <div className="page cert-verify-page">
      <header className="cert-verify-header">
        <Link to="/" className="cert-verify-brand">
          {orgName}
        </Link>
        <p className="page-eyebrow">Credential verification</p>
        <h1>Verify a certificate</h1>
        <p className="muted cert-verify-lead">{intro}</p>
      </header>

      {loading && <p className="muted">Verifying credential…</p>}

      {error && (
        <div className="card cert-verify-error" role="alert">
          <h2>Certificate not found</h2>
          <p>{error}</p>
          <p className="muted small-print">
            Check the credential ID in the link or ask the certificate holder for an updated
            verification URL.
          </p>
        </div>
      )}

      {record && !loading && (
        <article className="cert-verify-card card">
          <div className="cert-verify-status" role="status">
            <span className="cert-verify-badge" aria-hidden>
              ✓
            </span>
            <div>
              <h2>Verified credential</h2>
              <p className="muted small-print">
                Issued by <strong>{record.organization_name}</strong>
              </p>
            </div>
          </div>

          {record.verification_description && (
            <p className="cert-verify-summary">{record.verification_description}</p>
          )}

          <div className="cert-verify-layout">
            <div className="cert-verify-details">
              <dl className="cert-verify-facts">
                <div>
                  <dt>Recipient</dt>
                  <dd>{record.display_name}</dd>
                </div>
                <div>
                  <dt>Certificate</dt>
                  <dd>{record.title}</dd>
                </div>
                <div>
                  <dt>Level</dt>
                  <dd>{formatLevel(record.level)}</dd>
                </div>
                <div>
                  <dt>Language</dt>
                  <dd>{record.language_label}</dd>
                </div>
                <div>
                  <dt>Issue date</dt>
                  <dd>{formatDate(record.issued_at, record.issue_year, record.issue_month)}</dd>
                </div>
                {record.score_percent != null && (
                  <div>
                    <dt>Assessment score</dt>
                    <dd>{record.score_percent}%</dd>
                  </div>
                )}
                <div>
                  <dt>Credential ID</dt>
                  <dd>
                    <code>#{record.certificate_id}</code>
                  </dd>
                </div>
              </dl>

              {record.skills?.length > 0 && (
                <div className="cert-verify-skills">
                  <h3>Skills demonstrated</h3>
                  <ul>
                    {record.skills.map((skill) => (
                      <li key={skill}>{skill}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <div className="cert-verify-visual">
              <img
                src={imageUrl}
                alt={`Certificate for ${record.display_name}`}
                className="cert-verify-image"
              />
              <div className="cert-verify-qr-block">
                <img src={qrUrl} alt="QR code for verification page" className="cert-verify-qr" />
                <p className="muted small-print">Scan to open this verification page</p>
              </div>
            </div>
          </div>

          <footer className="cert-verify-footer muted small-print">
            <p>
              Only certificates issued through {record.organization_name} appear here. Employers can
              bookmark this page to validate future credentials.
            </p>
          </footer>
        </article>
      )}
    </div>
  );
}
