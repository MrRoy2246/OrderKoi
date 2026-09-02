import { useState } from "react";
import { Link } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import Icon from "../components/icons";
import Logo from "../components/Logo";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!email.trim()) {
      setError("Please enter your email address.");
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      await api.auth.forgotPassword(email.trim());
      setSubmitted(true); // same message whether or not the account exists
    } catch (err) {
      setError(getErrorMessage(err, "Could not send the reset email. Please try again."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page-centered">
      <div className="auth-card">
        <div className="auth-brand">
          <span className="auth-logo">
            <Logo size={38} />
          </span>
          <h1>Forgot your password?</h1>
          <p>Enter your email and we'll send you a reset link</p>
        </div>

        {error && (
          <div className="alert alert--error" role="alert">
            {error}
          </div>
        )}

        {submitted ? (
          <div className="alert alert--success" role="status">
            If an account exists with this email, a password reset link has been
            sent. Check your inbox (and spam folder). The link is valid for 30
            minutes.
          </div>
        ) : (
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

            <button
              type="submit"
              className="button button--primary button--full"
              disabled={submitting}
            >
              {submitting ? "Sending…" : "Send reset link"}
            </button>
          </form>
        )}

        <p className="auth-switch">
          Remembered it? <Link to="/login">Back to login</Link>
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
