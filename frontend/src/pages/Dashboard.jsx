import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import Icon from "../components/icons";
import { SkeletonCard } from "../components/States";
import { ordersLink } from "../utils/businessDate";
import { STATUS_META, formatTk, parseServerDate } from "../utils/orderStatus";

const RANGE_OPTIONS = [
  { value: "today", label: "Today" },
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
  { value: "all", label: "All time" },
  { value: "custom", label: "Custom" },
];

const DAY_MS = 24 * 60 * 60 * 1000;

function formatDate(value) {
  if (!value) return null;
  return parseServerDate(value).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

function toDateInput(date) {
  return date.toISOString().slice(0, 10); // YYYY-MM-DD
}

/**
 * The subscription card — the seller always knows exactly where they
 * stand: plan, expiry date, days remaining, and (on Free) a live
 * usage meter against the monthly order cap. Clicking it opens the
 * upgrade/renew options in Settings.
 */
function SubscriptionCard({ seller, stats }) {
  const pro = seller?.plan === "pro";
  const expiry = seller?.plan_expires_at ? parseServerDate(seller.plan_expires_at) : null;
  const daysLeft = expiry ? Math.ceil((expiry - new Date()) / DAY_MS) : null;
  const active = pro && (!expiry || daysLeft > 0);

  let headline, subline, meter;

  if (active && !expiry) {
    headline = "Pro — unlimited";
    subline = "No expiry — enjoy unlimited orders.";
  } else if (active) {
    headline = "Pro";
    subline = `Unlimited orders until ${formatDate(expiry)}`;
    meter = {
      label: daysLeft === 1 ? "1 day left" : `${daysLeft} days left`,
      detail: `expires ${formatDate(expiry)}`,
      pct: Math.min(Math.max((daysLeft / 365) * 100, 4), 100),
      tone: daysLeft <= 7 ? "danger" : "pro",
    };
  } else if (pro && expiry) {
    headline = "Pro expired";
    subline = `Your subscription ended ${formatDate(expiry)} — you're back on Free limits.`;
  } else {
    headline = "Free plan";
    subline = "Up to 50 orders per month";
    const used = stats?.month_orders ?? 0;
    const limit = stats?.plan_limit ?? 50;
    meter = {
      label: `${used} / ${limit} orders this month`,
      detail: used >= limit ? "limit reached — upgrade to keep selling" : `${limit - used} left`,
      pct: Math.min((used / limit) * 100, 100),
      tone: used >= limit ? "danger" : used / limit >= 0.8 ? "warn" : "free",
    };
  }

  return (
    <Link to="/dashboard/settings" className="subscription-card" title="Manage your subscription">
      <div className="subscription-info">
        <span className={`subscription-plan${active ? " subscription-plan--pro" : ""}`}>
          {active && <Icon name="sparkles" size={16} className="subscription-plan-icon" />}
          {headline}
        </span>
        <span className="subscription-subline">{subline}</span>
        {meter && (
          <div className={`subscription-meter subscription-meter--${meter.tone}`}>
            <div className="subscription-meter-track">
              <div className="subscription-meter-fill" style={{ width: `${meter.pct}%` }} />
            </div>
            <span className="subscription-meter-label">
              {meter.label} <span className="subscription-meter-detail">· {meter.detail}</span>
            </span>
          </div>
        )}
      </div>
      <span className="subscription-action" aria-hidden="true">
        {active ? "Manage / renew" : "Upgrade to Pro"}
        <Icon name="arrowRight" size={15} />
      </span>
    </Link>
  );
}

/** Pure-CSS bar chart — one bar per day of the selected range. */
function DailyChart({ daily }) {
  const max = Math.max(...daily.map((d) => d.count), 1);
  // Thin out labels so even a year of bars stays readable
  const labelEvery = Math.max(1, Math.ceil(daily.length / 10));

  return (
    <div className="chart" role="img" aria-label="Orders per day">
      {daily.map((day, index) => {
        const date = new Date(`${day.date}T00:00:00`);
        const label = date.toLocaleDateString(undefined, {
          day: "numeric",
          month: "short",
        });
        return (
          <div
            key={day.date}
            className="chart-bar-wrap"
            title={`${label}: ${day.count} order${day.count === 1 ? "" : "s"}`}
          >
            <span className="chart-count">{day.count > 0 ? day.count : ""}</span>
            <div
              className={`chart-bar${day.count > 0 ? "" : " chart-bar--empty"}`}
              style={{ height: `${Math.max((day.count / max) * 100, day.count > 0 ? 6 : 2)}%` }}
            />
            <span className="chart-label">
              {index % labelEvery === 0 || index === daily.length - 1
                ? label.split(" ")[0]
                : ""}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function StatCard({ icon, label, value, accent, to, title }) {
  const navigate = useNavigate();
  const content = (
    <>
      <span className={`stat-icon stat-icon--${accent}`}>
        <Icon name={icon} size={21} />
      </span>
      <div>
        <span className="stat-value">{value}</span>
        <span className="stat-label">{label}</span>
      </div>
      {to && (
        <span className="stat-go" aria-hidden="true">
          <Icon name="arrowRight" size={16} />
        </span>
      )}
    </>
  );

  if (to) {
    return (
      <article
        className="stat-card stat-card--clickable"
        role="link"
        tabIndex={0}
        title={title}
        onClick={() => navigate(to)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") navigate(to);
        }}
      >
        {content}
      </article>
    );
  }
  return <article className="stat-card">{content}</article>;
}

/** Custom date-range picker — appears when the "Custom" tab is active. */
function CustomRangePanel({ start, end, onStart, onEnd, onApply, error }) {
  const today = toDateInput(new Date());
  return (
    <div className="custom-range-panel">
      <div className="custom-range-field">
        <label htmlFor="range_start">From</label>
        <input
          id="range_start"
          type="date"
          max={end || today}
          value={start}
          onChange={(e) => onStart(e.target.value)}
        />
      </div>
      <span className="custom-range-sep" aria-hidden="true">
        <Icon name="arrowRight" size={14} />
      </span>
      <div className="custom-range-field">
        <label htmlFor="range_end">To</label>
        <input
          id="range_end"
          type="date"
          min={start}
          max={today}
          value={end}
          onChange={(e) => onEnd(e.target.value)}
        />
      </div>
      <button type="button" className="button button--primary button--small" onClick={onApply}>
        Apply
      </button>
      {error && <span className="custom-range-error">{error}</span>}
    </div>
  );
}

export default function Dashboard() {
  const { seller } = useAuth();
  const [range, setRange] = useState("today");
  const [customStart, setCustomStart] = useState(toDateInput(new Date(Date.now() - 29 * DAY_MS)));
  const [customEnd, setCustomEnd] = useState(toDateInput(new Date()));
  const [appliedRange, setAppliedRange] = useState(null); // {start, end} once applied
  const [rangeError, setRangeError] = useState(null);

  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchStats = useCallback((params) => {
    setLoading(true);
    setError(null);
    api.stats
      .summary(params)
      .then((data) => setStats(data))
      .catch((err) => setError(getErrorMessage(err, "Could not load your stats.")))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (range === "custom") {
      if (appliedRange) fetchStats({ range: "custom", ...appliedRange });
      return; // wait for Apply — don't fetch garbage while picking dates
    }
    fetchStats({ range });
  }, [range, appliedRange, fetchStats]);

  function handleApplyCustom() {
    setRangeError(null);
    if (!customStart || !customEnd) {
      setRangeError("Pick both dates.");
      return;
    }
    if (customStart > customEnd) {
      setRangeError("The start date must be before the end date.");
      return;
    }
    const days = (new Date(customEnd) - new Date(customStart)) / DAY_MS + 1;
    if (days > 366) {
      setRangeError("Custom ranges can span at most one year.");
      return;
    }
    setAppliedRange({ start: customStart, end: customEnd });
  }

  const rangeLabel =
    range === "custom"
      ? appliedRange
        ? `${formatDate(appliedRange.start)} – ${formatDate(appliedRange.end)}`
        : "Custom"
      : RANGE_OPTIONS.find((r) => r.value === range)?.label ?? "";

  const chartDays = stats?.daily?.length ?? 0;

  // Time-aware greeting — the dashboard should feel like it knows you
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";

  return (
    <div className="dashboard-page">
      <header className="page-header page-header--row">
        <div>
          <h1>
            {greeting}, {seller?.store_name}
          </h1>
          <p>Here's how your store is doing.</p>
        </div>
        <div className="range-tabs" role="tablist" aria-label="Date range">
          {RANGE_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={range === option.value}
              className={`range-tab${range === option.value ? " range-tab--active" : ""}`}
              onClick={() => {
                setRange(option.value);
                if (option.value !== "custom") setAppliedRange(null);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      </header>

      {range === "custom" && (
        <CustomRangePanel
          start={customStart}
          end={customEnd}
          onStart={setCustomStart}
          onEnd={setCustomEnd}
          onApply={handleApplyCustom}
          error={rangeError}
        />
      )}

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}

      <SubscriptionCard seller={seller} stats={stats} />

      {loading ? (
        <div className="stat-grid" aria-hidden="true">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : stats ? (
        <>
          <section className="stat-grid">
            <StatCard
              icon="package"
              label={`Orders (${rangeLabel})`}
              value={stats.total_orders}
              accent="blue"
              to={ordersLink(range, appliedRange)}
              title="View the orders behind this number"
            />
            <StatCard
              icon="clock"
              label={`Pending (${rangeLabel})`}
              value={stats.pending_orders}
              accent="amber"
              to={ordersLink(range, appliedRange, "pending")}
              title="See pending orders in this range (placed + confirmed)"
            />
            <StatCard
              icon="packageCheck"
              label={`Delivered (${rangeLabel})`}
              value={stats.delivered_orders}
              accent="green"
              to={ordersLink(range, appliedRange, "delivered")}
              title="See delivered orders in this range"
            />
            <StatCard
              icon="banknote"
              label={`Revenue (${rangeLabel})`}
              value={formatTk(stats.revenue)}
              accent="green"
              to={ordersLink(range, appliedRange)}
              title="View the orders this revenue came from"
            />
          </section>

          {chartDays > 1 && (
            <section className="card">
              <div className="card-header-row">
                <h3>Orders — {rangeLabel.toLowerCase()}</h3>
                <Link
                  to={ordersLink(range, appliedRange)}
                  className="card-header-link"
                >
                  View these orders
                  <Icon name="arrowRight" size={13} />
                </Link>
              </div>
              <DailyChart daily={stats.daily} />
            </section>
          )}

          <section className="card">
            <div className="card-header-row">
              <h3>Status breakdown ({rangeLabel})</h3>
            </div>
            <div className="status-breakdown">
              {Object.entries(stats.status_counts).map(([status, count]) => (
                <div key={status} className="status-breakdown-row">
                  <span className="status-breakdown-label">
                    <span className={`badge-dot badge-dot--${status}`} aria-hidden="true" />
                    {STATUS_META[status]?.label ?? status}
                  </span>
                  <div className="status-breakdown-track">
                    <div
                      className={`status-breakdown-fill badge-bg--${status}`}
                      style={{ width: `${(count / Math.max(stats.total_orders, 1)) * 100}%` }}
                    />
                  </div>
                  <span className="status-breakdown-count">{count}</span>
                </div>
              ))}
            </div>
            <p className="muted-note">
              {stats.total_orders} order{stats.total_orders === 1 ? "" : "s"} in this
              range · {stats.cancelled_orders} cancelled
            </p>
          </section>
        </>
      ) : null}
    </div>
  );
}
