import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import Icon from "./icons";

/**
 * The free-plan allowance as segmented pips — one per free order.
 * Filled pips are spent; the count of hollow ones IS what's left.
 * Past 75% used the pips turn amber (a calm "getting close", never
 * an error tone). Pro (plan_limit == null) shows nothing.
 */
export function FreeOrderPips({ limit, used }) {
  if (limit == null || limit <= 0) return null;
  const warn = used / limit >= 0.75;
  const pips = Array.from({ length: limit }, (_, i) => i < used);

  return (
    <span
      className={`free-pips${warn ? " free-pips--warn" : ""}`}
      role="img"
      aria-label={`${limit - used} of ${limit} free orders left`}
    >
      {pips.map((filled, i) => (
        <span key={i} className={`free-pip${filled ? " free-pip--filled" : ""}`} />
      ))}
    </span>
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
