import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import Icon from "../components/icons";
import Logo from "../components/Logo";
import { SkeletonCard } from "../components/States";
import StatusTimeline from "../components/StatusTimeline";
import { STATUS_META, formatDateTime } from "../utils/orderStatus";

function CancelledNotice({ history }) {
  const lastChange = history[history.length - 1];
  return (
    <div className="cancelled-notice" role="alert">
      <strong>
        <Icon name="x" size={16} />
        This order was cancelled
      </strong>
      {lastChange && <p>Cancelled on {formatDateTime(lastChange.changed_at)}</p>}
      <p>If you think this is a mistake, please contact the store.</p>
    </div>
  );
}

/** Small lookup form — used on the /track landing and on errors. */
function CodeForm({ initialCode = "" }) {
  const [code, setCode] = useState(initialCode);
  const navigate = useNavigate();

  function handleSubmit(event) {
    event.preventDefault();
    const clean = code.trim().toUpperCase();
    if (clean) navigate(`/track/${encodeURIComponent(clean)}`);
  }

  return (
    <form className="track-form" onSubmit={handleSubmit}>
      <input
        type="text"
        className="track-input"
        placeholder="Enter tracking code, e.g. A1B2C3D4"
        aria-label="Tracking code"
        value={code}
        maxLength={12}
        onChange={(e) => setCode(e.target.value.toUpperCase())}
      />
      <button type="submit" className="button button--primary">
        <Icon name="search" size={16} />
        Track
      </button>
    </form>
  );
}

export default function Track() {
  const { code } = useParams();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchOrder = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.tracking.get(code);
      setOrder(data);
    } catch (err) {
      if (err.status === 404) {
        setError("not_found");
      } else {
        setError(getErrorMessage(err, "Could not reach the server. Please try again."));
      }
    } finally {
      setLoading(false);
    }
  }, [code]);

  useEffect(() => {
    fetchOrder();
  }, [fetchOrder]);

  return (
    <div className="track-page">
      <div className="track-card">
        {loading && (
          <div className="track-loading" aria-hidden="true">
            <SkeletonCard lines={4} />
          </div>
        )}

        {!loading && error === "not_found" && (
          <div className="track-status">
            <span className="track-status-icon" aria-hidden="true">
              <Icon name="search" size={26} />
            </span>
            <h1>Order not found</h1>
            <p>Check the tracking code and try again. Codes look like <code>A1B2C3D4</code>.</p>
            <CodeForm initialCode={code} />
          </div>
        )}

        {!loading && error && error !== "not_found" && (
          <div className="track-status">
            <span className="track-status-icon track-status-icon--error" aria-hidden="true">
              <Icon name="alertCircle" size={26} />
            </span>
            <h1>Something went wrong</h1>
            <p>{error}</p>
            <button type="button" className="button button--outline" onClick={fetchOrder}>
              <Icon name="refresh" size={16} />
              Try again
            </button>
          </div>
        )}

        {!loading && order && (
          <>
            <header className="track-header">
              <h1>{order.store_name}</h1>
              <p className="track-order-line">
                Order <strong>#{order.order_number}</strong> for{" "}
                <strong>{order.customer_name}</strong>
              </p>
            </header>

            {order.status === "cancelled" ? (
              <CancelledNotice history={order.status_history} />
            ) : (
              <section aria-label="Order progress">
                <div className={`track-current track-current--${order.status}`}>
                  <span className="track-current-dot" aria-hidden="true" />
                  {STATUS_META[order.status].label}
                </div>
                <StatusTimeline status={order.status} history={order.status_history} />
              </section>
            )}

            <section className="track-meta">
              <div>
                <dt>Order placed</dt>
                <dd>{formatDateTime(order.created_at)}</dd>
              </div>
              <div>
                <dt>Last update</dt>
                <dd>{formatDateTime(order.updated_at)}</dd>
              </div>
              <div>
                <dt>Tracking code</dt>
                <dd>
                  <code>{code?.toUpperCase()}</code>
                </dd>
              </div>
            </section>

            <p className="track-note">
              Questions about this order? Contact {order.store_name} directly.
            </p>
          </>
        )}

        <footer className="track-footer">
          <Link to="/">
            <Logo size={18} />
            <span>Powered by OrderKoi</span>
          </Link>
        </footer>
      </div>
    </div>
  );
}
