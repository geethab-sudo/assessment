import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import SearchableLanguageSelect, { langLabel } from "../components/SearchableLanguageSelect.jsx";

const DOCS_PLACEHOLDER = `Optional. JSON array, e.g.:
[{"title": "Official tutorial", "url": "https://docs.python.org/3/tutorial/"}]

Each object needs "title" (1–512 chars). Optional: "url" and/or "path" (up to 2048 chars).`;

function parseRelatedDocuments(text) {
  const raw = (text || "").trim();
  if (!raw) return [];
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error("Related documents must be valid JSON array.");
  }
  if (!Array.isArray(parsed)) {
    throw new Error("Related documents must be a JSON array.");
  }
  const out = [];
  for (const item of parsed) {
    if (item == null || typeof item !== "object" || Array.isArray(item)) {
      throw new Error("Each related document must be a JSON object with at least a title.");
    }
    const title = String(item.title || "").trim();
    if (!title) {
      throw new Error('Each related document must include a non-empty "title".');
    }
    const o = { title };
    if (item.url != null && String(item.url).trim()) o.url = String(item.url).trim();
    if (item.path != null && String(item.path).trim()) o.path = String(item.path).trim();
    out.push(o);
  }
  return out;
}

export default function AdminCatalogPage() {
  const [languages, setLanguages] = useState([]);
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [langCode, setLangCode] = useState("");
  const [langName, setLangName] = useState("");
  const [langSubmitting, setLangSubmitting] = useState(false);
  const [langMessage, setLangMessage] = useState(null);
  const [langError, setLangError] = useState(null);

  const [topicLanguageId, setTopicLanguageId] = useState("");
  const [topicName, setTopicName] = useState("");
  const [topicDocsJson, setTopicDocsJson] = useState("");
  const [topicSubmitting, setTopicSubmitting] = useState(false);
  const [topicMessage, setTopicMessage] = useState(null);
  const [topicError, setTopicError] = useState(null);

  /** For the topics table: which language to list */
  const [listLanguageId, setListLanguageId] = useState("");
  const [topicNameFilter, setTopicNameFilter] = useState("");
  const [deletingTopicId, setDeletingTopicId] = useState(null);
  const [listActionError, setListActionError] = useState(null);

  const langDialogRef = useRef(null);
  const topicDialogRef = useRef(null);
  const [editLanguage, setEditLanguage] = useState(null);
  const [editLanguageSaving, setEditLanguageSaving] = useState(false);
  const [editLanguageError, setEditLanguageError] = useState(null);

  const [editTopic, setEditTopic] = useState(null);
  const [editTopicSaving, setEditTopicSaving] = useState(false);
  const [editTopicError, setEditTopicError] = useState(null);

  const languageById = useMemo(
    () => Object.fromEntries(languages.map((l) => [String(l.id), l])),
    [languages]
  );

  const topicsForSelectedLanguage = useMemo(() => {
    if (!listLanguageId) return [];
    const n = topicNameFilter.trim().toLowerCase();
    return topics
      .filter((t) => String(t.language_id) === String(listLanguageId))
      .filter(
        (t) =>
          !n ||
          String(t.name || "")
            .toLowerCase()
            .includes(n)
      );
  }, [topics, listLanguageId, topicNameFilter]);

  const selectedListLanguage = languageById[String(listLanguageId)];

  const loadAll = useCallback(async () => {
    setLoadError(null);
    setLoading(true);
    try {
      const [langRes, topicRes] = await Promise.all([
        apiFetch("/admin/languages"),
        apiFetch("/admin/topics"),
      ]);
      setLanguages(langRes.languages ?? []);
      setTopics(topicRes.topics ?? []);
    } catch (e) {
      setLoadError(e.message);
      setLanguages([]);
      setTopics([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const openEditLanguage = (l) => {
    setEditLanguageError(null);
    setEditLanguage({ id: l.id, code: l.code, name: l.name });
  };

  const openEditTopic = (t) => {
    setEditTopicError(null);
    setEditTopic({
      id: t.id,
      languageId: String(t.language_id),
      name: t.name,
      docsText: JSON.stringify(
        Array.isArray(t.related_documents) && t.related_documents.length
          ? t.related_documents
          : [],
        null,
        2
      ),
    });
  };

  useEffect(() => {
    const d = langDialogRef.current;
    if (!d) return;
    if (editLanguage) d.showModal();
    else d.close();
  }, [editLanguage]);

  useEffect(() => {
    const d = topicDialogRef.current;
    if (!d) return;
    if (editTopic) d.showModal();
    else d.close();
  }, [editTopic]);

  const saveLanguage = async (e) => {
    e.preventDefault();
    if (!editLanguage) return;
    setEditLanguageError(null);
    setEditLanguageSaving(true);
    try {
      await apiFetch(`/admin/languages/${editLanguage.id}`, {
        method: "PUT",
        authRole: "admin",
        body: JSON.stringify({
          code: editLanguage.code.trim(),
          name: editLanguage.name.trim(),
        }),
      });
      setEditLanguage(null);
      setLangMessage("Language updated.");
      await loadAll();
    } catch (err) {
      setEditLanguageError(err.message);
    } finally {
      setEditLanguageSaving(false);
    }
  };

  const saveTopic = async (e) => {
    e.preventDefault();
    if (!editTopic) return;
    setEditTopicError(null);
    const lid = Number.parseInt(String(editTopic.languageId), 10);
    if (!Number.isFinite(lid) || lid < 1) {
      setEditTopicError("Select a language.");
      return;
    }
    let related_documents;
    try {
      related_documents = parseRelatedDocuments(editTopic.docsText);
    } catch (err) {
      setEditTopicError(err.message);
      return;
    }
    setEditTopicSaving(true);
    try {
      await apiFetch(`/admin/topics/${editTopic.id}`, {
        method: "PUT",
        authRole: "admin",
        body: JSON.stringify({
          language_id: lid,
          name: editTopic.name.trim(),
          related_documents,
        }),
      });
      setEditTopic(null);
      setTopicMessage("Topic updated.");
      await loadAll();
    } catch (err) {
      setEditTopicError(err.message);
    } finally {
      setEditTopicSaving(false);
    }
  };

  const handleAddLanguage = async (e) => {
    e.preventDefault();
    setLangError(null);
    setLangMessage(null);
    const code = langCode.trim();
    const name = langName.trim();
    if (!code || !name) {
      setLangError("Code and name are required.");
      return;
    }
    setLangSubmitting(true);
    try {
      await apiFetch("/admin/languages", {
        method: "POST",
        authRole: "admin",
        body: JSON.stringify({ code, name }),
      });
      setLangCode("");
      setLangName("");
      setLangMessage("Language added.");
      await loadAll();
    } catch (err) {
      setLangError(err.message);
    } finally {
      setLangSubmitting(false);
    }
  };

  const handleDeleteTopic = async (t) => {
    if (
      !window.confirm(
        `Delete this topic?\n\n“${(t.name || "").slice(0, 200)}”\n\nThis cannot be undone.`
      )
    ) {
      return;
    }
    setListActionError(null);
    setDeletingTopicId(t.id);
    try {
      await apiFetch(`/admin/topics/${encodeURIComponent(t.id)}`, {
        method: "DELETE",
        authRole: "admin",
      });
      await loadAll();
    } catch (err) {
      setListActionError(err.message);
    } finally {
      setDeletingTopicId(null);
    }
  };

  const handleAddTopic = async (e) => {
    e.preventDefault();
    setTopicError(null);
    setTopicMessage(null);
    const lid = Number.parseInt(String(topicLanguageId), 10);
    if (!Number.isFinite(lid) || lid < 1) {
      setTopicError("Select a language (use search to find it).");
      return;
    }
    const name = topicName.trim();
    if (!name) {
      setTopicError("Topic name is required.");
      return;
    }
    let related_documents;
    try {
      related_documents = parseRelatedDocuments(topicDocsJson);
    } catch (err) {
      setTopicError(err.message);
      return;
    }
    setTopicSubmitting(true);
    try {
      await apiFetch("/admin/topics", {
        method: "POST",
        authRole: "admin",
        body: JSON.stringify({ language_id: lid, name, related_documents }),
      });
      setTopicName("");
      setTopicDocsJson("");
      setTopicMessage("Topic added.");
      setListLanguageId(String(lid));
      await loadAll();
    } catch (err) {
      setTopicError(err.message);
    } finally {
      setTopicSubmitting(false);
    }
  };

  return (
    <div className="page page--wide">
      <header className="header">
        <p className="page-eyebrow">Admin · Catalog</p>
        <h1>Languages &amp; topics</h1>
        <p className="muted">
          Manage the reference catalog used on <Link to="/admin">Generate</Link> when you choose
          &ldquo;Language and topic (from catalog)&rdquo;. Stored in PostgreSQL.
        </p>
      </header>

      {loadError && (
        <div className="error" role="alert">
          {loadError}
        </div>
      )}

      {loading && <p className="muted">Loading catalog…</p>}

      {!loading && !loadError && (
        <>
          <div className="grid catalog-form-row">
            <section className="card">
              <h2>Add language</h2>
              <p className="muted small-print">
                Short <strong>code</strong> (e.g. <code>en</code>, <code>de</code>) and display{" "}
                <strong>name</strong>. Codes must be unique.
              </p>
              <form onSubmit={handleAddLanguage} className="stack">
                <label>
                  Code
                  <input
                    value={langCode}
                    onChange={(e) => setLangCode(e.target.value)}
                    placeholder="en"
                    maxLength={32}
                    autoComplete="off"
                  />
                </label>
                <label>
                  Name
                  <input
                    value={langName}
                    onChange={(e) => setLangName(e.target.value)}
                    placeholder="English"
                    maxLength={128}
                    autoComplete="off"
                  />
                </label>
                <button type="submit" className="primary" disabled={langSubmitting}>
                  {langSubmitting ? "Saving…" : "Add language"}
                </button>
              </form>
              {langMessage && <p className="success">{langMessage}</p>}
              {langError && (
                <div className="error" role="alert">
                  {langError}
                </div>
              )}

              <h3 className="catalog-subh">Languages ({languages.length})</h3>
              {languages.length === 0 ? (
                <p className="muted">No languages yet. Add one above.</p>
              ) : (
                <div className="table-wrap table-wrap--nested">
                  <table className="data-table data-table--nested">
                    <thead>
                    <tr>
                      <th>ID</th>
                      <th>Code</th>
                      <th>Name</th>
                      <th className="cell-nowrap">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {languages.map((l) => (
                      <tr key={l.id}>
                        <td>
                          <code className="cell-id">{l.id}</code>
                        </td>
                        <td>
                          <code>{l.code}</code>
                        </td>
                        <td>{l.name}</td>
                        <td className="cell-actions">
                          <button
                            type="button"
                            className="btn-table-secondary"
                            onClick={() => openEditLanguage(l)}
                            disabled={!!editLanguage || editLanguageSaving}
                          >
                            Edit
                          </button>
                        </td>
                      </tr>
                    ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section className="card">
              <h2>Add topic</h2>
              <p className="muted small-print">
                Each topic belongs to one language. Name must be unique per language. Use search to pick
                the language. Optional: related documents (JSON) for the LLM.
              </p>
              <form onSubmit={handleAddTopic} className="stack">
                <SearchableLanguageSelect
                  label="Language"
                  inputId="topic-form-lang"
                  languages={languages}
                  value={topicLanguageId}
                  onChange={setTopicLanguageId}
                  required
                  disabled={languages.length === 0}
                  hint="Type to filter by name, code, or id, then pick from the list."
                />
                <label>
                  Topic name
                  <input
                    value={topicName}
                    onChange={(e) => setTopicName(e.target.value)}
                    placeholder="e.g. Python basics — syntax and types"
                    maxLength={256}
                    autoComplete="off"
                  />
                </label>
                <label>
                  Related documents (JSON, optional)
                  <textarea
                    rows={5}
                    value={topicDocsJson}
                    onChange={(e) => setTopicDocsJson(e.target.value)}
                    placeholder={DOCS_PLACEHOLDER}
                    className="mono-textarea"
                    spellCheck={false}
                  />
                </label>
                <button
                  type="submit"
                  className="primary"
                  disabled={topicSubmitting || languages.length === 0}
                >
                  {topicSubmitting ? "Saving…" : "Add topic"}
                </button>
              </form>
              {topicMessage && <p className="success">{topicMessage}</p>}
              {topicError && (
                <div className="error" role="alert">
                  {topicError}
                </div>
              )}
            </section>
          </div>

          <section className="card catalog-topics-row">
            <h2>Topics for selected language</h2>
            <p className="muted small-print" style={{ marginTop: 0 }}>
              Search and select a language to list only its topics. Use the field below to narrow
              topic titles. <strong>Edit</strong> or <strong>Delete</strong> changes the catalog; delete
              is permanent.
            </p>
            <div className="grid" style={{ marginTop: "0.75rem" }}>
              <SearchableLanguageSelect
                label="Language"
                inputId="list-filter-lang"
                languages={languages}
                value={listLanguageId}
                onChange={setListLanguageId}
                disabled={languages.length === 0}
                hint="Type to search — the topic table updates to match this language only."
              />
              <label>
                Filter topic titles (optional)
                <input
                  type="search"
                  value={topicNameFilter}
                  onChange={(e) => setTopicNameFilter(e.target.value)}
                  placeholder="Narrow by topic name…"
                  disabled={!listLanguageId}
                  autoComplete="off"
                />
                <span className="lang-combo-hint">Only applies after a language is selected.</span>
              </label>
            </div>

            <h3 className="catalog-subh">
              {!listLanguageId
                ? "Topics"
                : `Topics — ${selectedListLanguage ? langLabel(selectedListLanguage) : "language"}`}{" "}
              <span className="muted" style={{ fontWeight: 400, fontSize: "0.85em" }}>
                (
                {listLanguageId
                  ? `${topicsForSelectedLanguage.length} of ${
                      topics.filter((t) => String(t.language_id) === String(listLanguageId)).length
                    } in this language`
                  : "select a language"}
                )
              </span>
            </h3>

            {!listLanguageId && <p className="muted">Select a language above to see its topic list.</p>}

            {listActionError && (
              <div className="error" role="alert" style={{ marginTop: "0.75rem" }}>
                {listActionError}
              </div>
            )}

            {listLanguageId && topicsForSelectedLanguage.length === 0 && (
              <p className="muted">No topics for this language (or no matches for the title filter).</p>
            )}

            {listLanguageId && topicsForSelectedLanguage.length > 0 && (
              <div className="table-wrap table-wrap--nested">
                <table className="data-table data-table--nested">
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Topic</th>
                      <th>Docs</th>
                      <th className="cell-nowrap">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topicsForSelectedLanguage.map((t) => (
                      <tr key={t.id}>
                        <td>
                          <code className="cell-id">{t.id}</code>
                        </td>
                        <td>{t.name}</td>
                        <td className="cell-nowrap">
                          {Array.isArray(t.related_documents) ? t.related_documents.length : 0}
                        </td>
                        <td className="cell-actions">
                          <div className="cell-actions-btns">
                            <button
                              type="button"
                              className="btn-table-secondary"
                              onClick={() => openEditTopic(t)}
                              disabled={!!editTopic || editTopicSaving}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              className="btn-table-danger"
                              onClick={() => void handleDeleteTopic(t)}
                              disabled={deletingTopicId === t.id}
                            >
                              {deletingTopicId === t.id ? "…" : "Delete"}
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
            ref={langDialogRef}
            className="dialog-catalog"
            onClose={() => {
              setEditLanguage(null);
              setEditLanguageError(null);
            }}
          >
            {editLanguage && (
              <form onSubmit={saveLanguage} className="dialog-catalog-form">
                <div className="dialog-catalog__body stack">
                  <h3>Edit language</h3>
                  <p className="muted small-print" style={{ marginTop: 0, marginBottom: 0 }}>
                    Code must stay unique. Saving updates the list everywhere it is used.
                  </p>
                  <label>
                    Code
                    <input
                      value={editLanguage.code}
                      onChange={(e) =>
                        setEditLanguage((p) => (p ? { ...p, code: e.target.value } : p))
                      }
                      maxLength={32}
                      autoComplete="off"
                    />
                  </label>
                  <label>
                    Name
                    <input
                      value={editLanguage.name}
                      onChange={(e) =>
                        setEditLanguage((p) => (p ? { ...p, name: e.target.value } : p))
                      }
                      maxLength={128}
                      autoComplete="off"
                    />
                  </label>
                  {editLanguageError && (
                    <div className="error" role="alert">
                      {editLanguageError}
                    </div>
                  )}
                </div>
                <div className="dialog-catalog__actions">
                  <button
                    type="button"
                    className="btn-table-secondary"
                    onClick={() => {
                      if (langDialogRef.current) langDialogRef.current.close();
                    }}
                    disabled={editLanguageSaving}
                  >
                    Cancel
                  </button>
                  <button type="submit" className="primary" disabled={editLanguageSaving}>
                    {editLanguageSaving ? "Saving…" : "Save changes"}
                  </button>
                </div>
              </form>
            )}
          </dialog>

          <dialog
            ref={topicDialogRef}
            className="dialog-catalog"
            onClose={() => {
              setEditTopic(null);
              setEditTopicError(null);
            }}
          >
            {editTopic && (
              <form onSubmit={saveTopic} className="dialog-catalog-form">
                <div className="dialog-catalog__body stack">
                  <h3>Edit topic</h3>
                  <SearchableLanguageSelect
                    label="Language"
                    inputId="edit-topic-lang"
                    languages={languages}
                    value={editTopic.languageId}
                    onChange={(v) => setEditTopic((p) => (p ? { ...p, languageId: v } : p))}
                    disabled={languages.length === 0}
                    hint="Change language if the topic should live under a different one."
                  />
                  <label>
                    Topic name
                    <input
                      value={editTopic.name}
                      onChange={(e) =>
                        setEditTopic((p) => (p ? { ...p, name: e.target.value } : p))
                      }
                      maxLength={256}
                      autoComplete="off"
                    />
                  </label>
                  <label>
                    Related documents (JSON, optional)
                    <textarea
                      rows={6}
                      value={editTopic.docsText}
                      onChange={(e) =>
                        setEditTopic((p) => (p ? { ...p, docsText: e.target.value } : p))
                      }
                      className="mono-textarea"
                      placeholder={DOCS_PLACEHOLDER}
                      spellCheck={false}
                    />
                  </label>
                  {editTopicError && (
                    <div className="error" role="alert">
                      {editTopicError}
                    </div>
                  )}
                </div>
                <div className="dialog-catalog__actions">
                  <button
                    type="button"
                    className="btn-table-secondary"
                    onClick={() => {
                      if (topicDialogRef.current) topicDialogRef.current.close();
                    }}
                    disabled={editTopicSaving}
                  >
                    Cancel
                  </button>
                  <button type="submit" className="primary" disabled={editTopicSaving}>
                    {editTopicSaving ? "Saving…" : "Save changes"}
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
        <Link to="/admin/assessments">Assessments</Link>
        {" · "}
        <Link to="/admin/submissions">Submissions</Link>
      </p>
    </div>
  );
}
