import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { api, getErrorMessage } from "../api/client";
import Icon from "../components/icons";
import Logo from "../components/Logo";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const justReset = searchParams.get("reset") === "success";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  // Set when the account exists but the email isn't verified yet —
  // shows the resend option instead of a bare error
  const [needsVerification, setNeedsVerification] = useState(false);
  const [resendNote, setResendNote] = useState(null);
  const [resending, setResending] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setNeedsVerification(false);

    if (!email || !password) {
      setError("Please enter your email and password.");
      return;
    }

    setSubmitting(true);
    try {
      const me = await login(email, password);
      // Platform admins land in the admin panel, sellers in their store
      navigate(me.role === "admin" ? "/admin" : "/dashboard", { replace: true });
    } catch (err) {
      const message = getErrorMessage(err, "Login failed. Is the backend running?");
      if (err?.status === 403 && message.toLowerCase().includes("verify")) {
        setNeedsVerification(true);
      }
      setError(message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResend() {
    setResending(true);
    setResendNote(null);
    try {
      await api.auth.resendVerification(email.trim());
      setResendNote("If an unverified account exists with this email, a new link is on its way.");
    } catch (err) {
      setResendNote(getErrorMessage(err, "Could not resend the email. Please try again."));
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="page-centered">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="auth-logo">
            <Logo size={38} />
          </span>
          <h1>Welcome back</h1>
          <p>Log in to your OrderKoi dashboard</p>
        </div>

        {justReset && (
          <div className="alert alert--success" role="status">
            Password updated — log in with your new password.
          </div>
        )}

        {error && (
          <div className="alert alert--error" role="alert">
            {error}
          </div>
        )}

        {needsVerification && (
          <div className="verify-resend">
            <button
              type="button"
              className="button button--outline button--full"
              onClick={handleResend}
              disabled={resending || !email.trim()}
              title="Send a fresh verification link to your email"
            >
              {resending ? "Sending…" : "Resend verification email"}
            </button>
            {resendNote && (
              <p className="muted-note" role="status">
                {resendNote}
              </p>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="you@store.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              placeholder="Your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <button type="submit" className="button button--primary button--full" disabled={submitting}>
            {submitting ? "Logging in…" : "Log in"}
          </button>
        </form>

        <p className="auth-forgot">
          <Link to="/forgot-password">Forgot your password?</Link>
        </p>

        <p className="auth-switch">
          New to OrderKoi? <Link to="/signup">Create an account</Link>
        </p>
        <p className="auth-back">
          <Link to="/">
            <Icon name="chevronLeft" size={14} />
            Back to home
          </Link>
        </p>
      </div>
    </div>
  );
}
