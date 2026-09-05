import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import { ChartCard, KpiCard } from "../components/AdminDashboard";
import { BarChart } from "../components/Charts";
import { DashboardFilters, rangeLabel, rangeToWindow } from "../components/DashboardFilters";
import Icon from "../components/icons";
import { SkeletonCard, SkeletonRows } from "../components/States";
import StatusBreakdown from "../components/StatusBreakdown";
import { formatTk, parseServerDate } from "../utils/orderStatus";

const DEFAULT_RANGE = "30d";

/** "Sep 4, 2026" — shared shape with the overview's formatDate. */
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

/**
 * One shop, in depth — the admin's drill-down from the sellers list.
 * KPIs, a daily orders/revenue chart scoped by the same date-range
 * filter, a status breakdown, and a CSV report of the window's orders.
 */
export default function AdminShopDetail() {
  const { id } = useParams();
  const sellerId = Number(id);
  const navigate = useNavigate();

  // ---- Date filter (same component and window logic as the overview) ----
  const [range, setRange] = useState(DEFAULT_RANGE);
  const [custom, setCustom] = useState(null);

  const [shop, setShop] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [fetching, setFetching] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(null);

  // Orders vs revenue on the daily chart
  const [measure, setMeasure] = useState("orders");

  // PRIMITIVES in the effect deps — see AdminOverview for why an object
  // literal here once caused an infinite fetch loop.
  const window_ =
    range === "custom" && !custom
      ? rangeToWindow(DEFAULT_RANGE)
      : rangeToWindow(range, custom);
  const windowStart = window_?.start;
  const windowEnd = window_?.end;

  const fetchShop = useCallback(
    (win) => {
      setFetching(true);
      setError(null);
      api.admin
        .sellerStats(sellerId, win ? { start: win.start, end: win.end } : {})
        .then((data) => {
          setShop(data);
          setLoading(false);
        })
        .catch((err) => {
          if (err?.status === 404) navigate("/admin/sellers", { replace: true });
          else setError(getErrorMessage(err, "Could not load this shop's stats."));
          setLoading(false);
        })
        .finally(() => setFetching(false));
    },
    [sellerId, navigate]
  );

  useEffect(() => {
    if (range === "custom" && !custom) return;
    fetchShop(windowStart && windowEnd ? { start: windowStart, end: windowEnd } : {});
    // eslint-disable-next-line react-hooks/exhaustive-deps -- primitives only
  }, [windowStart, windowEnd, fetchShop]);

  function handleFilterApply(next) {
    if (next.range === "custom" && next.custom) {
      setCustom(next.custom);
      setRange("custom");
    } else if (next.range === "custom") {
      setRange("custom");
    } else {
      setCustom(null);
      setRange(next.range);
    }
  }

  async function handleExport() {
    setExporting(true);
    setExportError(null);
    try {
      await api.admin.exportSellerOrdersCsv(
        sellerId,
        windowStart && windowEnd ? { start: windowStart, end: windowEnd } : {}
      );
    } catch (err) {
      setExportError(getErrorMessage(err, "Could not build the report."));
    } finally {
      setExporting(false);
    }
  }

  if (loading) {
    return (
      <div className="admin-page">
        <header className="page-header page-header--row">
          <div>
            <h1>Shop</h1>
            <SkeletonRows rows={1} />
          </div>
        </header>
        <div className="kpi-grid" aria-hidden="true">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} lines={2} />
          ))}
        </div>
      </div>
    );
  }

  if (error && !shop) {
    return (
      <div className="admin-page">
        <header className="page-header">
          <h1>Shop</h1>
          <p>This shop's stats could not be loaded.</p>
        </header>
        <div className="section-error section-error--page">
          <p>{error}</p>
          <button
            type="button"
            className="button button--outline"
            onClick={() =>
              fetchShop(windowStart && windowEnd ? { start: windowStart, end: windowEnd } : {})
            }
          >
            <Icon name="refresh" size={16} />
            Try again
          </button>
        </div>
      </div>
    );
  }

  const daily = shop.daily.map((d) => ({ key: d.date, value: d[measure === "orders" ? "count" : "value"] }));
  const activeDays = shop.daily.filter((d) => d.count > 0).length;
  const peakDay = shop.daily.reduce(
    (best, d) => (d.count > best.count ? d : best),
    { date: null, count: 0, value: 0 }
  );
  const hasPeak = peakDay.date && peakDay.count > 0;
  const bestDay = shop.daily.reduce(
    (best, d) => (d.value > best.value ? d : best),
    { date: null, count: 0, value: 0 }
  );
  const hasBest = bestDay.date && bestDay.value > 0;

  const statusTotal = STATUS_ORDER.reduce((sum, s) => sum + (shop.status_counts?.[s] ?? 0), 0);
  const deliveredCount = shop.status_counts?.delivered ?? 0;
  const cancelledCount = shop.status_counts?.cancelled ?? 0;
  const fulfilledPct =
    statusTotal > 0 ? Math.round((deliveredCount / statusTotal) * 100) : 0;
  const cancelledPct =
    statusTotal > 0 ? Math.round((cancelledCount / statusTotal) * 100) : 0;

  const filterLabel = rangeLabel(range, custom);
  const windowLabel =
    range === "custom" && !custom ? "last 30 days" : filterLabel.toLowerCase();

  return (
    <div className={`admin-page${fetching ? " admin-page--refetching" : ""}`}>
      <header className="page-header page-header--row">
        <div>
          <p className="page-header-eyebrow">
            <Link to="/admin/sellers" className="back-link">
              <Icon name="chevronLeft" size={14} />
              All sellers
            </Link>
          </p>
          <h1 className="shop-detail-title">
            {shop.store_name}
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
          </h1>
          <p className="shop-detail-sub">
            {shop.email} · joined {formatDate(shop.created_at)}
            {shop.plan === "pro" && shop.plan_expires_at && (
              <> · Pro until {formatDate(shop.plan_expires_at)}</>
            )}
            {" · "}
            <a
              href={`/order/${shop.store_slug}`}
              target="_blank"
              rel="noreferrer"
              title="Open this shop's public order form"
            >
              /order/{shop.store_slug}
            </a>
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="button button--primary"
            onClick={handleExport}
            disabled={exporting || shop.total_orders === 0}
            title="Download this shop's orders for the selected date range as a CSV report"
          >
            <Icon name="download" size={15} />
            {exporting ? "Building…" : "Download report"}
          </button>
        </div>
      </header>

      {exportError && (
        <div className="alert alert--error" role="alert">
          {exportError}
        </div>
      )}

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}

      {/* Date filter — the only dimension the shop-stats API scopes */}
      <DashboardFilters
        range={range}
        custom={custom}
        onApply={handleFilterApply}
        defaultRange={DEFAULT_RANGE}
      />

      {/* KPI grid — the window's headline numbers */}
      <section className="kpi-grid">
        <KpiCard
          icon="package"
          label={`Orders · ${windowLabel}`}
          value={shop.total_orders.toLocaleString()}
          hint={
            shop.total_orders > 0
              ? `Orders on ${activeDays} of ${shop.daily.length} day${shop.daily.length === 1 ? "" : "s"}`
              : `No orders in this period`
          }
          accent="blue"
        />
        <KpiCard
          icon="banknote"
          label={`Revenue · ${windowLabel}`}
          value={formatTk(shop.revenue)}
          hint={hasBest ? `Best day: ${formatTk(bestDay.value)} on ${formatDate(bestDay.date)}` : "No revenue in this period"}
          accent="green"
        />
        <KpiCard
          icon="creditCard"
          label="Average order value"
          value={shop.total_orders > 0 ? formatTk(shop.aov) : "—"}
          hint={
            shop.total_orders > 0
              ? `Revenue across ${shop.total_orders} order${shop.total_orders === 1 ? "" : "s"} (cancelled excluded)`
              : "Needs at least one order"
          }
          accent="orange"
        />
        <KpiCard
          icon="packageCheck"
          label="Delivered"
          value={`${deliveredCount}`}
          hint={
            statusTotal > 0
              ? `${fulfilledPct}% of ${statusTotal} order${statusTotal === 1 ? "" : "s"} in this period`
              : "No orders in this period"
          }
          accent="green"
        />
      </section>

      {/* Daily performance chart, with a measure switch */}
      <ChartCard
        title={`Daily performance — ${windowLabel}`}
        meta={
          hasPeak
            ? `Peak: ${peakDay.count} orders on ${formatDate(peakDay.date)}`
            : `${shop.total_orders} order${shop.total_orders === 1 ? "" : "s"} in this period`
        }
        tabs={[
          { value: "orders", label: "Orders" },
          { value: "revenue", label: "Revenue" },
        ]}
        activeTab={measure}
        onTab={setMeasure}
        footer={
          measure === "revenue"
            ? "Daily order value — cancelled orders excluded."
            : "Orders placed per day (all statuses count)."
        }
      >
        {shop.total_orders === 0 ? (
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
            data={daily}
            measure={measure === "revenue" ? "money" : "count"}
            barColor={measure === "revenue" ? "var(--success)" : "var(--info)"}
          />
        )}
      </ChartCard>

      {/* Status breakdown — every order in the window, by workflow step */}
      <section className="card">
        <div className="card-header-row">
          <h3>Order status breakdown · {windowLabel}</h3>
        </div>
        <StatusBreakdown counts={shop.status_counts} />
        <p className="chart-card-foot">
          {statusTotal} order{statusTotal === 1 ? "" : "s"} in this period · {fulfilledPct}%
          delivered · {cancelledPct}% cancelled
        </p>
      </section>
    </div>
  );
}
