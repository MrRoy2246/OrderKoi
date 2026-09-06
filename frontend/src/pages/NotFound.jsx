import { Link } from "react-router-dom";
import Icon from "../components/icons";
import Logo from "../components/Logo";

/**
 * 404 — any URL that matches no route. Distinct from the landing page
 * so a bad link is visibly bad (and the browser back button makes
 * sense) instead of silently pretending to be home.
 */
export default function NotFound() {
  return (
    <div className="page-centered">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="auth-logo">
            <Logo size={38} />
          </span>
          <h1>Page not found</h1>
          <p>
            The page you&apos;re looking for doesn&apos;t exist — the link may be old
            or mistyped.
          </p>
        </div>

        <div className="alert" role="status" style={{ textAlign: "center" }}>
          <span aria-hidden="true" style={{ fontSize: "2rem", fontWeight: 700 }}>
            404
          </span>
        </div>

        <Link to="/" className="button button--primary button--full">
          <Icon name="chevronLeft" size={14} />
          Back to home
        </Link>
      </div>
    </div>
  );
}
