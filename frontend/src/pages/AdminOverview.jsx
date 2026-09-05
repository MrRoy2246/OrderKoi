import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import { BarChart, DonutChart, Sparkline } from "../components/Charts";
import Icon from "../components/icons";
import { ErrorState, SkeletonCard } from "../components/States";
import { formatTk, parseServerDate } from "../utils/orderStatus";

/** The activity-chart window: one row of preset range tabs scoping
 * every chart below it (single source of truth — no per-chart picks). */
const RANGE_TABS = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
];

/** A headline metric — navigates when `to` is given. */
function StatTile({ icon, label, value, hint, accent, to, title, spark }) {
  const navigate = useNavigate();
  const content = (
    <>
      <span className={`stat-icon stat-icon--${accent}`}>
        <Icon name={icon} size={21} />
      </span>
      <div>
        <span className="stat-value">{value}</span>
        <span className="stat-label">{label}</span>
        {hint && <span className="stat-hint">{hint}</span>}
      </div>
      {spark && spark.length > 1 && <Sparkline data={spark} />}
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

function formatDate(value) {
  return parseServerDate(value).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** Platform-owner view: the whole OrderKoi business at a glance. */
export default function AdminOverview() {
  const navigate = useNavigate();
  const [days, setDays] = useState(30);
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);

  // Refetch on window change. The first load shows skeletons; a
  // refetch keeps the previous render on screen (dimmed) so switching
  // windows doesn't flash empty frames — the spec's "hold the frame".
  const fetchStats = useCallback((newDays) => {
    setFetching(true);
    setError(null);
    api.admin
      .stats(newDays)
      .then((data) => {
        setStats(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(getErrorMessage(err, "Could not load platform stats."));
        setLoading(false);
      })
      .finally(() => setFetching(false));
  }, []);

  useEffect(() => {
    fetchStats(days);
  }, [days, fetchStats]);

  if (loading) {
    return (
      <div className="admin-page">
        <div className="stat-grid" aria-hidden="true">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
    );
  }

  if (error && !stats) {
    return (
      <div className="admin-page">
        <ErrorState message={error} onRetry={() => fetchStats(days)} />
      </div>
    );
  }

  const conversion =
    stats.total_sellers > 0
      ? Math.round((stats.pro_sellers / stats.total_sellers) * 100)
      : 0;
  const monthName = new Date().toLocaleDateString(undefined, { month: "long" });

  return (
    <div className={`admin-page${fetching ? " admin-page--refetching" : ""}`}>
      <header className="page-header">
        <h1>Platform Overview</h1>
        <p>Your OrderKoi business, at a glance.</p>
      </header>

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}

      {stats.pending_upgrade_requests > 0 && (
        <section className="plan-banner plan-banner--action">
          <div>
            <strong>
              {stats.pending_upgrade_requests} upgrade request
              {stats.pending_upgrade_requests === 1 ? "" : "s"} waiting
            </strong>
            <span className="plan-banner-sub">
              {" "}Sellers paid and want Pro — verify the payments and activate.
            </span>
          </div>
          <Link to="/admin/requests" className="button button--primary button--small">
            Review requests
          </Link>
        </section>
      )}

      {/* Earnings — the two kinds of money, clearly separated:
          what YOU earned (Pro subscriptions) vs what your SELLERS
          earned collectively through their shops (order value). */}
      <section className="earnings-grid">
        <article
          className="earnings-card earnings-card--admin"
          role="link"
          tabIndex={0}
          title="See the subscription ledger"
          onClick={() => navigate("/admin/requests")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") navigate("/admin/requests");
          }}
        >
          <header className="earnings-head">
            <span className="earnings-icon earnings-icon--admin">
              <Icon name="creditCard" size={22} />
            </span>
            <div>
              <h2 className="earnings-title">Your earnings</h2>
              <p className="earnings-sub">Pro subscriptions across the platform</p>
            </div>
          </header>
          <div className="earnings-body">
            <span className="earnings-value">{formatTk(stats.subscription_revenue_total)}</span>
            <span className="earnings-trend">
              <Icon name="sparkles" size={13} />
              {formatTk(stats.subscription_revenue_30d)} in the last 30 days
            </span>
          </div>
          <BarChart
            data={stats.subscription_monthly.map((m) => ({ key: m.month, value: m.value }))}
            measure="money"
            height={120}
          />
          <p className="earnings-foot">
            From {stats.pro_sellers} active Pro seller{stats.pro_sellers === 1 ? "" : "s"} ·
            free (comp) grants excluded
          </p>
        </article>

        <article className="earnings-card earnings-card--sellers">
          <header className="earnings-head">
            <span className="earnings-icon earnings-icon--sellers">
              <Icon name="banknote" size={22} />
            </span>
            <div>
              <h2 className="earnings-title">Sellers' income</h2>
              <p className="earnings-sub">Total order value across all stores</p>
            </div>
          </header>
          <div className="earnings-body">
            <span className="earnings-value">{formatTk(stats.platform_revenue)}</span>
            <span className="earnings-trend">
              <Icon name="package" size={13} />
              {formatTk(stats.gmv_this_month)} this month ·{" "}
              {stats.orders_this_month} order{stats.orders_this_month === 1 ? "" : "s"}
            </span>
          </div>
          <BarChart
            data={stats.revenue_monthly.map((m) => ({ key: m.month, value: m.value }))}
            measure="money"
            barColor="var(--success)"
            height={120}
          />
          <p className="earnings-foot">
            This is your sellers' money — you don't take a cut. Your income is the Pro
            subscriptions on the left.
          </p>
        </article>
      </section>

      {/* Filter row — one place to scope every activity chart below.
          Monthly series (12-month windows) are all-time views, so they
          sit outside the day-window scope. */}
      <div className="measure-tabs admin-range-tabs" role="tablist" aria-label="Activity window">
        {RANGE_TABS.map((tab) => (
          <button
            key={tab.days}
            type="button"
            role="tab"
            aria-selected={days === tab.days}
            className={`measure-tab${days === tab.days ? " measure-tab--active" : ""}`}
            onClick={() => setDays(tab.days)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Platform pulse */}
      <section className="stat-grid">
        <StatTile
          icon="store"
          label="Total sellers"
          value={stats.total_sellers}
          hint={
            stats.new_sellers_30d > 0
              ? `+${stats.new_sellers_30d} in the last 30 days`
              : null
          }
          accent="blue"
          to="/admin/sellers"
          title="See all sellers and their plans"
        />
        <StatTile
          icon="sparkles"
          label="Pro sellers"
          value={stats.pro_sellers}
          hint={`${conversion}% of sellers`}
          accent="amber"
          to="/admin/sellers?plan=pro"
          title="See who's on Pro"
        />
        <StatTile
          icon="package"
          label={`Orders · last ${days} days`}
          value={stats.orders_daily.reduce((sum, d) => sum + d.count, 0)}
          hint={`${stats.sellers_with_orders} of ${stats.total_sellers} sellers have orders`}
          accent="blue"
          spark={stats.orders_daily?.map((d) => d.count)}
        />
        <StatTile
          icon="chartBar"
          label="New sellers · 30 days"
          value={stats.new_sellers_30d}
          hint={`${monthName} so far: ${stats.orders_this_month} orders`}
          accent="green"
        />
      </section>

      {/* Charts — activity (scoped by the window tabs above) */}
      <section className="card">
        <div className="card-header-row">
          <h3>Orders — last {days} days</h3>
        </div>
        <BarChart data={stats.orders_daily.map((d) => ({ key: d.date, value: d.count }))} />
      </section>

      <div className="admin-chart-grid">
        <section className="card">
          <div className="card-header-row">
            <h3>Sellers' income — last 12 months</h3>
          </div>
          <BarChart
            data={stats.revenue_monthly.map((m) => ({ key: m.month, value: m.value }))}
            measure="money"
            barColor="var(--success)"
          />
        </section>
        <section className="card">
          <div className="card-header-row">
            <h3>New sellers — last 12 months</h3>
          </div>
          <BarChart
            data={stats.sellers_monthly.map((m) => ({ key: m.month, value: m.count }))}
          />
        </section>
      </div>

      {/* Plan mix — donut */}
      <section className="card admin-plan-mix-card">
        <div className="card-header-row">
          <h3>Plan mix</h3>
          <span className="admin-mix-total">
            {stats.pro_sellers} Pro · {stats.free_sellers} Free
          </span>
        </div>
        <DonutChart
          caption={`${stats.total_sellers} shops`}
          slices={[
            { label: "Pro", value: stats.pro_sellers, color: "var(--primary)" },
            { label: "Free", value: stats.free_sellers, color: "var(--info)" },
          ]}
        />
      </section>

      <section className="card">
        <div className="card-header-row">
          <h3>Newest sellers</h3>
          <Link to="/admin/sellers" className="card-header-link">
            All sellers
            <Icon name="arrowRight" size={13} />
          </Link>
        </div>
        {stats.recent_signups.length === 0 ? (
          <p className="muted-note">No sellers yet — share your signup link!</p>
        ) : (
          <ul className="recent-signup-list">
            {stats.recent_signups.map((signup) => (
              <li key={`${signup.store_name}-${signup.created_at}`} className="recent-signup">
                <span className={`plan-chip${signup.plan === "pro" ? " plan-chip--pro" : ""}`}>
                  {signup.plan === "pro" ? (
                    <>
                      <Icon name="sparkles" size={14} className="plan-chip-icon" />
                      Pro
                    </>
                  ) : (
                    "Free"
                  )}
                </span>
                <span className="recent-signup-name">{signup.store_name}</span>
                <span className="recent-signup-date">joined {formatDate(signup.created_at)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
