import { STATUS_META } from "../utils/orderStatus";

/** Workflow order — placed → delivered, cancelled last. Shared by this
 * component and the pages that compute status totals themselves. */
export const STATUS_ORDER = ["placed", "confirmed", "shipped", "delivered", "cancelled"];

/**
 * Status breakdown — a composition rail (one pill, one segment per
 * status, 2px of surface between fills) plus a value list below it.
 * Identity is never color-alone: every row carries the status name,
 * count, and share. Shared by the seller dashboard and the admin
 * shop-detail page so both read the same way.
 *
 * counts: { placed: n, confirmed: n, ... } — zero statuses are omitted.
 */
export default function StatusBreakdown({ counts }) {
  const active = STATUS_ORDER.filter((s) => (counts?.[s] ?? 0) > 0);
  const total = active.reduce((sum, s) => sum + counts[s], 0);

  if (total === 0) {
    return <p className="muted-note">No orders in this period.</p>;
  }

  const pct = (n) => (total > 0 ? Math.round((n / total) * 100) : 0);

  return (
    <div className="statusbreak">
      {/* Composition rail — the whole window's orders in one glance.
          Decorative: the rows below carry the exact values. */}
      <div className="statusbreak-rail" aria-hidden="true">
        {active.map((s) => (
          <span
            key={s}
            className={`statusbreak-seg st-fill--${s}`}
            style={{ width: `${(counts[s] / total) * 100}%` }}
          />
        ))}
      </div>

      <ul className="statusbreak-list">
        {active.map((s) => {
          const meta = STATUS_META[s];
          return (
            <li key={s} className="statusbreak-row">
              <span className="statusbreak-name">
                <span className={`statusbreak-dot st-fill--${s}`} aria-hidden="true" />
                {meta?.label ?? s}
              </span>
              <span className="statusbreak-nums">
                <span className="statusbreak-count">{counts[s]}</span>
                <span className="statusbreak-pct">{pct(counts[s])}%</span>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
