import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";

const PROVIDER_LABELS = {
  groq: "Groq",
  openai: "OpenAI",
  claude: "Claude",
  gemini: "Gemini",
};

function providerLabel(name) {
  return PROVIDER_LABELS[name] || name;
}

export default function AdminAgentsPage() {
  const [agents, setAgents] = useState([]);
  const [supportedProviders, setSupportedProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [agentName, setAgentName] = useState("groq");
  const [apiKey, setApiKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formMessage, setFormMessage] = useState(null);
  const [formError, setFormError] = useState(null);

  const [selectingId, setSelectingId] = useState(null);
  const [listActionError, setListActionError] = useState(null);

  const dialogRef = useRef(null);
  const [editAgent, setEditAgent] = useState(null);
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState(null);

  const existingNames = new Set(agents.map((a) => a.agent_name));

  const availableToAdd = supportedProviders.filter((p) => !existingNames.has(p));

  const loadAll = useCallback(async () => {
    setLoadError(null);
    setLoading(true);
    try {
      const res = await apiFetch("/admin/agents");
      setAgents(res.agents ?? []);
      setSupportedProviders(res.supported_providers ?? []);
    } catch (e) {
      setLoadError(e.message);
      setAgents([]);
      setSupportedProviders([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    const d = dialogRef.current;
    if (!d) return;
    if (editAgent) d.showModal();
    else d.close();
  }, [editAgent]);

  const openEdit = (agent) => {
    setEditError(null);
    setEditAgent({
      id: agent.id,
      agent_name: agent.agent_name,
      status: agent.status,
      is_selected: agent.is_selected,
      apiKey: "",
    });
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    setFormError(null);
    setFormMessage(null);
    const key = apiKey.trim();
    if (!key) {
      setFormError("API key is required.");
      return;
    }
    setSubmitting(true);
    try {
      await apiFetch("/admin/agents", {
        method: "POST",
        authRole: "admin",
        body: JSON.stringify({ agent_name: agentName, api_key: key }),
      });
      setApiKey("");
      setFormMessage(`${providerLabel(agentName)} agent added.`);
      await loadAll();
    } catch (err) {
      setFormError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleSelect = async (agent) => {
    setListActionError(null);
    setSelectingId(agent.id);
    try {
      await apiFetch(`/admin/agents/${agent.id}/select`, {
        method: "POST",
        authRole: "admin",
      });
      await loadAll();
    } catch (err) {
      setListActionError(err.message);
    } finally {
      setSelectingId(null);
    }
  };

  const saveEdit = async (e) => {
    e.preventDefault();
    if (!editAgent) return;
    setEditError(null);
    const body = {};
    if (editAgent.apiKey.trim()) {
      body.api_key = editAgent.apiKey.trim();
    }
    if (editAgent.status !== undefined) {
      body.status = editAgent.status;
    }
    if (!body.api_key && body.status === undefined) {
      setEditError("Provide a new API key and/or change status.");
      return;
    }
    setEditSaving(true);
    try {
      await apiFetch(`/admin/agents/${editAgent.id}`, {
        method: "PUT",
        authRole: "admin",
        body: JSON.stringify(body),
      });
      setEditAgent(null);
      await loadAll();
    } catch (err) {
      setEditError(err.message);
    } finally {
      setEditSaving(false);
    }
  };

  return (
    <div className="page page--wide">
      <header className="header">
        <p className="page-eyebrow">Admin · Agents</p>
        <h1>LLM providers</h1>
        <p className="muted">
          Configure Groq, Claude, OpenAI, or Gemini. Select one active agent — all question generation
          and grading uses that provider and its API key. Changes apply immediately without redeploy.
        </p>
      </header>

      {loadError && (
        <div className="error" role="alert">
          {loadError}
        </div>
      )}

      {loading && <p className="muted">Loading agents…</p>}

      {!loading && !loadError && (
        <>
          <div className="grid catalog-form-row">
            <section className="card">
              <h2>Add agent</h2>
              <p className="muted small-print">
                Each provider can only be added once. After adding, use <strong>Select</strong> in the
                table to make it the active LLM for the platform.
              </p>
              {availableToAdd.length === 0 ? (
                <p className="muted">All supported providers are already configured.</p>
              ) : (
                <form onSubmit={handleAdd} className="stack">
                  <label>
                    Provider
                    <select
                      value={agentName}
                      onChange={(e) => setAgentName(e.target.value)}
                    >
                      {availableToAdd.map((p) => (
                        <option key={p} value={p}>
                          {providerLabel(p)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    API key
                    <input
                      type="password"
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                      placeholder="Paste provider API key"
                      autoComplete="off"
                    />
                  </label>
                  <button type="submit" className="primary" disabled={submitting}>
                    {submitting ? "Saving…" : "Add agent"}
                  </button>
                </form>
              )}
              {formMessage && <p className="success">{formMessage}</p>}
              {formError && (
                <div className="error" role="alert">
                  {formError}
                </div>
              )}
            </section>

            <section className="card">
              <h2>How it works</h2>
              <ul className="muted small-print" style={{ marginTop: 0, paddingLeft: "1.25rem" }}>
                <li>
                  <strong>Active</strong> agents can be selected; <strong>Inactive</strong> agents are
                  disabled.
                </li>
                <li>
                  Exactly one agent is <strong>selected</strong> at a time — it handles all LLM
                  requests.
                </li>
                <li>
                  API keys are stored in PostgreSQL and masked in the UI after saving.
                </li>
                <li>
                  On first startup, a Groq agent is seeded from <code>GROQ_API_KEY</code> in{" "}
                  <code>.env</code> if the table is empty.
                </li>
              </ul>
            </section>
          </div>

          <section className="card catalog-topics-row">
            <h2>Configured agents ({agents.length})</h2>

            {listActionError && (
              <div className="error" role="alert" style={{ marginTop: "0.75rem" }}>
                {listActionError}
              </div>
            )}

            {agents.length === 0 ? (
              <p className="muted">No agents yet. Add one above or set GROQ_API_KEY in .env and restart.</p>
            ) : (
              <div className="table-wrap table-wrap--nested">
                <table className="data-table data-table--nested">
                  <thead>
                    <tr>
                      <th>Provider</th>
                      <th>Status</th>
                      <th>API key</th>
                      <th>Selected</th>
                      <th>Updated</th>
                      <th className="cell-nowrap">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agents.map((a) => (
                      <tr key={a.id}>
                        <td>
                          <strong>{providerLabel(a.agent_name)}</strong>
                          <br />
                          <code className="cell-id">{a.agent_name}</code>
                        </td>
                        <td>{a.status}</td>
                        <td>
                          <code>{a.api_key_configured ? a.api_key_masked : "—"}</code>
                        </td>
                        <td>{a.is_selected ? "Yes" : "—"}</td>
                        <td className="cell-nowrap small-print">{a.updated_at?.slice(0, 19)}</td>
                        <td className="cell-actions">
                          <div className="cell-actions-btns">
                            {!a.is_selected && a.status === "Active" && (
                              <button
                                type="button"
                                className="primary btn-table-primary"
                                onClick={() => void handleSelect(a)}
                                disabled={selectingId === a.id}
                              >
                                {selectingId === a.id ? "…" : "Select"}
                              </button>
                            )}
                            <button
                              type="button"
                              className="btn-table-secondary"
                              onClick={() => openEdit(a)}
                              disabled={!!editAgent || editSaving}
                            >
                              Edit
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <dialog
            ref={dialogRef}
            className="dialog-catalog"
            onClose={() => {
              setEditAgent(null);
              setEditError(null);
            }}
          >
            {editAgent && (
              <form onSubmit={saveEdit} className="dialog-catalog-form">
                <div className="dialog-catalog__body stack">
                  <h3>Edit {providerLabel(editAgent.agent_name)}</h3>
                  <label>
                    Status
                    <select
                      value={editAgent.status}
                      onChange={(e) =>
                        setEditAgent((p) => (p ? { ...p, status: e.target.value } : p))
                      }
                      disabled={editAgent.is_selected && editAgent.status === "Active"}
                    >
                      <option value="Active">Active</option>
                      <option value="Inactive">Inactive</option>
                    </select>
                    {editAgent.is_selected && (
                      <span className="lang-combo-hint">
                        Deactivate the selected agent by selecting another provider first.
                      </span>
                    )}
                  </label>
                  <label>
                    New API key (optional)
                    <input
                      type="password"
                      value={editAgent.apiKey}
                      onChange={(e) =>
                        setEditAgent((p) => (p ? { ...p, apiKey: e.target.value } : p))
                      }
                      placeholder="Leave blank to keep current key"
                      autoComplete="off"
                    />
                  </label>
                  {editError && (
                    <div className="error" role="alert">
                      {editError}
                    </div>
                  )}
                </div>
                <div className="dialog-catalog__actions">
                  <button
                    type="button"
                    className="btn-table-secondary"
                    onClick={() => {
                      if (dialogRef.current) dialogRef.current.close();
                    }}
                    disabled={editSaving}
                  >
                    Cancel
                  </button>
                  <button type="submit" className="primary" disabled={editSaving}>
                    {editSaving ? "Saving…" : "Save changes"}
                  </button>
                </div>
              </form>
            )}
          </dialog>
        </>
      )}

      <p className="muted footer-hint">
        <Link to="/admin">Generate</Link>
        {" · "}
        <Link to="/admin/catalog">Catalog</Link>
        {" · "}
        <Link to="/admin/assessments">Assessments</Link>
      </p>
    </div>
  );
}
