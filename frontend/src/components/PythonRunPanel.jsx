import { useCallback, useRef, useState } from "react";

const RUN_TIMEOUT_MS = 25000;
/** Load runtime from CDN — avoids broken local WASM paths and works without COOP/COEP headers. */
const PYODIDE_INDEX_URL = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";

/** Injected once per Pyodide instance; captures stdout/stderr from user `exec`. */
const RUNNER_SETUP = `
def __run_user_code__(user_code):
    from io import StringIO
    import sys
    import traceback
    user_code = (user_code or "").strip()
    if not user_code:
        return (
            "",
            "Nothing to run - the editor is empty or only whitespace. Add Python code, then Execute.\\n",
        )
    _out, _err = StringIO(), StringIO()
    _so, _se = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = _out, _err
    try:
        try:
            code_obj = compile(user_code, "<user>", "exec")
        except SyntaxError as syn:
            _err.write("".join(traceback.format_exception_only(type(syn), syn)))
            return _out.getvalue(), _err.getvalue()
        exec(code_obj, {"__name__": "__main__"})
    except BaseException:
        _err.write(traceback.format_exc())
    finally:
        sys.stdout, sys.stderr = _so, _se
    return _out.getvalue(), _err.getvalue()
`;

let pyodideRef = null;
let pyodideLoadPromise = null;

function asText(v) {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v.toJs === "function") {
    try {
      const j = v.toJs({ depth: 3 });
      return typeof j === "string" ? j : String(j);
    } catch {
      /* fall through */
    }
  }
  if (typeof v.toString === "function") return v.toString();
  return String(v);
}

async function getPyodideWithRunner() {
  if (pyodideRef) return pyodideRef;
  if (!pyodideLoadPromise) {
    pyodideLoadPromise = (async () => {
      try {
        const { loadPyodide } = await import("pyodide");
        const py = await loadPyodide({
          fullStdLib: false,
          indexURL: PYODIDE_INDEX_URL,
        });
        await py.runPythonAsync(RUNNER_SETUP);
        pyodideRef = py;
        return py;
      } catch (e) {
        pyodideLoadPromise = null;
        const msg = e?.message || String(e);
        throw new Error(
          `Could not load Python in the browser (Pyodide). Check your network, VPN, or ad-blocker, then try Execute again. ${msg}`
        );
      }
    })();
  }
  return pyodideLoadPromise;
}

/**
 * Run Python source in the browser (Pyodide). Only meaningful when the editor language is Python.
 * @param {"default" | "playground"} [props.variant] playground = CodePen-style console (always shows output area)
 */
export default function PythonRunPanel({ code, disabled, variant = "default" }) {
  const [running, setRunning] = useState(false);
  const [loadingHint, setLoadingHint] = useState(false);
  const [stdout, setStdout] = useState("");
  const [stderr, setStderr] = useState("");
  const runLockRef = useRef(false);

  const clearOutput = useCallback(() => {
    setStdout("");
    setStderr("");
  }, []);

  const run = useCallback(async () => {
    if (disabled || runLockRef.current) return;
    runLockRef.current = true;
    setStdout("");
    setStderr("");
    setRunning(true);
    setLoadingHint(true);
    try {
      const py = await getPyodideWithRunner();
      setLoadingHint(false);
      const src = (code ?? "").trim();
      if (src) {
        try {
          await py.loadPackagesFromImports(src, { checkIntegrity: false });
        } catch (packErr) {
          setStderr((prev) => (prev ? `${prev}\n` : "") + (packErr?.message || String(packErr)));
        }
      }
      py.globals.set("user_code", code ?? "");
      const execPromise = py.runPythonAsync("OUT, ERR = __run_user_code__(user_code)");
      const timeoutPromise = new Promise((_, rej) =>
        setTimeout(
          () =>
            rej(
              new Error(
                `Still running after ${RUN_TIMEOUT_MS / 1000}s — close this tab if it hangs.`
              )
            ),
          RUN_TIMEOUT_MS
        )
      );
      await Promise.race([execPromise, timeoutPromise]);
      setStdout(asText(py.globals.get("OUT")));
      setStderr(asText(py.globals.get("ERR")));
    } catch (e) {
      setLoadingHint(false);
      setStderr((prev) => (prev ? `${prev}\n` : "") + (e?.message || String(e)));
    } finally {
      setRunning(false);
      setLoadingHint(false);
      runLockRef.current = false;
    }
  }, [code, disabled]);

  const isPlayground = variant === "playground";
  const hasOutput = !!(stdout || stderr);

  const toolbar = (
    <div className={`python-run-toolbar${isPlayground ? " python-run-toolbar--playground" : ""}`}>
      <div className="python-run-actions">
        <button
          type="button"
          className="primary"
          style={{ width: "auto", minWidth: "7rem" }}
          onClick={run}
          disabled={disabled || running}
        >
          {running ? (loadingHint ? "Loading Python…" : "Executing…") : "Execute"}
        </button>
        {isPlayground && (
          <button
            type="button"
            className="nav-btn"
            onClick={clearOutput}
            disabled={disabled || running || !hasOutput}
          >
            Clear
          </button>
        )}
      </div>
      {!isPlayground && (
        <span className="muted small-print">
          Runs in your browser (Pyodide). First use downloads the Python runtime (~20+ MB). If you see{" "}
          <code className="cell-id">&lt;user&gt;</code>, line 1 — that is <em>your</em> code’s first line; scroll
          the red box for the real error (e.g. <code className="cell-id">SyntaxError</code>,{" "}
          <code className="cell-id">IndentationError</code>).
        </span>
      )}
    </div>
  );

  const outputBlock = (
    <div
      className={`python-run-output${isPlayground ? " python-run-output--playground" : ""}`}
      role="region"
      aria-label="Program output"
    >
      {isPlayground && !hasOutput && !running && (
        <p className="python-run-placeholder muted small-print">
          Output from <strong>print()</strong> and errors appear here after you click Execute. First run downloads
          Pyodide (~20+ MB).
        </p>
      )}
      {stdout ? (
        <div>
          <span className="python-run-label">stdout</span>
          <pre className="python-run-pre python-run-pre--out">{stdout}</pre>
        </div>
      ) : null}
      {stderr ? (
        <div>
          <span className="python-run-label">stderr / traceback</span>
          <pre className="python-run-pre python-run-pre--err">{stderr}</pre>
        </div>
      ) : null}
    </div>
  );

  if (isPlayground) {
    return (
      <div className="python-run-panel python-run-panel--playground">
        {toolbar}
        {outputBlock}
        <p className="python-run-playground-hint muted small-print">
          Tracebacks reference <code className="cell-id">&lt;user&gt;</code> for your editor text — read the last
          lines for <code className="cell-id">SyntaxError</code> / <code className="cell-id">NameError</code>, etc.
        </p>
      </div>
    );
  }

  return (
    <div className="python-run-panel">
      {toolbar}
      {hasOutput && outputBlock}
    </div>
  );
}
