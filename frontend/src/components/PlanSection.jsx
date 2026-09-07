import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { api, getErrorMessage } from "../api/client";
import Icon from "./icons";
import { parseServerDate } from "../utils/orderStatus";
import { fetchProOptions, PRO_OPTIONS_FALLBACK } from "../utils/proPricing";

/** Where sellers send payment. */
const PAYMENT_INSTRUCTIONS =
  "Send the amount via bKash to 01736060259 (Personal), then submit " +
  "the request below with your transaction ID. We'll activate Pro after " +
  "verifying the payment (usually within a few hours).";

/** Must match the backend's free_plan_orders setting. */
const FREE_PLAN_ORDERS = 15;

const STATUS_LABELS = {
  pending: { text: "Pending review", className: "upgrade-status--pending" },
  approved: { text: "Approved", className: "upgrade-status--approved" },
  rejected: { text: "Rejected", className: "upgrade-status--rejected" },
};

/** Subscription ledger events, phrased for the seller's own history. */
const EVENT_LABELS = {
  subscribed: { text: "Pro activated", className: "upgrade-status--approved" },
  renewed: { text: "Pro renewed", className: "upgrade-status--approved" },
  cancelled: { text: "Pro cancelled", className: "upgrade-status--rejected" },
};

function formatDateTime(value) {
  return parseServerDate(value).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

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
  const [events, setEvents] = useState([]);
  const [selected, setSelected] = useState(1);
  const [paymentRef, setPaymentRef] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [proOptions, setProOptions] = useState(PRO_OPTIONS_FALLBACK);

  // Live prices from the backend (env-driven there) — fallback keeps
  // the card rendered if the fetch fails
  useEffect(() => {
    let cancelled = false;
    fetchProOptions().then((options) => {
      if (!cancelled) setProOptions(options);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const fetchRequests = useCallback(() => {
    api.auth
      .upgradeRequests()
      .then(setRequests)
      .catch(() => setRequests([]))
      .finally(() => setLoading(false));
    api.auth
      .subscriptionHistory()
      .then(setEvents)
      .catch(() => setEvents([]));
  }, []);

  useEffect(() => {
    fetchRequests();
  }, [fetchRequests]);

  const pendingRequest = requests.find((r) => r.status === "pending");
  const proActive =
    seller?.plan === "pro" &&
    (!seller?.plan_expires_at || new Date(seller.plan_expires_at) > new Date());
  const chosen = proOptions.find((o) => o.months === selected) ?? proOptions[0];

  // One timeline: upgrade requests + subscription events (activation,
  // renewal, cancellation), newest first. An approved request and its
  // ledger event (Pro activated/renewed) are the SAME moment recorded
  // by two systems — show it once, as the richer event row. Pending
  // and rejected requests have no event, so they stand alone.
  const handledRequestIds = new Set(
    events
      .filter((e) => e.event === "subscribed" || e.event === "renewed")
      .map((e) => e.request_id)
      .filter((id) => id != null)
  );

  const history = [
    ...requests
      .filter((r) => !handledRequestIds.has(r.id))
      .map((r) => ({
        key: `request-${r.id}`,
        when: r.handled_at || r.created_at,
        left: `${r.months} month${r.months === 1 ? "" : "s"}`,
        status: STATUS_LABELS[r.status] ?? STATUS_LABELS.pending,
        date: r.handled_at || r.created_at,
      })),
    ...events.map((e) => {
      const label = EVENT_LABELS[e.event] ?? {
        text: e.event,
        className: "upgrade-status--pending",
      };
      return {
        key: `event-${e.id}`,
        when: e.created_at,
        left: e.months ? `${e.months} month${e.months === 1 ? "" : "s"}` : label.text,
        status: label,
        date: e.created_at,
      };
    }),
  ].sort((a, b) => new Date(b.when) - new Date(a.when));

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    if (!paymentRef.trim()) {
      setError("Please enter your bKash transaction ID so we can verify the payment.");
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
        "• Your Pro status ends immediately\n" +
        `• Your account returns to the Free plan (${FREE_PLAN_ORDERS} lifetime free orders)\n` +
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
          {proActive
            ? "Unlimited orders"
            : `Free plan — first ${FREE_PLAN_ORDERS} orders, unlimited on Pro`}
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
            {proOptions.map((option) => (
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
                  bKash transaction ID *
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
          You&apos;re on Pro with no expiry set — thank you for supporting the platform!
        </p>
      )}

      {!loading && history.length > 0 && (
        <div className="upgrade-history">
          <h4>Subscription history</h4>
          <ul className="upgrade-history-list">
            {history.map((entry) => (
              <li key={entry.key}>
                <span>{entry.left}</span>
                <span className={`upgrade-status ${entry.status.className}`}>
                  {entry.status.text}
                </span>
                <span className="upgrade-history-date">{formatDateTime(entry.date)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
