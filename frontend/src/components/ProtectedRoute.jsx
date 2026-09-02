import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

/**
 * Gate for seller pages (/dashboard/*): sellers proceed, admins are
 * redirected to their platform panel, everyone else to login.
 */
export default function ProtectedRoute({ children }) {
  const { seller, loading } = useAuth();

  if (loading) {
    return (
      <div className="page-centered">
        <div className="loading-card">
          <div className="spinner" aria-hidden="true" />
          <p>Loading your session…</p>
        </div>
      </div>
    );
  }

  if (!seller) {
    return <Navigate to="/login" replace />;
  }

  if (seller.role === "admin") {
    return <Navigate to="/admin" replace />;
  }

  return children;
}
