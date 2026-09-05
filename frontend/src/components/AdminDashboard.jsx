import { useNavigate } from "react-router-dom";
import Icon from "./icons";
import { Sparkline } from "./Charts";
import { formatRelativeTime, parseServerDate } from "../utils/orderStatus";

/**
 * KPI card — the dashboard's headline metrics. Structure: icon, label,
 * main value, contextual hint, optional sparkline. Values are always
 * real API data; where the backend provides no comparison figure, the
 * hint carries context instead (no invented percentages).
 *
 * Navigates when `to` is given — the card drills into the page behind
 * the number.
 */
export function KpiCard({ icon, label, value, hint, accent, to, title, spark, sparkColor }) {
  const navigate = useNavigate();
  const content = (
    <>
      <div className="kpi-head">
        <span className={`kpi-icon kpi-icon--${accent}`}>
          <Icon name={icon} size={18} />
        </span>
        <span className="kpi-label">{label}</span>
      </div>
      <div className="kpi-body">
        <span className="kpi-value">{value}</span>
        {spark && spark.length > 1 && (
          <Sparkline data={spark} color={sparkColor || "var(--primary)"} />
        )}
      </div>
      {hint && <p className="kpi-hint">{hint}</p>}
      {to && (
        <span className="kpi-go" aria-hidden="true">
          <Icon name="arrowRight" size={15} />
        </span>
      )}
    </>
  );

  if (to) {
    return (
      <article
        className="kpi-card kpi-card--clickable"
        role="link"
        tabIndex={0}
        title={title || `Open ${label}`}
        onClick={() => navigate(to)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") navigate(to);
        }}
      >
        {content}
      </article>
    );
  }
  return <article className="kpi-card">{content}</article>;
}

/**
 * Recent activity — derived from the real subscription ledger
 * (`api.admin.subscriptionEvents()`), not a fabricated feed. Each row:
 * dot, message, store, relative time with the exact date on hover.
 */
const EVENT_META = {
  subscribed: { verb: "upgraded to Pro", tone: "pro" },
  renewed: { verb: "renewed Pro", tone: "pro" },
  cancelled: { verb: "was downgraded from Pro", tone: "down" },
};

export function ActivityFeed({ events, emptyNote = "No subscription activity yet." }) {
  if (!events || events.length === 0) {
    return <p className="muted-note">{emptyNote}</p>;
  }
  return (
    <ul className="activity-feed">
      {events.map((event) => {
        const meta = EVENT_META[event.event] ?? { verb: event.event, tone: "down" };
        const duration =
          event.months
            ? ` · ${event.months} month${event.months === 1 ? "" : "s"}${event.comp ? ", free" : ""}`
            : "";
        return (
          <li key={`${event.id}`} className="activity-item">
            <span className={`activity-dot activity-dot--${meta.tone}`} aria-hidden="true" />
            <div className="activity-body">
              <p className="activity-text">
                <span className="activity-store">{event.store_name}</span> {meta.verb}
                {duration}
              </p>
              <span className="activity-time" title={formatExact(event.created_at)}>
                {formatRelativeTime(event.created_at)}
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function formatExact(iso) {
  if (!iso) return "—";
  return parseServerDate(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
