import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import Icon from "../components/icons";
import { ErrorState, SkeletonCard } from "../components/States";
import StatusBadge from "../components/StatusBadge";
import StatusTimeline from "../components/StatusTimeline";
import {
  NEXT_STATUSES,
  STATUS_META,
  formatDateTime,
  formatTk,
  trackingUrl,
} from "../utils/orderStatus";

/**
 * Order detail — one order, everything the seller can do with it:
 * edit customer/items (locked once delivered/cancelled), advance the
 * status along the backend's workflow (valid next steps only — the
 * server enforces the same transitions), copy the customer's tracking
 * link, and delete (only while still 'placed'). Status changes email
 * the customer server-side.
 */
export default function OrderDetail() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const fetchOrder = useCallback(async () => {
    try {
      const data = await api.orders.get(id);
      setOrder(data);
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err, "Could not load this order."));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    setLoading(true);
    fetchOrder();
  }, [fetchOrder]);

  async function handleStatusChange(newStatus) {
    const label = STATUS_META[newStatus]?.label ?? newStatus;
    if (newStatus === "cancelled" && !window.confirm("Cancel this order? This cannot be undone.")) {
      return;
    }

    setBusy(true);
    setActionError(null);
    try {
      const updated = await api.orders.updateStatus(id, newStatus);
      setOrder(updated);
    } catch (err) {
      setActionError(getErrorMessage(err, `Could not mark as ${label.toLowerCase()}.`));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm("Delete this order permanently?")) return;
    setBusy(true);
    try {
      await api.orders.remove(id);
      navigate("/dashboard/orders", { replace: true });
    } catch (err) {
      setActionError(getErrorMessage(err, "Could not delete this order."));
      setBusy(false);
    }
  }

  async function handleCopyLink() {
    try {
      await navigator.clipboard.writeText(trackingUrl(order.tracking_code));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.open(trackingUrl(order.tracking_code), "_blank");
    }
  }

  if (loading) {
    return (
      <div className="order-detail-page">
        <div className="skeleton-block" aria-hidden="true">
          <SkeletonCard />
          <SkeletonCard lines={3} />
          <SkeletonCard lines={3} />
        </div>
      </div>
    );
  }

  if (error && !order) {
    return (
      <div className="orders-page">
        <ErrorState message={error} onRetry={fetchOrder} />
        <Link to="/dashboard/orders" className="button button--outline">
          <Icon name="chevronLeft" size={16} />
          Back to orders
        </Link>
      </div>
    );
  }

  const nextStatuses = NEXT_STATUSES[order.status] ?? [];

  return (
    <div className="order-detail-page">
      <nav className="breadcrumb">
        <Link to="/dashboard/orders">
          <Icon name="chevronLeft" size={14} />
          Orders
        </Link>
      </nav>

      <header className="page-header page-header--row">
        <div>
          <h1 className="order-detail-title">
            Order #{order.order_number}
            <StatusBadge status={order.status} />
          </h1>
          <p className="td-muted">
            Created {formatDateTime(order.created_at)} · Updated {formatDateTime(order.updated_at)}
          </p>
        </div>
        <div className="order-detail-actions">
          <button type="button" className="button button--outline" onClick={handleCopyLink}>
            <Icon name={copied ? "check" : "link"} size={16} />
            {copied ? "Copied" : "Copy tracking link"}
          </button>
          {order.status === "placed" && (
            <button
              type="button"
              className="button button--danger-outline"
              onClick={handleDelete}
              disabled={busy}
            >
              <Icon name="trash" size={16} />
              Delete
            </button>
          )}
        </div>
      </header>

      {actionError && (
        <div className="alert alert--error" role="alert">
          {actionError}
        </div>
      )}

      {nextStatuses.length > 0 ? (
        <section className="card status-actions">
          <h3>Move this order forward</h3>
          <div className="status-action-buttons">
            {nextStatuses.map((status) => (
              <button
                key={status}
                type="button"
                className={`button ${status === "cancelled" ? "button--danger-outline" : "button--primary"}`}
                onClick={() => handleStatusChange(status)}
                disabled={busy}
              >
                <Icon name={STATUS_META[status].icon} size={16} />
                Mark as {STATUS_META[status].label}
              </button>
            ))}
          </div>
        </section>
      ) : (
        <section className="card status-actions status-actions--final">
          <h3>
            {order.status === "delivered"
              ? "Delivered — nothing left to do!"
              : "This order was cancelled."}
          </h3>
          <p className="td-muted">
            {order.status === "delivered"
              ? "The customer saw the final status on their tracking link."
              : "The customer saw the cancellation on their tracking link."}
          </p>
        </section>
      )}

      <div className="order-detail-grid">
        <section className="card">
          <h3>Customer</h3>
          <dl className="detail-list">
            <div>
              <dt>
                <Icon name="users" size={14} /> Name
              </dt>
              <dd>{order.customer_name}</dd>
            </div>
            <div>
              <dt>
                <Icon name="phone" size={14} /> Phone
              </dt>
              <dd className="td-mono">{order.customer_phone}</dd>
            </div>
            <div>
              <dt>
                <Icon name="mail" size={14} /> Email
              </dt>
              <dd>
                {order.customer_email ? (
                  <a href={`mailto:${order.customer_email}`}>{order.customer_email}</a>
                ) : (
                  "—"
                )}
              </dd>
            </div>
            <div>
              <dt>
                <Icon name="mapPin" size={14} /> Delivery address
              </dt>
              <dd>{order.customer_address || "—"}</dd>
            </div>
            <div>
              <dt>
                <Icon name="note" size={14} /> Notes
              </dt>
              <dd>{order.notes || "—"}</dd>
            </div>
          </dl>
        </section>

        <section className="card">
          <h3>Items</h3>
          <table className="items-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Qty</th>
                <th>Price</th>
                <th>Subtotal</th>
              </tr>
            </thead>
            <tbody>
              {order.items.map((item, index) => (
                <tr key={index}>
                  <td className="td-strong">{item.name}</td>
                  <td>{item.quantity}</td>
                  <td>{formatTk(item.price)}</td>
                  <td className="td-strong">{formatTk(item.quantity * item.price)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={3}>Total</td>
                <td className="td-strong">{formatTk(order.total_price)}</td>
              </tr>
            </tfoot>
          </table>
          <p className="tracking-code-note">
            Tracking code: <code>{order.tracking_code}</code>
          </p>
        </section>
      </div>

      <section className="card">
        <h3>Timeline</h3>
        <StatusTimeline status={order.status} history={order.status_history} />
      </section>
    </div>
  );
}
