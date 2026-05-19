import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getAdminToken, logoutAdmin } from "../api";

export default function NavBar() {
  const navigate = useNavigate();
  const [, setTick] = useState(0);

  useEffect(() => {
    const h = () => setTick((t) => t + 1);
    window.addEventListener("auth-change", h);
    return () => window.removeEventListener("auth-change", h);
  }, []);

  const adminAuthed = !!getAdminToken();

  return (
    <nav className="nav" aria-label="Main">
      <Link to="/" className="brand">
        AI Assessment
      </Link>
      <div className="nav-links">
        {adminAuthed ? (
          <>
            <span className="nav-label" aria-hidden="true">
              Admin
            </span>
            <Link to="/admin">Generate</Link>
            <Link to="/admin/manual">Manual</Link>
            <Link to="/admin/assessments">Assessments</Link>
            <Link to="/admin/catalog">Catalog</Link>
            <Link to="/admin/submissions">Submissions</Link>
            <button
              type="button"
              className="nav-btn"
              onClick={() => {
                logoutAdmin();
                navigate("/login/admin");
              }}
            >
              Sign out
            </button>
          </>
        ) : (
          <Link to="/login/admin">Admin</Link>
        )}
        <span className="nav-divider" aria-hidden="true" />
        <Link to="/client">Take test</Link>
      </div>
    </nav>
  );
}
