import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch, setClientToken } from "../api";

export default function LoginClientPage() {
  const navigate = useNavigate();
  const [clientId, setClientId] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = await apiFetch("/auth/login", {
        method: "POST",
        body: JSON.stringify({ role: "client", client_id: clientId.trim() }),
      });
      setClientToken(data.access_token);
      navigate("/client", { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page page--narrow page--center">
      <header className="header" style={{ textAlign: "center" }}>
        <p className="page-eyebrow">Participant</p>
        <h1>Welcome</h1>
        <p className="muted">
          Enter the <strong>client ID</strong> your organization shared with you (same value the admin used
          when creating your assessment).
        </p>
      </header>

      <section className="card card--elevated">
        <form onSubmit={handleSubmit}>
          <label>
            Client ID
            <input
              type="text"
              autoComplete="username"
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              placeholder="e.g. acme-corp"
              required
            />
          </label>
          <button type="submit" className="primary" style={{ width: "100%" }} disabled={loading}>
            {loading ? "Continuing…" : "Continue"}
          </button>
        </form>
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        <p className="muted footer-hint" style={{ marginTop: "1.25rem" }}>
          <Link to="/login/admin">Administrator sign in →</Link>
        </p>
      </section>
    </div>
  );
}
