import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import { ActivityFeed, ChartCard, KpiCard } from "../components/AdminDashboard";
import { BarChart, DonutChart } from "../components/Charts";
import { DashboardFilters, rangeLabel, rangeToWindow } from "../components/DashboardFilters";
import Icon from "../components/icons";
import { SkeletonCard, SkeletonRows } from "../components/States";
import { formatTk, parseServerDate } from "../utils/orderStatus";

const DEFAULT_RANGE = "30d";

/** "Sep 4, 2026" — handles full ISO datetimes AND date-only strings
 * (the old local helper smashed "T00:00:00" onto datetimes → Invalid
 * Date; this is the shared replacement). */
function formatDate(iso) {
  if (!iso) return "—";
  const parsed = parseServerDate(iso);
  if (Number.isNaN(parsed.getTime())) return "—";
  return parsed.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** One analytics section: title, optional meta row, chart. Sections
 * render independently — one failed API never blanks its neighbors. */

/** Newest-sellers table — columns mapped to what /admin/sellers
 * actually returns (store, plan, orders, revenue, joined). */
function NewestSellers({ sellers, loading, error, onRetry }) {
  if (loading) {
    return (
      <section className="card">
        <div className="card-header-row">
          <h3>Newest sellers</h3>
        </div>
        <SkeletonRows rows={5} />
      </section>
    );
  }
  if (error) {
    return (
      <section className="card">
        <div className="card-header-row">
          <h3>Newest sellers</h3>
        </div>
        <div className="section-error">
          <p>{error}</p>
          <button type="button" className="button button--outline button--small" onClick={onRetry}>
            <Icon name="refresh" size={14} />
            Try again
          </button>
        </div>
      </section>
    );
  }
  const shops = sellers
    .filter((s) => s.role !== "admin")
    .sort((a, b) => b.created_at?.localeCompare(a.created_at ?? "") ?? 0)
    .slice(0, 5);

  return (
    <section className="card">
      <div className="card-header-row">
        <h3>Newest sellers</h3>
        <Link to="/admin/sellers" className="card-header-link">
          View all
          <Icon name="arrowRight" size={13} />
        </Link>
      </div>
      {shops.length === 0 ? (
        <p className="muted-note">No sellers yet — share your signup link.</p>
      ) : (
        <div className="table-wrap">
          <table className="orders-table newest-sellers-table">
            <thead>
              <tr>
                <th>Seller</th>
                <th>Plan</th>
                <th>Orders</th>
                <th>Revenue</th>
                <th>Joined</th>
              </tr>
            </thead>
            <tbody>
              {shops.map((shop) => (
                <tr key={shop.id}>
                  <td className="td-strong" data-label="Seller">
                    <Link
                      to={`/admin/sellers/${shop.id}`}
                      className="shop-link"
                      title={`Open ${shop.store_name}'s performance, revenue, and report`}
                    >
                      {shop.store_name}
                    </Link>
                  </td>
                  <td data-label="Plan">
                    <span className={`plan-chip${shop.plan === "pro" ? " plan-chip--pro" : ""}`}>
                      {shop.plan === "pro" ? (
                        <>
                          <Icon name="sparkles" size={14} className="plan-chip-icon" />
                          Pro
                        </>
                      ) : (
                        "Free"
                      )}
                    </span>
                  </td>
                  <td className="td-strong" data-label="Orders">{shop.orders_count}</td>
                  <td className="td-strong" data-label="Revenue">{formatTk(shop.revenue)}</td>
                  <td className="td-muted" data-label="Joined" title={formatDate(shop.created_at)}>
                    {formatDate(shop.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** Two-row KPI hint: the window-scoped figure on top, the all-time
 * total as a separated label→value footer row. Two scopes should never
 * share one run-on line — the split keeps "what this period did" from
 * reading as the same number as the lifetime figure. */
function KpiHint({ period, allTime }) {
  return (
    <>
      <span className="kpi-hint-period">{period}</span>
      <span className="kpi-hint-row">
        <span className="kpi-hint-row-label">All time</span>
        <span className="kpi-hint-row-value">{allTime}</span>
      </span>
    </>
  );
}

/** Platform-owner view: the whole OrderKoi business at a glance. */
export default function AdminOverview() {
  // ---- Global date filter (the only dimension the stats API scopes) ----
  const [range, setRange] = useState(DEFAULT_RANGE);
  const [custom, setCustom] = useState(null); // {start, end} once applied

  // ---- Three independent data sources: one failure never blanks
  // the page, and each section shows its own retry. ----
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState(null);
  const [statsFetching, setStatsFetching] = useState(false);

  const [sellers, setSellers] = useState(null);
  const [sellersLoading, setSellersLoading] = useState(true);
  const [sellersError, setSellersError] = useState(null);

  const [events, setEvents] = useState(null);
  const [eventsLoading, setEventsLoading] = useState(true);
  const [eventsError, setEventsError] = useState(null);

  // Sellers' income measure: revenue, order count, or average order
  // value (AOV = revenue / orders per month — derived, not stored)
  const [incomeMeasure, setIncomeMeasure] = useState("revenue");

  // The window a fetch stands for — a custom range only counts once
  // applied; while dates are being picked the last window stays on
  // screen (no garbage fetches). PRIMITIVES in the effect deps: an
  // object literal here re-created every render caused an infinite
  // fetch loop (dim + pointer-events:none blinking forever).
  const window_ =
    range === "custom" && !custom
      ? rangeToWindow(DEFAULT_RANGE)
      : rangeToWindow(range, custom);
  const windowStart = window_?.start;
  const windowEnd = window_?.end;

  const fetchStats = useCallback((win) => {
    setStatsFetching(true);
    setStatsError(null);
    api.admin
      .stats(win ? { start: win.start, end: win.end } : {})
      .then((data) => {
        setStats(data);
        setStatsLoading(false);
      })
      .catch((err) => {
        setStatsError(getErrorMessage(err, "Could not load platform stats."));
        setStatsLoading(false);
      })
      .finally(() => setStatsFetching(false));
  }, []);

  const fetchSellers = useCallback(() => {
    setSellersLoading(true);
    setSellersError(null);
    api.admin
      .sellers()
      .then((data) => {
        setSellers(data);
        setSellersLoading(false);
      })
      .catch((err) => {
        setSellersError(getErrorMessage(err, "Could not load sellers."));
        setSellersLoading(false);
      });
  }, []);

  const fetchEvents = useCallback(() => {
    setEventsLoading(true);
    setEventsError(null);
    api.admin
      .subscriptionEvents()
      .then((data) => {
        setEvents(data);
        setEventsLoading(false);
      })
      .catch((err) => {
        setEventsError(getErrorMessage(err, "Could not load activity."));
        setEventsLoading(false);
      });
  }, []);

  useEffect(() => {
    // Custom range not yet applied → keep the previous data on screen
    if (range === "custom" && !custom) return;
    fetchStats(windowStart && windowEnd ? { start: windowStart, end: windowEnd } : {});
    // eslint-disable-next-line react-hooks/exhaustive-deps -- primitives only
  }, [windowStart, windowEnd, fetchStats]);
  useEffect(() => {
    fetchSellers();
  }, [fetchSellers]);
  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  function handleFilterApply(next) {
    if (next.range === "custom" && next.custom) {
      setCustom(next.custom);
      setRange("custom");
    } else if (next.range === "custom") {
      // just opening the panel — no fetch until Apply
      setRange("custom");
    } else {
      setCustom(null);
      setRange(next.range);
    }
  }

  // ---- Hard error (nothing loaded, first fetch failed) ----
  if (statsLoading && !stats) {
    return (
      <div className="admin-page">
        <header className="page-header">
          <h1>Platform Overview</h1>
          <p>Monitor your marketplace performance, seller growth, and platform revenue.</p>
        </header>
        <div className="kpi-grid" aria-hidden="true">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} lines={2} />
          ))}
        </div>
      </div>
    );
  }

  if (statsError && !stats) {
    return (
      <div className="admin-page">
        <header className="page-header">
          <h1>Platform Overview</h1>
          <p>Monitor your marketplace performance, seller growth, and platform revenue.</p>
        </header>
        <div className="section-error section-error--page">
          <p>{statsError}</p>
          <button
            type="button"
            className="button button--outline"
            onClick={() =>
              fetchStats(windowStart && windowEnd ? { start: windowStart, end: windowEnd } : {})
            }
          >
            <Icon name="refresh" size={16} />
            Try again
          </button>
        </div>
      </div>
    );
  }

  // ---- Derived figures (all real, all from the API payload) ----
  // Buckets follow the date filter with adaptive granularity: short
  // windows (<= 90 days) are daily (key in `date`), wide ones are
  // monthly (key in `month`)
  const bucketKey = (b) => b.date ?? b.month;
  const ordersInWindow = stats.orders_daily.reduce((sum, d) => sum + d.count, 0);
  const daysInWindow = Math.max(stats.orders_daily.length, 1);
  const avgPerDay = ordersInWindow / daysInWindow;
  const peak = stats.orders_daily.reduce(
    (best, d) => (d.count > best.count ? d : best),
    { key: null, count: 0 }
  );
  const peakDay = peak.key && peak.count > 0 ? peak : null;

  const conversion =
    stats.total_sellers > 0 ? Math.round((stats.pro_sellers / stats.total_sellers) * 100) : 0;

  const monthly = stats.revenue_monthly.map((m) => ({ key: bucketKey(m), count: m.count, value: m.value }));
  const incomeData =
    incomeMeasure === "revenue"
      ? monthly.map((m) => ({ key: m.key, value: m.value }))
      : incomeMeasure === "orders"
        ? monthly.map((m) => ({ key: m.key, value: m.count }))
        : monthly
            .filter((m) => m.count > 0)
            .map((m) => ({ key: m.key, value: Math.round((m.value / m.count) * 100) / 100 }));
  // New signups over the chart's actual series — the meta line must
  // describe what's plotted, not a fixed 30-day pulse
  const newSellersInSeries = stats.sellers_monthly.reduce((sum, m) => sum + m.count, 0);
  // Window sums — the chart meta must carry what's PLOTTED in the
  // selected range, not the all-time totals
  const revenueInWindow = monthly.reduce((sum, m) => sum + m.value, 0);
  const ordersInMoneySeries = monthly.reduce((sum, m) => sum + m.count, 0);
  const subsInWindow = stats.subscription_monthly.reduce(
    (sum, m) => sum + m.value,
    0
  );
  const paymentsInWindow = stats.subscription_monthly.reduce(
    (sum, m) => sum + m.count,
    0
  );
  const filterLabel = rangeLabel(range, custom);
  const windowLabel =
    range === "custom" && !custom ? "last 30 days" : filterLabel.toLowerCase();
  // Every chart now follows the date filter (adaptive granularity:
  // daily buckets for windows <= 90 days, monthly for wider ones), so
  // the scope label simply names the selected range
  const chartScope = windowLabel;

  return (
    <div className={`admin-page${statsFetching ? " admin-page--refetching" : ""}`}>
      <header className="page-header page-header--row">
        <div>
          <h1>Platform Overview</h1>
          <p>Monitor your marketplace performance, seller growth, and platform revenue.</p>
        </div>
        {stats.pending_upgrade_requests > 0 && (
          <div className="header-actions">
            <Link to="/admin/requests" className="button button--primary button--small">
              <Icon name="inbox" size={15} />
              {stats.pending_upgrade_requests} request
              {stats.pending_upgrade_requests === 1 ? "" : "s"} to review
            </Link>
          </div>
        )}
      </header>

      {statsError && (
        <div className="alert alert--error" role="alert">
          {statsError}
        </div>
      )}

      {/* Global filter bar — scopes every analytics section below */}
      <DashboardFilters
        range={range}
        custom={custom}
        onApply={handleFilterApply}
        defaultRange={DEFAULT_RANGE}
      />

      {/* KPI grid — six headline metrics, all real API values.
          Every number follows the global date filter; all-time
          context lives in the hints. */}
      <section className="kpi-grid">
        <KpiCard
          icon="creditCard"
          label={`Your earnings · ${windowLabel}`}
          value={formatTk(subsInWindow)}
          hint={
            <KpiHint
              period={
                paymentsInWindow > 0
                  ? `${paymentsInWindow} payment${paymentsInWindow === 1 ? "" : "s"} in this period`
                  : "No payments in this period"
              }
              allTime={formatTk(stats.subscription_revenue_total)}
            />
          }
          accent="orange"
          to="/admin/requests"
          title="See the subscription ledger"
        />
        <KpiCard
          icon="banknote"
          label={`Seller revenue · ${windowLabel}`}
          value={formatTk(revenueInWindow)}
          hint={
            <KpiHint
              period={`${ordersInMoneySeries.toLocaleString()} order${ordersInMoneySeries === 1 ? "" : "s"} in this period`}
              allTime={formatTk(stats.platform_revenue)}
            />
          }
          accent="green"
          to="/admin/sellers"
          title="See sellers and their order value"
        />
        <KpiCard
          icon="package"
          label={`Orders · ${windowLabel}`}
          value={ordersInWindow.toLocaleString()}
          hint={
            avgPerDay >= 1
              ? `${avgPerDay.toFixed(1)} per day on average`
              : `${(avgPerDay * daysInWindow).toFixed(0)} total across ${daysInWindow} days`
          }
          accent="blue"
          spark={stats.orders_daily.map((d) => d.count)}
          sparkColor="var(--info)"
        />
        <KpiCard
          icon="store"
          label="Total sellers"
          value={stats.total_sellers}
          hint={
            newSellersInSeries > 0
              ? `+${newSellersInSeries} joined in ${windowLabel}`
              : `${stats.sellers_with_orders} sellers with orders`
          }
          accent="blue"
          to="/admin/sellers"
          title="See all sellers and their plans"
        />
        <KpiCard
          icon="sparkles"
          label="Pro sellers"
          value={stats.pro_sellers}
          hint={`${conversion}% of all sellers`}
          accent="orange"
          to="/admin/sellers?plan=pro"
          title="See who's on Pro"
        />
        <KpiCard
          icon="users"
          label={`New sellers · ${windowLabel}`}
          value={newSellersInSeries}
          hint={`${stats.sellers_with_orders} sellers with orders · all time`}
          accent="green"
        />
      </section>

      {/* Revenue analytics — the two kinds of money, side by side.
          Both series follow the global date filter with adaptive
          granularity (daily for <= 90-day windows, monthly otherwise). */}
      <div className="admin-chart-grid admin-chart-grid--revenue">
        <ChartCard
          title="Platform revenue"
          meta={`${formatTk(subsInWindow)} in ${chartScope}`}
          footer={`From ${stats.pro_sellers} active Pro seller${stats.pro_sellers === 1 ? "" : "s"} · all-time ${formatTk(stats.subscription_revenue_total)} · comp grants excluded`}
        >
          <BarChart
            data={stats.subscription_monthly.map((m) => ({ key: bucketKey(m), value: m.value }))}
            measure="money"
            height={160}
          />
        </ChartCard>

        <ChartCard
          title="Seller income"
          meta={`${formatTk(revenueInWindow)} in ${chartScope}`}
          tabs={[
            { value: "revenue", label: "Revenue" },
            { value: "orders", label: "Orders" },
            { value: "aov", label: "AOV" },
          ]}
          activeTab={incomeMeasure}
          onTab={setIncomeMeasure}
          footer="All-time sales across every shop — you don't take a cut. Your income is the Pro subscriptions."
        >
          <BarChart
            data={incomeData}
            measure={incomeMeasure === "orders" ? "count" : "money"}
            barColor="var(--success)"
            height={160}
          />
        </ChartCard>
      </div>

      {/* Orders analytics — scoped by the global date filter */}
      <ChartCard
        title={`Orders — ${windowLabel}`}
        meta={
          peakDay
            ? `Peak: ${peakDay.count} on ${formatDate(peakDay.key)}`
            : `${ordersInWindow} order${ordersInWindow === 1 ? "" : "s"} in this period`
        }
      >
        {ordersInWindow === 0 ? (
          <div className="chart-empty">
            <p>No orders in this period.</p>
            <button
              type="button"
              className="button button--outline button--small"
              onClick={() => handleFilterApply({ range: DEFAULT_RANGE })}
            >
              Change date range
            </button>
          </div>
        ) : (
          <BarChart
            data={stats.orders_daily.map((d) => ({ key: d.date, value: d.count }))}
            barColor="var(--info)"
          />
        )}
      </ChartCard>

      {/* Growth + plan mix */}
      <div className="admin-chart-grid">
        <ChartCard
          title="Seller growth"
          meta={`${newSellersInSeries} new seller${newSellersInSeries === 1 ? "" : "s"} · ${chartScope}`}
        >
          <BarChart
            data={stats.sellers_monthly.map((m) => ({ key: bucketKey(m), value: m.count }))}
            height={180}
          />
        </ChartCard>

        <section className="card admin-plan-mix-card">
          <div className="card-header-row">
            <h3>Plan distribution</h3>
          </div>
          <DonutChart
            caption={`${stats.total_sellers} shops`}
            slices={[
              { label: "Pro", value: stats.pro_sellers, color: "var(--primary)" },
              { label: "Free", value: stats.free_sellers, color: "var(--info)" },
            ]}
          />
          <p className="chart-card-foot">
            {stats.pro_sellers} Pro · {stats.free_sellers} Free · {conversion}% conversion
          </p>
        </section>
      </div>

      {/* Needs attention + newest sellers + activity */}
      <div className="admin-chart-grid admin-chart-grid--lists">
        <NewestSellers
          sellers={sellers ?? []}
          loading={sellersLoading}
          error={sellersError}
          onRetry={fetchSellers}
        />

        <div className="stack-col">
          <section className="card">
            <div className="card-header-row">
              <h3>Upgrade requests</h3>
              <Link to="/admin/requests" className="card-header-link">
                Review
                <Icon name="arrowRight" size={13} />
              </Link>
            </div>
            <div className="requests-mini">
              <span className="requests-mini-value">
                {stats.pending_upgrade_requests}
              </span>
              <span className="requests-mini-label">
                pending request{stats.pending_upgrade_requests === 1 ? "" : "s"}
                {stats.pending_upgrade_requests > 0
                  ? " — sellers paid and want Pro"
                  : " — you're all caught up"}
              </span>
            </div>
          </section>

          <section className="card">
            <div className="card-header-row">
              <h3>Recent activity</h3>
            </div>
            {eventsLoading ? (
              <SkeletonRows rows={3} />
            ) : eventsError ? (
              <div className="section-error">
                <p>{eventsError}</p>
                <button
                  type="button"
                  className="button button--outline button--small"
                  onClick={fetchEvents}
                >
                  <Icon name="refresh" size={14} />
                  Try again
                </button>
              </div>
            ) : (
              <ActivityFeed events={(events ?? []).slice(0, 6)} />
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
