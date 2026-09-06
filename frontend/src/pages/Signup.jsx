import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { getErrorMessage } from "../api/client";
import Icon from "../components/icons";
import Logo from "../components/Logo";

const INITIAL_FORM = {
  store_name: "",
  email: "",
  phone: "",
  password: "",
  confirm: "",
};

export default function Signup() {
  const { signup } = useAuth();

  const [form, setForm] = useState(INITIAL_FORM);
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  // Set after a successful signup — the account needs email
  // verification before login works, so we land on a note instead of
  // routing into the dashboard
  const [verifyPending, setVerifyPending] = useState(null);

  function updateField(name, value) {
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  function validate() {
    if (!form.store_name.trim()) return "Please enter your store name.";
    if (form.store_name.trim().length < 2) return "Store name is too short.";
    if (!form.email.trim()) return "Please enter your email.";
    if (!/^\S+@\S+\.\S+$/.test(form.email)) return "Please enter a valid email address.";
    if (form.phone && form.phone.trim().length < 6) return "Phone number looks too short.";
    if (form.password.length < 8) return "Password must be at least 8 characters.";
    if (form.password !== form.confirm) return "Passwords do not match.";
    return null;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      await signup({
        store_name: form.store_name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim() || null,
        password: form.password,
      });
      setVerifyPending(form.email.trim());
    } catch (err) {
      setError(getErrorMessage(err, "Signup failed. Is the backend running?"));
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
          {verifyPending ? (
            <>
              <h1>Check your email</h1>
              <p>
                We sent a verification link to <strong>{verifyPending}</strong>.
                Click it to activate your account, then log in.
              </p>
            </>
          ) : (
            <>
              <h1>Create your store</h1>
              <p>Start tracking orders in 30 seconds</p>
            </>
          )}
        </div>

        {verifyPending ? (
          <>
            <div className="alert alert--success" role="status">
              Your store is ready — one last step: verify your email address
              so you can log in and start taking orders.
            </div>
            <Link to="/login" className="button button--primary button--full">
              Go to login
            </Link>
            <p className="auth-back">
              <Link to="/">
                <Icon name="chevronLeft" size={14} />
                Back to home
              </Link>
            </p>
          </>
        ) : (
          <>
            {error && (
              <div className="alert alert--error" role="alert">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} noValidate>
          <div className="field">
            <label htmlFor="store_name">Store name</label>
            <input
              id="store_name"
              type="text"
              autoComplete="organization"
              placeholder="e.g. Abin Fashion House"
              value={form.store_name}
              onChange={(e) => updateField("store_name", e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="you@store.com"
              value={form.email}
              onChange={(e) => updateField("email", e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="phone">
              Phone <span className="field-optional">(optional)</span>
            </label>
            <input
              id="phone"
              type="tel"
              autoComplete="tel"
              placeholder="01XXXXXXXXX"
              value={form.phone}
              onChange={(e) => updateField("phone", e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              placeholder="At least 8 characters"
              value={form.password}
              onChange={(e) => updateField("password", e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="confirm">Confirm password</label>
            <input
              id="confirm"
              type="password"
              autoComplete="new-password"
              placeholder="Repeat your password"
              value={form.confirm}
              onChange={(e) => updateField("confirm", e.target.value)}
            />
          </div>

          <button type="submit" className="button button--primary button--full" disabled={submitting}>
            {submitting ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="auth-switch">
          Already have an account? <Link to="/login">Log in</Link>
        </p>
        <p className="auth-back">
          <Link to="/">
            <Icon name="chevronLeft" size={14} />
            Back to home
          </Link>
        </p>
          </>
        )}
      </div>
    </div>
  );
}
