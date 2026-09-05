import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { BarChart, Sparkline } from "../components/Charts";
import Icon from "../components/icons";
import { SkeletonCard } from "../components/States";
import StatusBreakdown from "../components/StatusBreakdown";
import FreeLimitBanner, { FreeOrderMeter } from "../components/FreeLimitBanner";
import { ordersLink } from "../utils/businessDate";
import { formatTk, parseServerDate } from "../utils/orderStatus";

const RANGE_OPTIONS = [
  { value: "today", label: "Today" },
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
  { value: "all", label: "All time" },
  { value: "custom", label: "Custom" },
];

const DAY_MS = 24 * 60 * 60 * 1000;

/** Must match the backend's free_plan_orders setting. */
const FREE_PLAN_ORDERS = 15;

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
 * stand: plan, expiry date, and days remaining on Pro. Clicking it
 * opens the upgrade/renew options in Settings. New sellers get a
 * one-time free order allowance (metered here); Pro is unlimited.
 */
function SubscriptionCard({ seller, stats }) {
  const pro = seller?.plan === "pro";
  const expiry = seller?.plan_expires_at ? parseServerDate(seller.plan_expires_at) : null;
  const daysLeft = expiry ? Math.ceil((expiry - new Date()) / DAY_MS) : null;
  const active = pro && (!expiry || daysLeft > 0);

  // Free-plan allowance (one-time, not monthly) — shown as a usage
  // meter while there's runway left; amber past 75% used. The
  // full-limit banner handles the exhausted case, Pro shows nothing.
  const limit = stats?.plan_limit ?? null;
  const used = stats?.month_orders ?? 0;
  const showFreeMeter = !active && limit != null && used < limit && limit > 0;

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
    subline = `Your subscription ended ${formatDate(expiry)} — renew to keep supporting the platform.`;
  } else {
    headline = "Free plan";
    subline = `First ${FREE_PLAN_ORDERS} orders free — unlimited on Pro`;
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
        {showFreeMeter && <FreeOrderMeter limit={limit} used={used} />}
      </div>
      <span className="subscription-action" aria-hidden="true">
        {active ? "Manage / renew" : "Upgrade to Pro"}
        <Icon name="arrowRight" size={15} />
      </span>
    </Link>
  );
}

/** Activity chart — one measure at a time (the measure switch replaces
 * the old dual-axis bars+line overlay: count and money never share a
 * plot; they trade places via the tabs above the chart). */
function OrdersChart({ daily }) {
  const [measure, setMeasure] = useState("orders");
  const isMoney = measure === "revenue";
  const data = daily.map((day) => ({
    key: day.date,
    value: isMoney ? day.value ?? 0 : day.count,
  }));

  return (
    <div>
      <div className="measure-tabs" role="tablist" aria-label="Chart measure">
        <button
          type="button"
          role="tab"
          aria-selected={!isMoney}
          className={`measure-tab${!isMoney ? " measure-tab--active" : ""}`}
          onClick={() => setMeasure("orders")}
        >
          Orders
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={isMoney}
          className={`measure-tab${isMoney ? " measure-tab--active" : ""}`}
          onClick={() => setMeasure("revenue")}
        >
          Revenue
        </button>
      </div>
      <BarChart
        data={data}
        measure={isMoney ? "money" : "count"}
        barColor={isMoney ? "var(--success)" : "var(--primary)"}
      />
    </div>
  );
}

function StatCard({ icon, label, value, accent, to, title, spark }) {
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
      {spark && <Sparkline data={spark} color="var(--success)" />}
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

      <FreeLimitBanner stats={stats} />

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
              spark={chartDays > 1 ? stats.daily.map((d) => d.value ?? 0) : undefined}
            />
          </section>

          {chartDays > 1 && (
            <section className="card">
              <div className="card-header-row">
                <h3>Activity — {rangeLabel.toLowerCase()}</h3>
                <Link
                  to={ordersLink(range, appliedRange)}
                  className="card-header-link"
                >
                  View these orders
                  <Icon name="arrowRight" size={13} />
                </Link>
              </div>
              <OrdersChart daily={stats.daily} />
            </section>
          )}

          <section className="card">
            <div className="card-header-row">
              <h3>Status breakdown ({rangeLabel})</h3>
            </div>
            <StatusBreakdown counts={stats.status_counts} />
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
