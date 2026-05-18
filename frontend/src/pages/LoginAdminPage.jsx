import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch, setAdminToken } from "../api";

export default function LoginAdminPage() {
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = await apiFetch("/auth/login", {
        method: "POST",
        body: JSON.stringify({ role: "admin", password }),
      });
      setAdminToken(data.access_token);
      navigate("/admin", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page page--narrow page--center">
      <header className="header" style={{ textAlign: "center" }}>
        <p className="page-eyebrow">Administrator</p>
        <h1>Sign in</h1>
        <p className="muted">Use the admin password from your server configuration.</p>
      </header>

      <section className="card card--elevated">
        <form onSubmit={handleSubmit}>
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
            />
          </label>
          <button type="submit" className="primary" style={{ width: "100%" }} disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <p className="muted footer-hint" style={{ marginTop: "1.25rem" }}>
          <Link to="/client">Participant: take a test (no sign-in) →</Link>
        </p>
      </section>
    </div>
  );
}
