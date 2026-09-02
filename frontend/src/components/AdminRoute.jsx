import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

/**
 * Gate for admin-only pages: must be logged in AND have role=admin.
 */
export default function AdminRoute({ children }) {
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

  if (seller.role !== "admin") {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
}
