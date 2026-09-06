import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import Icon from "../components/icons";
import Logo from "../components/Logo";

/**
 * The landing page for a signup verification link — /verify-email?token=….
 * Verifies on mount, then shows success or a resend form (expired and
 * single-use tokens get a second chance here).
 */
export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";

  const [state, setState] = useState(token ? "checking" : "missing");
  const [error, setError] = useState(null);
  const [resendEmail, setResendEmail] = useState("");
  const [resendNote, setResendNote] = useState(null);
  const [resending, setResending] = useState(false);

  // Fire the verification request once per token — React StrictMode
  // mounts effects twice in dev, and a second request would hit the
  // now-consumed single-use token and wrongly show "link expired".
  // The result is always applied (no unmount-cancel flag): the cleanup
  // of the first StrictMode mount would otherwise swallow the response
  // of the only request we ever send, leaving the page stuck on
  // "Verifying…" forever.
  const firedRef = useRef(false);

  useEffect(() => {
    if (!token || firedRef.current) return;
    firedRef.current = true;
    api.auth
      .verifyEmail(token)
      .then(() => setState("success"))
      .catch((err) => {
        setError(getErrorMessage(err, "This verification link is invalid or has expired."));
        setState("error");
      });
  }, [token]);

  async function handleResend(event) {
    event.preventDefault();
    if (!resendEmail.trim()) {
      setResendNote("Please enter your email address.");
      return;
    }
    setResending(true);
    setResendNote(null);
    try {
      await api.auth.resendVerification(resendEmail.trim());
      setResendNote("If an unverified account exists with this email, a new link is on its way.");
      setState("resent");
    } catch (err) {
      setResendNote(getErrorMessage(err, "Could not resend the email. Please try again."));
    } finally {
      setResending(false);
    }
  }

  const headings = {
    checking: "Verifying your email…",
    success: "Email verified!",
    error: "Verification link problem",
    missing: "Missing verification token",
    resent: "Check your inbox",
  };
  const subtitles = {
    checking: "Give it a second…",
    success: "Your account is ready — log in and start taking orders.",
    error: "The link may have expired or was already used.",
    missing: "This page needs to be opened from the link in your email.",
    resent: "We sent a fresh verification link.",
  };

  return (
    <div className="page-centered">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="auth-logo">
            <Logo size={38} />
          </span>
          <h1>{headings[state]}</h1>
          <p>{subtitles[state]}</p>
        </div>

        {state === "checking" && (
          <p className="auth-switch" aria-live="polite">
            <Icon name="refresh" size={14} /> Contacting the server…
          </p>
        )}

        {state === "success" && (
          <Link to="/login" className="button button--primary button--full">
            Log in
          </Link>
        )}

        {state === "error" && error && (
          <div className="alert alert--error" role="alert">
            {error}
          </div>
        )}

        {(state === "error" || state === "missing") && (
          <form onSubmit={handleResend} noValidate>
            <div className="field">
              <label htmlFor="resend_email">Email address</label>
              <input
                id="resend_email"
                type="email"
                autoComplete="email"
                placeholder="you@store.com"
                value={resendEmail}
                onChange={(e) => setResendEmail(e.target.value)}
              />
            </div>
            <button
              type="submit"
              className="button button--primary button--full"
              disabled={resending}
            >
              {resending ? "Sending…" : "Send a new verification link"}
            </button>
            {resendNote && state !== "resent" && (
              <p className="muted-note" role="status">
                {resendNote}
              </p>
            )}
          </form>
        )}

        {state === "resent" && resendNote && (
          <div className="alert alert--success" role="status">
            {resendNote}
          </div>
        )}

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
