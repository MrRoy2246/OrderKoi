import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { api, getErrorMessage } from "../api/client";
import Icon from "./icons";
import { parseServerDate } from "../utils/orderStatus";
import { PRO_OPTIONS } from "../utils/proPricing";

/** Where sellers send payment. Replace with your real numbers. */
const PAYMENT_INSTRUCTIONS =
  "Send the amount via bKash/Nagad to 01XXXXXXXXX (Personal), then submit " +
  "the request below with your transaction ID. We'll activate Pro after " +
  "verifying the payment (usually within a few hours).";

const STATUS_LABELS = {
  pending: { text: "Pending review", className: "upgrade-status--pending" },
  approved: { text: "Approved", className: "upgrade-status--approved" },
  rejected: { text: "Rejected", className: "upgrade-status--rejected" },
};

function formatDate(value) {
  return parseServerDate(value).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * The seller's subscription card: current plan, expiry, Pro duration
 * options, payment instructions, request submission and history.
 */
export default function PlanSection() {
  const { seller, refresh } = useAuth();

  const [requests, setRequests] = useState([]);
  const [selected, setSelected] = useState(1);
  const [paymentRef, setPaymentRef] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const fetchRequests = useCallback(() => {
    api.auth
      .upgradeRequests()
      .then(setRequests)
      .catch(() => setRequests([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchRequests();
  }, [fetchRequests]);

  const pendingRequest = requests.find((r) => r.status === "pending");
  const proActive =
    seller?.plan === "pro" &&
    (!seller?.plan_expires_at || new Date(seller.plan_expires_at) > new Date());
  const chosen = PRO_OPTIONS.find((o) => o.months === selected);

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    if (!paymentRef.trim()) {
      setError("Please enter your bKash/Nagad transaction ID so we can verify the payment.");
      return;
    }

    setSubmitting(true);
    try {
      await api.auth.requestUpgrade({
        months: selected,
        payment_reference: paymentRef.trim(),
      });
      setPaymentRef("");
      setSuccess(
        "Request sent! We'll verify your payment and activate Pro shortly — you'll get an email."
      );
      fetchRequests();
      refresh();
    } catch (err) {
      setError(getErrorMessage(err, "Could not send your request. Please try again."));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCancel() {
    const confirmed = window.confirm(
      "Cancel your Pro subscription?\n\n" +
        "• Pro ends immediately — unlimited orders stops now\n" +
        "• You'll return to the Free plan (50 orders per month)\n" +
        "• Payments already made are not refunded automatically — contact support if needed\n\n" +
        "If you just don't want to renew, you can simply do nothing instead."
    );
    if (!confirmed) return;

    setCancelling(true);
    setError(null);
    setSuccess(null);
    try {
      await api.auth.cancelSubscription();
      setSuccess("Subscription cancelled — you're back on the Free plan.");
      refresh();
      fetchRequests();
    } catch (err) {
      setError(getErrorMessage(err, "Could not cancel your subscription."));
    } finally {
      setCancelling(false);
    }
  }

  return (
    <section className="card">
      <h3>Plan &amp; subscription</h3>

      <div className="plan-status-row">
        <div>
          <span className={`plan-chip${proActive ? " plan-chip--pro" : ""}`}>
            {proActive ? (
              <>
                <Icon name="sparkles" size={14} className="plan-chip-icon" />
                Pro
              </>
            ) : (
              "Free"
            )}
          </span>
          {proActive && seller?.plan_expires_at && (
            <span className="plan-expiry">active until {formatDate(seller.plan_expires_at)}</span>
          )}
          {!proActive && seller?.plan === "pro" && seller?.plan_expires_at && (
            <span className="plan-expiry plan-expiry--expired">
              expired {formatDate(seller.plan_expires_at)} — renew below
            </span>
          )}
        </div>
        <span className="plan-limit-note">
          {proActive ? "Unlimited orders" : "50 orders per month"}
        </span>
      </div>

      {proActive && (
        <div className="cancel-row">
          <span className="cancel-note">
            You can cancel any time — or just let your paid time run out and do nothing.
          </span>
          <button
            type="button"
            className="cancel-button"
            onClick={handleCancel}
            disabled={cancelling}
          >
            {cancelling ? "Cancelling…" : "Cancel subscription"}
          </button>
        </div>
      )}

      {!proActive || seller?.plan_expires_at ? (
        <>
          <div className="plan-options">
            {PRO_OPTIONS.map((option) => (
              <button
                key={option.months}
                type="button"
                className={`plan-option${selected === option.months ? " plan-option--selected" : ""}`}
                onClick={() => setSelected(option.months)}
              >
                <span className="plan-option-months">
                  {option.months} {option.months === 1 ? "month" : "months"}
                </span>
                <span className="plan-option-price">৳{option.price.toLocaleString("en-IN")}</span>
                <span className="plan-option-note">{option.note}</span>
              </button>
            ))}
          </div>

          {pendingRequest ? (
            <div className="alert alert--success" role="status">
              You have a pending upgrade request ({pendingRequest.months}{" "}
              month{pendingRequest.months === 1 ? "" : "s"}, submitted{" "}
              {formatDate(pendingRequest.created_at)}). We&apos;ll review it shortly —
              no need to submit again.
            </div>
          ) : (
            <form onSubmit={handleSubmit} noValidate>
              <p className="payment-instructions">{PAYMENT_INSTRUCTIONS}</p>
              <div className="field">
                <label htmlFor="payment_ref">
                  bKash / Nagad transaction ID *
                </label>
                <input
                  id="payment_ref"
                  type="text"
                  placeholder="e.g. 8H2K9A1B2C"
                  value={paymentRef}
                  onChange={(e) => setPaymentRef(e.target.value)}
                />
              </div>

              {error && (
                <div className="alert alert--error" role="alert">
                  {error}
                </div>
              )}
              {success && (
                <div className="alert alert--success" role="status">
                  {success}
                </div>
              )}

              <button type="submit" className="button button--primary" disabled={submitting}>
                <Icon name="send" size={15} />
                {submitting
                  ? "Sending…"
                  : `Request Pro — ${chosen.months} month${chosen.months === 1 ? "" : "s"} (৳${chosen.price.toLocaleString("en-IN")})`}
              </button>
            </form>
          )}
        </>
      ) : (
        <p className="muted-note">
          You&apos;re on Pro with no expiry set — enjoy unlimited orders!
        </p>
      )}

      {!loading && requests.length > 0 && (
        <div className="upgrade-history">
          <h4>Request history</h4>
          <ul className="upgrade-history-list">
            {requests.map((request) => {
              const meta = STATUS_LABELS[request.status] ?? STATUS_LABELS.pending;
              return (
                <li key={request.id}>
                  <span>{request.months} month{request.months === 1 ? "" : "s"}</span>
                  <span className={`upgrade-status ${meta.className}`}>{meta.text}</span>
                  <span className="upgrade-history-date">
                    {formatDate(request.handled_at || request.created_at)}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}
