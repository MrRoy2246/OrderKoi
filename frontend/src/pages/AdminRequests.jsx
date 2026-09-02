import { useCallback, useEffect, useMemo, useState } from "react";
import { api, getErrorMessage } from "../api/client";
import Icon from "../components/icons";
import { EmptyState, SkeletonCard } from "../components/States";
import {
  formatRelativeTime,
  formatTk,
  parseServerDate,
} from "../utils/orderStatus";
import { proPriceFor } from "../utils/proPricing";

const STATUS_META = {
  pending: { label: "Pending", className: "upgrade-status--pending" },
  approved: { label: "Approved", className: "upgrade-status--approved" },
  rejected: { label: "Rejected", className: "upgrade-status--rejected" },
};

const EVENT_META = {
  subscribed: { label: "Subscribed", className: "upgrade-status--approved" },
  renewed: { label: "Renewed", className: "upgrade-status--renewed" },
  cancelled: { label: "Cancelled", className: "upgrade-status--rejected" },
};

function formatDate(value) {
  if (!value) return "—";
  return parseServerDate(value).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function formatDateTime(value) {
  if (!value) return "—";
  return parseServerDate(value).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Koi-tinted avatar with the store's initial — puts a face on each request. */
function StoreAvatar({ storeName }) {
  return (
    <span className="request-avatar" aria-hidden="true">
      {(storeName.trim()[0] || "?").toUpperCase()}
    </span>
  );
}

/**
 * The admin's money desk. Pending requests come first — each card shows
 * exactly what to verify (duration, the amount the seller should have
 * paid, the transaction ID) so checking against the bKash/Nagad
 * statement is a glance, not a hunt. Below, one calm row per store:
 * click it and a modal tells the shop's complete story — its upgrade
 * requests (approved, rejected, pending) and its full plan timeline.
 */
export default function AdminRequests() {
  const [requests, setRequests] = useState([]);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const fetchRequests = useCallback(() => {
    api.admin
      .upgradeRequests()
      .then(setRequests)
      .catch((err) => setError(getErrorMessage(err, "Could not load upgrade requests."))
      )
      .finally(() => setLoading(false));
    api.admin
      .subscriptionEvents()
      .then(setEvents)
      .catch(() => setEvents([])); // the ledger is supplementary
  }, []);

  useEffect(() => {
    fetchRequests();
  }, [fetchRequests]);

  async function handleAction(requestId, action) {
    setBusyId(requestId);
    setError(null);
    try {
      await api.admin.handleUpgradeRequest(requestId, action);
      fetchRequests();
    } catch (err) {
      setError(getErrorMessage(err, "Could not update the request."));
    } finally {
      setBusyId(null);
    }
  }

  const pending = requests.filter((r) => r.status === "pending");
  const expectedTotal = pending.reduce(
    (sum, r) => sum + (proPriceFor(r.months) ?? 0),
    0
  );

  // Store history grouped — one row per shop, holding BOTH its requests
  // and its plan changes. A store appears here if it has either. Rows
  // and modal both order by the shop's most recent activity.
  const [historyStore, setHistoryStore] = useState(null);
  const storeGroups = useMemo(() => {
    const groups = new Map();
    const ensure = (sellerId, storeName) => {
      if (!groups.has(sellerId)) {
        groups.set(sellerId, { sellerId, storeName, events: [], requests: [] });
      }
      return groups.get(sellerId);
    };
    for (const event of events) {
      ensure(event.seller_id, event.store_name).events.push(event);
    }
    for (const request of requests) {
      ensure(request.seller_id, request.store_name).requests.push(request);
    }
    return [...groups.values()]
      .map((group) => ({
        ...group,
        // newest first within each list (requests arrive pending-first)
        requests: [...group.requests].sort(
          (a, b) => parseServerDate(b.created_at) - parseServerDate(a.created_at)
        ),
      }))
      .sort(
        (a, b) =>
          parseServerDate(b.requests[0]?.created_at ?? b.events[0]?.created_at ?? 0) -
          parseServerDate(a.requests[0]?.created_at ?? a.events[0]?.created_at ?? 0)
      );
  }, [events, requests]);

  // Escape closes the history modal
  useEffect(() => {
    if (historyStore === null) return undefined;
    function handleKeyDown(event) {
      if (event.key === "Escape") setHistoryStore(null);
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [historyStore]);

  if (loading) {
    return (
      <div className="admin-page">
        <div className="request-list" aria-hidden="true">
          <SkeletonCard lines={2} />
          <SkeletonCard lines={2} />
        </div>
      </div>
    );
  }

  return (
    <div className="admin-page">
      <header className="page-header">
        <h1>Upgrade Requests</h1>
        <p>
          {pending.length > 0
            ? `${pending.length} waiting · ${formatTk(expectedTotal)} expected — verify each payment against your bKash/Nagad statement, then approve.`
            : "Sellers who paid and want Pro. New requests appear here the moment a seller submits one."}
        </p>
      </header>

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}

      {pending.length === 0 ? (
        <EmptyState icon="check" title="No pending requests">
          <p>You're all caught up — nothing waiting for review.</p>
        </EmptyState>
      ) : (
        <div className="request-list">
          {pending.map((request) => {
            const expected = proPriceFor(request.months);
            return (
              <article key={request.id} className="request-card request-card--pending">
                <div className="request-seller">
                  <StoreAvatar storeName={request.store_name} />
                  <div className="request-seller-info">
                    <strong>{request.store_name}</strong>
                    <span className="request-card-email">{request.seller_email}</span>
                  </div>
                </div>

                <div className="request-terms">
                  <span className="request-duration">
                    <Icon name="sparkles" size={14} />
                    {request.months} month{request.months === 1 ? "" : "s"}
                  </span>
                  <span className="request-amount">
                    {expected ? formatTk(expected) : "—"}
                  </span>
                  <span className="request-amount-label">should have paid</span>
                </div>

                <div className="request-proof">
                  <span className="request-trx">
                    TrxID <code>{request.payment_reference || "not provided"}</code>
                  </span>
                  <span className="request-card-date">
                    requested {formatDate(request.created_at)} ·{" "}
                    {formatRelativeTime(request.created_at)}
                  </span>
                </div>

                <div className="request-card-actions">
                  <button
                    type="button"
                    className="button button--primary button--small"
                    disabled={busyId === request.id}
                    onClick={() => handleAction(request.id, "approve")}
                  >
                    <Icon name="check" size={14} />
                    {busyId === request.id ? "…" : "Approve"}
                  </button>
                  <button
                    type="button"
                    className="button button--outline button--small"
                    disabled={busyId === request.id}
                    onClick={() => handleAction(request.id, "reject")}
                  >
                    <Icon name="x" size={14} />
                    Reject
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <section className="card">
        <div className="card-header-row">
          <h3>Store history</h3>
          <span className="admin-mix-total">
            {storeGroups.length > 0
              ? `${storeGroups.length} store${storeGroups.length === 1 ? "" : "s"} · click one for its requests and plan changes`
              : "requests and plan changes per store"}
          </span>
        </div>
        {storeGroups.length === 0 ? (
          <p className="muted-note">
            A store appears here with its first upgrade request or plan change.
          </p>
        ) : (
          <ul className="ledger-list">
            {storeGroups.map((group) => {
              // The shop's latest activity of any kind — drives the chip
              const candidates = [
                ...group.events.map((e) => ({
                  at: e.created_at,
                  meta: EVENT_META[e.event] ?? {
                    label: e.event,
                    className: "upgrade-status--pending",
                  },
                })),
                ...group.requests.map((r) => ({
                  at: r.created_at,
                  meta: STATUS_META[r.status] ?? STATUS_META.pending,
                })),
              ].sort((a, b) => parseServerDate(b.at) - parseServerDate(a.at));
              const latest = candidates[0];
              return (
                <li key={group.sellerId} className="ledger-store">
                  <button
                    type="button"
                    className="ledger-store-header"
                    onClick={() => setHistoryStore(group)}
                  >
                    <span className="ledger-store-name">{group.storeName}</span>
                    <span className={`upgrade-status ${latest.meta.className}`}>
                      {latest.meta.label}
                    </span>
                    <span className="ledger-store-meta">
                      {group.requests.length > 0 &&
                        `${group.requests.length} request${group.requests.length === 1 ? "" : "s"} · `}
                      {group.events.length} change{group.events.length === 1 ? "" : "s"}
                    </span>
                    <Icon
                      name="chevronRight"
                      size={15}
                      className="ledger-caret"
                    />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {historyStore && (
        <div
          className="modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={`Store history — ${historyStore.storeName}`}
        >
          <div className="modal modal--ledger">
            <button
              type="button"
              className="modal-close modal-close--float"
              onClick={() => setHistoryStore(null)}
              aria-label="Close"
            >
              <Icon name="x" size={16} />
            </button>

            {/* Store identity — centered, so the modal opens with a face */}
            <div className="ledger-modal-head">
              <span className="request-avatar request-avatar--lg" aria-hidden="true">
                {(historyStore.storeName.trim()[0] || "?").toUpperCase()}
              </span>
              <h2>{historyStore.storeName}</h2>
              <div className="ledger-modal-badges">
                <span className="ledger-modal-count">
                  {historyStore.requests.length} request
                  {historyStore.requests.length === 1 ? "" : "s"} ·{" "}
                  {historyStore.events.length} plan change
                  {historyStore.events.length === 1 ? "" : "s"} · newest first
                </span>
              </div>
            </div>

            <div className="modal-form">
              {historyStore.requests.length > 0 && (
                <div className="ledger-modal-section">
                  <h4 className="ledger-modal-section-title">Upgrade requests</h4>
                  <ul className="ledger-request-list">
                    {historyStore.requests.map((request) => {
                      const meta = STATUS_META[request.status] ?? STATUS_META.pending;
                      const expected = proPriceFor(request.months);
                      return (
                        <li key={request.id} className="ledger-request-item">
                          <span className={`upgrade-status ${meta.className}`}>
                            {meta.label}
                          </span>
                          <div className="ledger-request-body">
                            <span className="ledger-request-title">
                              {request.months} month{request.months === 1 ? "" : "s"}
                              {expected ? ` · ${formatTk(expected)}` : ""}
                              {request.status === "approved" && request.granted_until
                                ? ` · Pro until ${formatDate(request.granted_until)}`
                                : ""}
                            </span>
                            <span className="ledger-request-meta">
                              TrxID {request.payment_reference || "not provided"} ·
                              requested {formatDate(request.created_at)}
                              {request.handled_at
                                ? ` · decided ${formatDate(request.handled_at)}`
                                : ""}
                            </span>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}

              {historyStore.events.length > 0 && (
                <div className="ledger-modal-section">
                  <h4 className="ledger-modal-section-title">Plan timeline</h4>
                  <ol className="ledger-timeline ledger-timeline--modal">
                    {historyStore.events.map((event) => {
                      const meta = EVENT_META[event.event] ?? {
                        label: event.event,
                        className: "upgrade-status--pending",
                      };
                      return (
                        <li key={event.id} className="ledger-event">
                          <span
                            className={`ledger-dot ledger-dot--${event.event}`}
                            aria-hidden="true"
                          />
                          <div className="ledger-event-body">
                            <span className="ledger-event-title">
                              {meta.label}
                              {event.months
                                ? ` · ${event.months} month${event.months === 1 ? "" : "s"}`
                                : ""}
                            </span>
                            {event.note && (
                              <span className="ledger-event-note">{event.note}</span>
                            )}
                          </div>
                          <span className="ledger-event-date">
                            {formatDateTime(event.created_at)}
                          </span>
                        </li>
                      );
                    })}
                  </ol>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
