import { useEffect, useMemo, useRef, useState } from "react";

export function langLabel(l) {
  if (!l) return "";
  return `${l.name} (${l.code})`;
}

/**
 * @param {Object} props
 * @param {string} props.label
 * @param {Array<{id: number, code: string, name: string}>} props.languages
 * @param {string} props.value - selected language id, or ""
 * @param {(v: string) => void} props.onChange
 * @param {boolean} [props.required]
 * @param {boolean} [props.disabled]
 * @param {string} [props.hint]
 * @param {string} [props.inputId]
 */
export default function SearchableLanguageSelect({
  label,
  languages,
  value,
  onChange,
  required = false,
  disabled = false,
  hint,
  inputId = "search-lang",
}) {
  const wrapRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!value || !languages.length) return;
    const sel = languages.find((l) => String(l.id) === String(value));
    if (sel) setSearch(langLabel(sel));
  }, [value, languages]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return languages;
    return languages.filter(
      (l) =>
        l.name.toLowerCase().includes(q) ||
        l.code.toLowerCase().includes(q) ||
        String(l.id).toLowerCase().includes(q)
    );
  }, [languages, search]);

  useEffect(() => {
    const close = (e) => {
      if (!wrapRef.current || wrapRef.current.contains(e.target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const pick = (l) => {
    onChange(String(l.id));
    setSearch(langLabel(l));
    setOpen(false);
  };

  const onInputChange = (e) => {
    const v = e.target.value;
    setSearch(v);
    setOpen(true);
    if (value) {
      onChange("");
    }
  };

  return (
    <div className="lang-combo" ref={wrapRef}>
      <label htmlFor={inputId}>
        {label}
        {required && (
          <span className="muted" aria-hidden="true">
            {" "}
            *
          </span>
        )}
        <input
          id={inputId}
          type="text"
          className="lang-combo-input"
          value={search}
          onChange={onInputChange}
          onFocus={() => setOpen(true)}
          placeholder="Type to search by name, code, or id…"
          autoComplete="off"
          required={false}
          disabled={disabled}
          role="combobox"
          aria-expanded={open}
          aria-controls={`${inputId}-listbox`}
          aria-autocomplete="list"
        />
      </label>
      {hint && <span className="lang-combo-hint">{hint}</span>}
      {open && !disabled && filtered.length > 0 && (
        <ul className="lang-combo-list" id={`${inputId}-listbox`} role="listbox">
          {filtered.map((l) => (
            <li key={l.id} role="none">
              <button
                type="button"
                className="lang-combo-item"
                role="option"
                onMouseDown={(e) => {
                  e.preventDefault();
                  pick(l);
                }}
              >
                <strong>{l.name}</strong> <span className="muted">({l.code})</span>{" "}
                <span className="muted" style={{ fontSize: "0.72rem" }}>
                  id {l.id}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && !disabled && search.trim() && filtered.length === 0 && (
        <ul className="lang-combo-list" id={`${inputId}-listbox`} role="listbox">
          <li className="lang-combo-item" style={{ cursor: "default", color: "var(--text-muted)" }}>
            No languages match
          </li>
        </ul>
      )}
    </div>
  );
}
