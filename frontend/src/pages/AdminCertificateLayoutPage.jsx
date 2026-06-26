import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, apiFetchBlob } from "../api";

const FIELD_KEYS = ["display_name", "issue_date", "signature"];
const FIELD_LABELS = {
  display_name: "Name",
  issue_date: "Date",
  signature: "Signature",
};

const DEFAULT_TEXT_FIELD = {
  x_ratio: 0.5,
  y_ratio: 0.5,
  anchor: "center",
  size: 48,
  color: "#1a1a1a",
};

const DEFAULT_DATE_FIELD = {
  x_ratio: 0.25,
  y_ratio: 0.86,
  anchor: "center",
  size: 14,
  color: "#333333",
};

const DEFAULT_SIGNATURE_FIELD = {
  x_ratio: 0.75,
  y_ratio: 0.85,
  anchor: "center",
  max_width_ratio: 0.14,
  max_height_ratio: 0.06,
};

function emptyLayout() {
  return {
    display_name: { ...DEFAULT_TEXT_FIELD },
    issue_date: { ...DEFAULT_DATE_FIELD },
    signature: { ...DEFAULT_SIGNATURE_FIELD },
  };
}

function layoutFromApi(raw) {
  if (!raw) return emptyLayout();
  return {
    display_name: { ...DEFAULT_TEXT_FIELD, ...(raw.display_name || {}) },
    issue_date: { ...DEFAULT_DATE_FIELD, ...(raw.issue_date || {}) },
    signature: { ...DEFAULT_SIGNATURE_FIELD, ...(raw.signature || {}) },
  };
}

function Marker({ fieldKey, field, color, label }) {
  if (field?.x_ratio == null || field?.y_ratio == null) return null;
  const left = `${field.x_ratio * 100}%`;
  const top = `${field.y_ratio * 100}%`;
  return (
    <div
      className={`cert-layout-marker cert-layout-marker--${fieldKey}`}
      style={{ left, top, borderColor: color }}
      title={`${label}: ${Math.round(field.x_ratio * 1000) / 10}%, ${Math.round(field.y_ratio * 1000) / 10}%`}
    >
      <span className="cert-layout-marker-label">{label}</span>
    </div>
  );
}

function CertificatePreviewLightbox({ open, title, previewUrl, onClose }) {
  useEffect(() => {
    if (!open) return undefined;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  if (!open || !previewUrl) return null;

  return (
    <div
      className="emp-report-chart-lightbox cert-layout-preview-lightbox no-print"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <button
        type="button"
        className="emp-report-chart-lightbox-backdrop"
        onClick={onClose}
        aria-label="Close preview"
      />
      <div
        className="emp-report-chart-lightbox-panel emp-report-chart-lightbox-panel--certificate"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="emp-report-chart-lightbox-header">
          <h3>{title}</h3>
          <button
            type="button"
            className="emp-report-chart-lightbox-close"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </header>
        <div className="emp-report-chart-lightbox-body cert-layout-lightbox-body">
          <img
            src={previewUrl}
            alt="Certificate preview"
            className="cert-layout-lightbox-img"
          />
        </div>
      </div>
    </div>
  );
}

export default function AdminCertificateLayoutPage() {
  const [templates, setTemplates] = useState([]);
  const [selected, setSelected] = useState("");
  const [activeField, setActiveField] = useState("display_name");
  const [layout, setLayout] = useState(emptyLayout());
  const [sampleName, setSampleName] = useState("Sample Name");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [previewLightboxOpen, setPreviewLightboxOpen] = useState(false);
  const [backgroundBlobUrl, setBackgroundBlobUrl] = useState(null);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);
  const [issuerOrg, setIssuerOrg] = useState("");
  const [issuerIntro, setIssuerIntro] = useState("");
  const [issuerLoading, setIssuerLoading] = useState(true);
  const [issuerSaving, setIssuerSaving] = useState(false);
  const [issuerMessage, setIssuerMessage] = useState(null);
  const imgWrapRef = useRef(null);

  const selectedMeta = useMemo(
    () => templates.find((t) => t.filename === selected) || null,
    [templates, selected]
  );

  const backgroundUrl = backgroundBlobUrl;

  const loadTemplates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch("/admin/certificate/templates", { authRole: "admin" });
      const list = data.templates ?? [];
      setTemplates(list);
      setSelected((prev) => {
        if (prev && list.some((t) => t.filename === prev)) return prev;
        return list[0]?.filename ?? "";
      });
    } catch (e) {
      setError(e.message);
      setTemplates([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTemplates();
  }, [loadTemplates]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setIssuerLoading(true);
      try {
        const data = await apiFetch("/admin/certificate/issuer-settings", { authRole: "admin" });
        if (!cancelled) {
          setIssuerOrg(data.organization_name || "");
          setIssuerIntro(data.verification_intro || "");
        }
      } catch (e) {
        if (!cancelled) setError(e.message);
      } finally {
        if (!cancelled) setIssuerLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSaveIssuerSettings() {
    setIssuerSaving(true);
    setIssuerMessage(null);
    setError(null);
    try {
      const data = await apiFetch("/admin/certificate/issuer-settings", {
        method: "PUT",
        authRole: "admin",
        body: JSON.stringify({
          organization_name: issuerOrg.trim(),
          verification_intro: issuerIntro.trim(),
        }),
      });
      setIssuerOrg(data.organization_name || "");
      setIssuerIntro(data.verification_intro || "");
      setIssuerMessage("Issuing organization saved. LinkedIn and verification pages will use this name.");
    } catch (e) {
      setError(e.message);
    } finally {
      setIssuerSaving(false);
    }
  }

  useEffect(() => {
    if (!selectedMeta) {
      setLayout(emptyLayout());
      return;
    }
    setLayout(layoutFromApi(selectedMeta.layout));
    setMessage(null);
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setPreviewLightboxOpen(false);
  }, [selectedMeta]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  useEffect(() => {
    let cancelled = false;
    let objectUrl = null;
    async function loadBackground() {
      if (!selected) {
        setBackgroundBlobUrl(null);
        return;
      }
      try {
        const { blob } = await apiFetchBlob(
          `/admin/certificate/templates/${encodeURIComponent(selected)}/background`,
          { authRole: "admin" }
        );
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setBackgroundBlobUrl(objectUrl);
      } catch (e) {
        if (!cancelled) setError(e.message);
      }
    }
    void loadBackground();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [selected]);

  function updateField(fieldKey, patch) {
    setLayout((prev) => ({
      ...prev,
      [fieldKey]: { ...prev[fieldKey], ...patch },
    }));
  }

  function handleCanvasClick(event) {
    const wrap = imgWrapRef.current;
    const img = wrap?.querySelector("img");
    if (!wrap || !img) return;
    const rect = img.getBoundingClientRect();
    const x_ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    const y_ratio = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
    updateField(activeField, {
      x_ratio: Math.round(x_ratio * 10000) / 10000,
      y_ratio: Math.round(y_ratio * 10000) / 10000,
    });
  }

  async function handleSave() {
    if (!selected) return;
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      await apiFetch(
        `/admin/certificate/templates/${encodeURIComponent(selected)}/layout`,
        {
          method: "PUT",
          authRole: "admin",
          body: JSON.stringify(layout),
        }
      );
      setMessage("Layout saved to certificates/layout.json");
      await loadTemplates();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handlePreview() {
    if (!selected) return;
    setPreviewing(true);
    setError(null);
    try {
      const { blob } = await apiFetchBlob(
        `/admin/certificate/templates/${encodeURIComponent(selected)}/preview`,
        {
          method: "POST",
          authRole: "admin",
          body: JSON.stringify({
            display_name: sampleName.trim() || "Sample Name",
            layout,
          }),
        }
      );
      setPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return URL.createObjectURL(blob);
      });
      setPreviewLightboxOpen(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setPreviewing(false);
    }
  }

  const active = layout[activeField] || {};

  return (
    <div className="page page--wide cert-layout-page">
      <header className="header">
        <p className="page-eyebrow">Admin</p>
        <h1>Certificate layout</h1>
        <p className="muted hero-lead">
          Click the template to place the active field. Adjust font size and colors, preview,
          then save — coordinates are stored in <code>certificates/layout.json</code> per template
          filename. New JPGs in <code>certificates/</code> appear as <strong>Needs setup</strong> until
          calibrated.
        </p>
      </header>

      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {message && (
        <p className="muted" role="status">
          {message}
        </p>
      )}

      <section className="card cert-layout-issuer">
        <h2 className="cert-layout-sidebar-title">Issuing organization</h2>
        <p className="muted small-print cert-layout-issuer-lead">
          Used as the <strong>Issuing organization</strong> when learners share on LinkedIn and on
          the public certificate verification page.
        </p>
        {issuerLoading ? (
          <p className="muted">Loading issuer settings…</p>
        ) : (
          <>
            <label className="review-field">
              <span className="review-field-label">Organization name</span>
              <input
                type="text"
                className="review-field-input"
                value={issuerOrg}
                onChange={(e) => setIssuerOrg(e.target.value)}
                maxLength={256}
                placeholder="Wekan Enterprise Solutions"
              />
            </label>
            <label className="review-field">
              <span className="review-field-label">Verification page intro</span>
              <textarea
                className="review-field-input cert-layout-issuer-intro"
                value={issuerIntro}
                onChange={(e) => setIssuerIntro(e.target.value)}
                maxLength={2000}
                rows={3}
              />
            </label>
            <div className="cert-layout-editor-actions">
              <button
                type="button"
                className="primary"
                onClick={handleSaveIssuerSettings}
                disabled={issuerSaving || !issuerOrg.trim() || !issuerIntro.trim()}
              >
                {issuerSaving ? "Saving…" : "Save organization"}
              </button>
            </div>
            {issuerMessage && (
              <p className="muted small-print" role="status">
                {issuerMessage}
              </p>
            )}
          </>
        )}
      </section>

      {loading ? (
        <p className="muted">Loading templates…</p>
      ) : templates.length === 0 ? (
        <p className="muted">No certificate templates found in certificates/</p>
      ) : (
        <div className="cert-layout-grid">
          <aside className="card cert-layout-sidebar">
            <h2 className="cert-layout-sidebar-title">Templates</h2>
            <ul className="cert-layout-template-list">
              {templates.map((t) => (
                <li key={t.filename}>
                  <button
                    type="button"
                    className={`cert-layout-template-btn${selected === t.filename ? " cert-layout-template-btn--active" : ""}`}
                    onClick={() => setSelected(t.filename)}
                  >
                    <span className="cert-layout-template-name">{t.filename}</span>
                    <span
                      className={`cert-layout-badge${t.calibrated ? " cert-layout-badge--ok" : " cert-layout-badge--warn"}`}
                    >
                      {t.calibrated ? "Configured" : "Needs setup"}
                    </span>
                    {t.levels?.length > 0 && (
                      <span className="muted small-print">
                        Levels: {t.levels.join(", ")}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          <section className="card cert-layout-canvas-card">
            <div className="cert-layout-field-tabs" role="tablist">
              {FIELD_KEYS.map((key) => (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={activeField === key}
                  className={`cert-layout-field-tab${activeField === key ? " cert-layout-field-tab--active" : ""}`}
                  onClick={() => setActiveField(key)}
                >
                  {FIELD_LABELS[key]}
                </button>
              ))}
            </div>
            <p className="muted small-print cert-layout-click-hint">
              Active: <strong>{FIELD_LABELS[activeField]}</strong> — click on the image to set
              position ({active.x_ratio != null ? `${Math.round(active.x_ratio * 100)}%` : "—"},{" "}
              {active.y_ratio != null ? `${Math.round(active.y_ratio * 100)}%` : "—"}).
            </p>
            <div
              ref={imgWrapRef}
              className="cert-layout-canvas-wrap"
              onClick={handleCanvasClick}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") e.preventDefault();
              }}
              aria-label="Certificate template — click to place active field"
            >
              {backgroundUrl && (
                <img
                  src={backgroundUrl}
                  alt={`Template ${selected}`}
                  className="cert-layout-canvas-img"
                  draggable={false}
                />
              )}
              <Marker
                fieldKey="display_name"
                field={layout.display_name}
                color="#2563eb"
                label="Name"
              />
              <Marker
                fieldKey="issue_date"
                field={layout.issue_date}
                color="#059669"
                label="Date"
              />
              <Marker
                fieldKey="signature"
                field={layout.signature}
                color="#d97706"
                label="Sig"
              />
            </div>
          </section>

          <aside className="card cert-layout-editor">
            <h2 className="cert-layout-sidebar-title">Field settings</h2>
            {activeField !== "signature" ? (
              <>
                <label className="review-field">
                  <span className="review-field-label">Font size (px)</span>
                  <input
                    type="number"
                    min={8}
                    max={120}
                    className="review-field-input"
                    value={active.size ?? 16}
                    onChange={(e) =>
                      updateField(activeField, { size: Number(e.target.value) || 16 })
                    }
                  />
                </label>
                <label className="review-field">
                  <span className="review-field-label">Color</span>
                  <input
                    type="color"
                    value={active.color || "#1a1a1a"}
                    onChange={(e) => updateField(activeField, { color: e.target.value })}
                  />
                </label>
                <label className="review-field">
                  <span className="review-field-label">Anchor</span>
                  <select
                    className="review-field-input"
                    value={active.anchor || "center"}
                    onChange={(e) => updateField(activeField, { anchor: e.target.value })}
                  >
                    <option value="center">center</option>
                    <option value="left">left</option>
                    <option value="right">right</option>
                    <option value="baseline">baseline</option>
                  </select>
                </label>
              </>
            ) : (
              <>
                <label className="review-field">
                  <span className="review-field-label">Max width (% of canvas)</span>
                  <input
                    type="number"
                    min={5}
                    max={50}
                    step={1}
                    className="review-field-input"
                    value={Math.round((active.max_width_ratio ?? 0.14) * 100)}
                    onChange={(e) =>
                      updateField("signature", {
                        max_width_ratio: (Number(e.target.value) || 14) / 100,
                      })
                    }
                  />
                </label>
                <label className="review-field">
                  <span className="review-field-label">Max height (% of canvas)</span>
                  <input
                    type="number"
                    min={2}
                    max={25}
                    step={1}
                    className="review-field-input"
                    value={Math.round((active.max_height_ratio ?? 0.06) * 100)}
                    onChange={(e) =>
                      updateField("signature", {
                        max_height_ratio: (Number(e.target.value) || 6) / 100,
                      })
                    }
                  />
                </label>
              </>
            )}
            <label className="review-field">
              <span className="review-field-label">Preview sample name</span>
              <input
                type="text"
                className="review-field-input"
                value={sampleName}
                onChange={(e) => setSampleName(e.target.value)}
              />
            </label>
            <div className="cert-layout-editor-actions">
              <button
                type="button"
                className="secondary"
                onClick={handlePreview}
                disabled={previewing || !selected}
              >
                {previewing ? "Rendering…" : "Preview"}
              </button>
              {previewUrl && !previewLightboxOpen && (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setPreviewLightboxOpen(true)}
                >
                  View preview
                </button>
              )}
              <button
                type="button"
                className="primary"
                onClick={handleSave}
                disabled={saving || !selected}
              >
                {saving ? "Saving…" : "Save layout"}
              </button>
            </div>
            {previewUrl && (
              <p className="muted small-print cert-layout-preview-hint">
                Last preview ready — use <strong>Preview</strong> to refresh or{" "}
                <strong>View preview</strong> to open full screen.
              </p>
            )}
          </aside>
        </div>
      )}

      <p className="muted footer-hint">
        <Link to="/admin">← Back to generate</Link>
      </p>

      <CertificatePreviewLightbox
        open={previewLightboxOpen}
        title={selected ? `Preview — ${selected}` : "Certificate preview"}
        previewUrl={previewUrl}
        onClose={() => setPreviewLightboxOpen(false)}
      />
    </div>
  );
}
