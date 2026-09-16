import { useState } from "react";
import { api, getErrorMessage, setToken } from "../api/client";
import Icon from "./icons";

/**
 * Change the signed-in seller's password.
 *
 * Two things make this more than a form:
 *
 *  - the server revokes every token minted before the change, which is
 *    the point (it is how someone evicts whoever else has their
 *    password) — so the replacement token it returns MUST be stored,
 *    or the very next request signs the seller out;
 *  - the old password is required as well as the new one, so a
 *    borrowed laptop with a live session is not enough to take the
 *    account over.
 */
export default function ChangePasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setDone(false);

    // Checked here as well as on the server so the common mistakes are
    // answered without a round trip — the server's checks still stand.
    if (next.length < 8) {
      setError("Your new password must be at least 8 characters.");
      return;
    }
    if (next !== confirm) {
      setError("The two new passwords don't match.");
      return;
    }
    if (next === current) {
      setError("Your new password must be different from your current one.");
      return;
    }

    setSubmitting(true);
    try {
      const { access_token: token } = await api.auth.changePassword(current, next);
      setToken(token); // the old one is dead as of this moment
      setCurrent("");
      setNext("");
      setConfirm("");
      setDone(true);
    } catch (err) {
      setError(getErrorMessage(err, "Could not change your password."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="card">
      <h3>Password</h3>
      <p>
        Changing your password signs you out everywhere else. You'll stay signed in
        here.
      </p>

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}
      {done && (
        <div className="alert alert--success" role="status">
          Password updated. Any other device that was signed in has been signed out.
        </div>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <div className="field">
          <label htmlFor="current_password">Current password</label>
          <input
            id="current_password"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="new_password">
            New password <span className="field-optional">(at least 8 characters)</span>
          </label>
          <input
            id="new_password"
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="confirm_password">Confirm new password</label>
          <input
            id="confirm_password"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </div>

        <button
          type="submit"
          className="button button--primary"
          disabled={submitting || !current || !next || !confirm}
        >
          <Icon name="check" size={16} />
          {submitting ? "Updating…" : "Update password"}
        </button>
      </form>
    </section>
  );
}
