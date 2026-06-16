import { BrowserRouter, Link, Navigate, Route, Routes } from "react-router-dom";
import NavBar from "./components/NavBar.jsx";
import { ProtectedAdmin } from "./components/ProtectedRoute.jsx";
import AdminPage from "./pages/AdminPage.jsx";
import AdminAssessmentsPage from "./pages/AdminAssessmentsPage.jsx";
import AdminReviewPage from "./pages/AdminReviewPage.jsx";
import AdminSubmissionsPage from "./pages/AdminSubmissionsPage.jsx";
import AdminCatalogPage from "./pages/AdminCatalogPage.jsx";
import AdminQuestionBankPage from "./pages/AdminQuestionBankPage.jsx";
import ClientPage from "./pages/ClientPage.jsx";
import LoginAdminPage from "./pages/LoginAdminPage.jsx";
import LoginClientPage from "./pages/LoginClientPage.jsx";

function HomePage() {
  return (
    <div className="page">
      <div className="hero">
        <header className="header">
          <p className="page-eyebrow">AI-powered</p>
          <h1>Assessment platform</h1>
          <p className="muted hero-lead">
            Admins generate Python assessments with an LLM. Participants open the test page, enter their
            employee ID, name, and assessment ID, and complete the test in the browser — no sign-in
            required.
          </p>
        </header>
      </div>
      <div className="portal-grid">
        <Link to="/login/admin" className="portal-card">
          <div className="portal-icon" aria-hidden="true">
            ⚙️
          </div>
          <h3>Administrator</h3>
          <p>Create assessments, review all tests and submissions.</p>
        </Link>
        <Link to="/client" className="portal-card">
          <div className="portal-icon" aria-hidden="true">
            📝
          </div>
          <h3>Participant</h3>
          <p>Enter your employee ID, name, and assessment ID to take a test.</p>
        </Link>
      </div>
    </div>
  );
}

function Layout() {
  return (
    <>
      <NavBar />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/login/admin" element={<LoginAdminPage />} />
        <Route path="/login/client" element={<LoginClientPage />} />
        <Route
          path="/admin"
          element={
            <ProtectedAdmin>
              <AdminPage />
            </ProtectedAdmin>
          }
        />
        <Route
          path="/admin/assessments"
          element={
            <ProtectedAdmin>
              <AdminAssessmentsPage />
            </ProtectedAdmin>
          }
        />
        <Route
          path="/admin/review"
          element={
            <ProtectedAdmin>
              <AdminReviewPage />
            </ProtectedAdmin>
          }
        />
        <Route
          path="/admin/submissions"
          element={
            <ProtectedAdmin>
              <AdminSubmissionsPage />
            </ProtectedAdmin>
          }
        />
        <Route
          path="/admin/catalog"
          element={
            <ProtectedAdmin>
              <AdminCatalogPage />
            </ProtectedAdmin>
          }
        />
        <Route
          path="/admin/question-bank"
          element={
            <ProtectedAdmin>
              <AdminQuestionBankPage />
            </ProtectedAdmin>
          }
        />
        <Route path="/client" element={<ClientPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  );
}
