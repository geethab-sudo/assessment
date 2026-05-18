import { Navigate } from "react-router-dom";
import { getAdminToken } from "../api";

export function ProtectedAdmin({ children }) {
  if (!getAdminToken()) {
    return <Navigate to="/login/admin" replace />;
  }
  return children;
}
