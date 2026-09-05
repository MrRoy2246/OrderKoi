import { useState } from "react";
import { api, getErrorMessage } from "../api/client";
import Icon from "./icons";
import { parseServerDate } from "../utils/orderStatus";

/** Manual Pro activation durations — mirrors what sellers pay for. */
const DURATIONS = [
  { months: 1, label: "1 month", note: "short boost" },
  { months: 6, label: "6 months", note: "half a year" },
  { months: 12, label: "12 months", note: "a full year" },
];

function formatDate(value) {
  return parseServerDate(value).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * Modal for granting Pro to a shop by hand (cash sales, support cases,
 * and free "comp" gifts). The duration is required — no accidental
 * lifetime Pro — and extends stack on the current expiry, exactly like
 * approved upgrade requests.
 */
export default function AdminProModal({ seller, onClose, onDone }) {
  const [selected, setSelected] = useState(1);
  const [comp, setComp] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const active =
    seller.plan === "pro" &&
    (!seller.plan_expires_at || new Date(seller.plan_expires_at) >= new Date());
  const expired = seller.plan === "pro" && !active;
  const chosen = DURATIONS.find((d) => d.months === selected);

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const updated = await api.admin.setPlan(seller.id, "pro", selected, comp);
      onDone(updated);
    } catch (err) {
      setError(getErrorMessage(err, "Could not update the plan."));
      setSubmitting(false);
    }
  }

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={`${active ? "Extend" : "Activate"} Pro for ${seller.store_name}`}
    >
      <div className="modal modal--compact">
        <div className="modal-header">
          <h2>
            {active ? "Extend Pro" : expired ? "Renew Pro" : "Activate Pro"}
          </h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            <Icon name="x" size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          <div className="modal-form">
            <p className="admin-pro-store">
              <Icon name="store" size={15} />
              <strong>{seller.store_name}</strong>
            </p>
            <p className="admin-pro-context">
              {active && seller.plan_expires_at
                ? `Pro is active until ${formatDate(seller.plan_expires_at)} — the duration you pick adds on top, so no paid time is lost.`
                : active
                  ? "Pro is active with no expiry. Picking a duration sets a concrete end date going forward."
                  : "Pick how long Pro lasts. The shop gets unlimited orders for that period."}
            </p>

            <div className="plan-options" role="radiogroup" aria-label="Pro duration">
              {DURATIONS.map((duration) => (
                <button
                  key={duration.months}
                  type="button"
                  role="radio"
                  aria-checked={selected === duration.months}
                  className={`plan-option${selected === duration.months ? " plan-option--selected" : ""}`}
                  onClick={() => setSelected(duration.months)}
                >
                  <span className="plan-option-months">Pro for</span>
                  <span className="plan-option-price">{duration.label}</span>
                  <span className="plan-option-note">{duration.note}</span>
                </button>
              ))}
            </div>

            {/* Free access (comp) — gift Pro instead of recording a sale */}
            <label className={`comp-toggle${comp ? " comp-toggle--on" : ""}`}>
              <input
                type="checkbox"
                checked={comp}
                onChange={(e) => setComp(e.target.checked)}
              />
              <span className="comp-toggle-track" aria-hidden="true">
                <span className="comp-toggle-thumb" />
              </span>
              <span className="comp-toggle-text">
                <strong>Give this free</strong>
                <span>
                  {comp
                    ? "A gift — not counted in subscription earnings, and the seller gets an email."
                    : "For gifts/support cases: the seller pays nothing and this grant is excluded from earnings."}
                </span>
              </span>
            </label>

            {error && (
              <div className="alert alert--error" role="alert">
                {error}
              </div>
            )}
          </div>

          <div className="modal-actions">
            <button
              type="button"
              className="button button--ghost"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </button>
            <button type="submit" className="button button--primary" disabled={submitting}>
              <Icon name="sparkles" size={15} />
              {submitting
                ? "Saving…"
                : comp
                  ? `Grant free Pro — ${chosen.label}`
                  : `${active ? "Extend" : "Activate"} Pro — ${chosen.label}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
