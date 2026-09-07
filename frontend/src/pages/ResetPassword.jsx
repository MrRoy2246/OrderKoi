import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import Icon from "../components/icons";
import Logo from "../components/Logo";

/**
 * Reset password — step 2 of the reset flow (arrives via the email
 * link, ?token=…). The token is single-use and expires in 30 minutes;
 * on success every previously issued session token is invalidated
 * server-side (stolen sessions can't outlive the reset), and we route
 * to /login?reset=success.
 */
export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const navigate = useNavigate();

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();

    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      await api.auth.resetPassword(token, password);
      navigate("/login?reset=success", { replace: true });
    } catch (err) {
      setError(getErrorMessage(err, "Could not reset your password. Please request a new link."));
    } finally {
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <div className="page-centered">
        <div className="auth-card">
          <div className="auth-brand">
            <span className="auth-logo">
              <Logo size={38} />
            </span>
            <h1>Missing reset token</h1>
            <p>This page needs to be opened from the link in your email.</p>
          </div>
          <Link to="/forgot-password" className="button button--primary button--full">
            Request a new reset link
          </Link>
          <p className="auth-back">
            <Link to="/login">
              <Icon name="chevronLeft" size={14} />
              Back to login
            </Link>
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-centered">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="auth-logo">
            <Logo size={38} />
          </span>
          <h1>Choose a new password</h1>
          <p>Make it strong — at least 8 characters</p>
        </div>

        {error && (
          <div className="alert alert--error" role="alert">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>
          <div className="field">
            <label htmlFor="password">New password</label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              placeholder="At least 8 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="confirm">Confirm new password</label>
            <input
              id="confirm"
              type="password"
              autoComplete="new-password"
              placeholder="Repeat your new password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </div>

          <button
            type="submit"
            className="button button--primary button--full"
            disabled={submitting}
          >
            {submitting ? "Updating…" : "Update password"}
          </button>
        </form>

        <p className="auth-back">
          <Link to="/login">
            <Icon name="chevronLeft" size={14} />
            Back to login
          </Link>
        </p>
      </div>
    </div>
  );
}
