import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import { DonutChart, MonthlyBars, Sparkline } from "../components/Charts";
import Icon from "../components/icons";
import { ErrorState, SkeletonCard } from "../components/States";
import { formatTk, parseServerDate } from "../utils/orderStatus";

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
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchStats = useCallback(() => {
    setLoading(true);
    setError(null);
    api.admin
      .stats()
      .then(setStats)
      .catch((err) => setError(getErrorMessage(err, "Could not load platform stats.")))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

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

  if (error) {
    return (
      <div className="admin-page">
        <ErrorState message={error} onRetry={fetchStats} />
      </div>
    );
  }

  const conversion =
    stats.total_sellers > 0
      ? Math.round((stats.pro_sellers / stats.total_sellers) * 100)
      : 0;
  const monthName = new Date().toLocaleDateString(undefined, { month: "long" });

  return (
    <div className="admin-page">
      <header className="page-header">
        <h1>Platform Overview</h1>
        <p>Your OrderKoi business, at a glance.</p>
      </header>

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

      {/* The numbers that define the business */}
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
          label="Total orders"
          value={stats.total_orders}
          hint={`${stats.sellers_with_orders} of ${stats.total_sellers} sellers have orders`}
          accent="blue"
          spark={stats.orders_daily?.map((d) => d.count)}
        />
        <StatTile
          icon="banknote"
          label="Gross order value"
          value={formatTk(stats.platform_revenue)}
          hint="total value of non-cancelled orders"
          accent="green"
        />
        <StatTile
          icon="creditCard"
          label="Subscription earnings"
          value={formatTk(stats.subscription_revenue_total)}
          hint="what sellers paid for Pro — comps excluded"
          accent="amber"
          to="/admin/requests"
          title="See the subscription ledger"
          spark={stats.revenue_monthly?.map((m) => m.value)}
        />
        <StatTile
          icon="chartBar"
          label="Earned · last 30 days"
          value={formatTk(stats.subscription_revenue_30d)}
          hint="Pro payments in the last 30 days"
          accent="green"
        />
      </section>

      {/* Charts — orders per day, GMV per month, growth per month */}
      <section className="card">
        <div className="card-header-row">
          <h3>Orders — last 30 days</h3>
          <span className="chart-legend" aria-hidden="true">
            <span className="chart-legend-item">
              <span className="chart-legend-swatch chart-legend-swatch--bar" />
              orders/day
            </span>
          </span>
        </div>
        <MonthlyBars
          data={stats.orders_daily.map((d) => ({ key: d.date, count: d.count }))}
          valueLabel="orders"
        />
      </section>

      <div className="admin-chart-grid">
        <section className="card">
          <div className="card-header-row">
            <h3>Gross order value — last 12 months</h3>
          </div>
          <MonthlyBars data={stats.revenue_monthly} valueLabel="GMV" />
        </section>
        <section className="card">
          <div className="card-header-row">
            <h3>New sellers — last 12 months</h3>
          </div>
          <MonthlyBars data={stats.sellers_monthly} valueLabel="signups" />
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
            { label: "Free", value: stats.free_sellers, color: "var(--border-strong)" },
          ]}
        />
      </section>

      {/* Growth pulse — this business month */}
      <section className="card admin-month-card">
        <h3>{monthName} so far</h3>
        <div className="admin-month-strip">
          <div className="admin-month-stat">
            <span className="admin-month-value">{stats.orders_this_month}</span>
            <span className="admin-month-label">orders</span>
          </div>
          <div className="admin-month-divider" aria-hidden="true" />
          <div className="admin-month-stat">
            <span className="admin-month-value">{formatTk(stats.gmv_this_month)}</span>
            <span className="admin-month-label">order value</span>
          </div>
          <div className="admin-month-divider" aria-hidden="true" />
          <div className="admin-month-stat">
            <span className="admin-month-value">{stats.new_sellers_30d}</span>
            <span className="admin-month-label">new sellers · 30 days</span>
          </div>
        </div>
        <p className="muted-note">
          Free sellers can create 50 orders a month — beyond that they need Pro,
          which they pay for via bKash/Nagad and you activate after verifying.
        </p>
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
