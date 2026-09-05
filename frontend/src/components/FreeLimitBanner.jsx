import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import Icon from "./icons";

/**
 * The free-plan allowance as a refined usage meter: a slim bar with
 * hairline tick marks at every 5th order, a gradient fill, and the
 * remaining count as a right-aligned chip. Past 75% used the fill
 * turns amber (a calm heads-up, never an alarm). Pro
 * (plan_limit == null) shows nothing.
 */
export function FreeOrderMeter({ limit, used, compact = false }) {
  if (limit == null || limit <= 0) return null;
  const remaining = Math.max(limit - used, 0);
  const warn = used / limit >= 0.75;
  const pct = Math.min(Math.max((used / limit) * 100, 0), 100);

  // Tick marks every 5th order — subtle orientation, not a grid
  const tickIndexes = [];
  for (let i = 5; i < limit; i += 5) tickIndexes.push(i);

  return (
    <div
      className={`free-meter${warn ? " free-meter--warn" : ""}${compact ? " free-meter--compact" : ""}`}
      role="status"
      aria-label={`${remaining} of ${limit} free orders left`}
    >
      {!compact && (
        <div className="free-meter-head">
          <span className="free-meter-label">Free orders</span>
          <span className="free-meter-chip">
            {remaining === 1 ? "1 left" : `${remaining} left`}
          </span>
        </div>
      )}
      <div className="free-meter-track">
        <div className="free-meter-fill" style={{ width: `${pct}%` }} />
        {tickIndexes.map((i) => (
          <span
            key={i}
            className={`free-meter-tick${i <= used ? " free-meter-tick--passed" : ""}`}
            style={{ left: `${(i / limit) * 100}%` }}
          />
        ))}
      </div>
      {compact ? (
        <span className="free-meter-note">
          {remaining === 1 ? "1 free order left" : `${remaining} free orders left`}
          <span className="free-meter-note-detail"> · {used} of {limit}</span>
        </span>
      ) : (
        <span className="free-meter-note">
          {used} of {limit} used
          {warn && <span className="free-meter-note-detail"> — almost there</span>}
        </span>
      )}
    </div>
  );
}

/**
 * The focused "you've hit the free limit" banner. Shown on the seller's
 * Dashboard and Orders pages while the account is on Free and the
 * one-time order allowance is used up — the store is effectively
 * paused for new orders until Pro is activated.
 *
 * Data comes from the stats summary (month_orders / plan_limit), which
 * every dashboard already loads — no extra request.
 */
export function FreeLimitBanner({ stats }) {
  const { seller } = useAuth();
  if (!stats || stats.plan_limit == null) return null;
  if (stats.month_orders < stats.plan_limit) return null;

  return (
    <div className="free-limit-banner" role="alert">
      <div className="free-limit-icon">
        <Icon name="sparkles" size={20} />
      </div>
      <div className="free-limit-copy">
        <strong>
          {seller?.plan === "pro"
            ? "Pro expired — orders are paused"
            : `You've used all ${stats.plan_limit} free orders`}
        </strong>
        <p>
          Your store is paused for new orders — customers can't submit
          through your form link right now. Everything you've built stays
          exactly as it is.
        </p>
      </div>
      <Link to="/dashboard/settings" className="button button--primary">
        <Icon name="sparkles" size={15} />
        Upgrade to Pro
      </Link>
    </div>
  );
}

export default FreeLimitBanner;
