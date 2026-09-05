import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import Icon from "../components/icons";
import OrderFormModal from "../components/OrderFormModal";
import FreeLimitBanner from "../components/FreeLimitBanner";
import { EmptyState, SkeletonRows } from "../components/States";
import StatusBadge from "../components/StatusBadge";
import useMediaQuery from "../utils/useMediaQuery";
import { businessToday, shiftDays } from "../utils/businessDate";
import {
  STATUS_FILTER_OPTIONS,
  formatDateTime,
  formatRelativeTime,
  formatTk,
  trackingUrl,
} from "../utils/orderStatus";

const PAGE_SIZE = 20;

/** Date window tabs — same options as the dashboard. */
const DATE_RANGE_TABS = [
  { value: "all", label: "All" },
  { value: "today", label: "Today" },
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
  { value: "custom", label: "Custom" },
];

/** Dropdown values that map to more than one backend status. */
const NAMED_FILTERS = {
  pending: ["placed", "confirmed"],
};

/** Translate a dropdown/status-URL value into API status values. */
function toApiStatuses(value) {
  if (!value) return undefined;
  return NAMED_FILTERS[value] ?? [value];
}

/** "Sep 2" style date for the active-filter summary in the header. */
function formatShortDate(value) {
  if (!value) return null;
  return new Date(`${value}T00:00:00`).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
}

/** Which tab is active for a given start/end window? Links from the
 * dashboard carry explicit dates — match them back to a tab when they
 * line up (Today/7d/30d), else fall back to "custom". */
function deriveRangeTab(start, end) {
  if (!start && !end) return "all";
  const today = businessToday();
  if (start === today && end === today) return "today";
  if (start === shiftDays(today, -6) && end === today) return "7d";
  if (start === shiftDays(today, -29) && end === today) return "30d";
  return "custom";
}

/** The window a quick tab stands for ("custom" keeps the inputs). */
function rangeTabToDates(value) {
  const today = businessToday();
  if (value === "today") return { start: today, end: today };
  if (value === "7d") return { start: shiftDays(today, -6), end: today };
  if (value === "30d") return { start: shiftDays(today, -29), end: today };
  return { start: "", end: "" };
}

export default function Orders() {
  const [searchParams, setSearchParams] = useSearchParams();
  const isMobile = useMediaQuery("(max-width: 767px)");

  const [orders, setOrders] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  // ?status=/?start=/?end= in the URL (e.g. linked from a dashboard
  // stat card) seed the filters — "pending" means placed + confirmed
  const [statusFilter, setStatusFilter] = useState(searchParams.get("status") || "");
  const [dateFrom, setDateFrom] = useState(searchParams.get("start") || "");
  const [dateTo, setDateTo] = useState(searchParams.get("end") || "");
  // Active tab: seeded from the URL dates so dashboard links light up
  // the right tab (Today/7d/30d) instead of showing "custom"
  const [rangeTab, setRangeTab] = useState(() =>
    deriveRangeTab(searchParams.get("start") || "", searchParams.get("end") || "")
  );

  const [modalOpen, setModalOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [copiedCode, setCopiedCode] = useState(null);
  const copyTimer = useRef(null);

  // Plan state — powers the free-limit banner (and whether the
  // "New order" button opens the form or the upgrade prompt)
  const [planStats, setPlanStats] = useState(null);
  useEffect(() => {
    api.stats
      .summary({ range: "today" })
      .then(setPlanStats)
      .catch(() => setPlanStats(null));
  }, []);

  // Debounce the search box so we don't hammer the API on every keystroke
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setOffset(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.orders.list({
        q: debouncedSearch || undefined,
        status: toApiStatuses(statusFilter),
        start: dateFrom || undefined,
        end: dateTo || undefined,
        limit: PAGE_SIZE,
        offset,
      });
      setOrders(data.orders);
      setTotal(data.total);
    } catch (err) {
      setError(getErrorMessage(err, "Could not load orders."));
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch, statusFilter, dateFrom, dateTo, offset]);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

  useEffect(() => () => clearTimeout(copyTimer.current), []);

  /** Keep the URL shareable — every filter change is reflected in ?params. */
  function syncUrlParams(next) {
    const { status = statusFilter, start = dateFrom, end = dateTo } = next;
    const params = {};
    if (status) params.status = status;
    if (start) params.start = start;
    if (end) params.end = end;
    setSearchParams(params, { replace: true });
  }

  const hasActiveFilters = Boolean(
    debouncedSearch || statusFilter || dateFrom || dateTo
  );

  function clearFilters() {
    setSearch("");
    setDebouncedSearch("");
    setStatusFilter("");
    setDateFrom("");
    setDateTo("");
    setRangeTab("all");
    setOffset(0);
    setSearchParams({}, { replace: true });
  }

  /** Quick tabs — Today/7d/30d set the window instantly; Custom keeps
   * whatever dates are picked in the From/To inputs. */
  function handleRangeTab(value) {
    setRangeTab(value);
    setOffset(0);
    if (value === "custom") return; // dates in the inputs apply live
    const { start, end } = rangeTabToDates(value);
    setDateFrom(start);
    setDateTo(end);
    syncUrlParams({ start, end });
  }

  function handleCreated() {
    setModalOpen(false);
    setOffset(0);
    setSearch("");
    setStatusFilter("");
    setDateFrom("");
    setDateTo("");
    setSearchParams({}, { replace: true });
    fetchOrders();
    // Brief highlight is implicit: newest order appears at the top
  }

  async function handleExport() {
    // Downloads whatever the current filters show — same search/status/
    // dates as the list, so "what I see" and "what I get" always match
    setExporting(true);
    try {
      await api.orders.exportCsv({
        q: debouncedSearch || undefined,
        status: toApiStatuses(statusFilter),
        start: dateFrom || undefined,
        end: dateTo || undefined,
      });
    } catch (err) {
      setError(getErrorMessage(err, "Could not export orders."));
    } finally {
      setExporting(false);
    }
  }

  async function handleCopyLink(code) {
    try {
      await navigator.clipboard.writeText(trackingUrl(code));
      setCopiedCode(code);
      clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopiedCode(null), 2000);
    } catch {
      // Clipboard unavailable (e.g. insecure context) — open instead
      window.open(trackingUrl(code), "_blank");
    }
  }

  const showingFrom = total === 0 ? 0 : offset + 1;
  const showingTo = Math.min(offset + PAGE_SIZE, total);

  // Human summary of the active date window, e.g. "Sep 1 – Sep 2"
  const dateSummary =
    dateFrom && dateTo
      ? dateFrom === dateTo
        ? formatShortDate(dateFrom)
        : `${formatShortDate(dateFrom)} – ${formatShortDate(dateTo)}`
      : dateFrom
        ? `since ${formatShortDate(dateFrom)}`
        : dateTo
          ? `until ${formatShortDate(dateTo)}`
          : null;

  return (
    <div className="orders-page">
      <header className="page-header page-header--row">
        <div>
          <h1>Orders</h1>
          <p>
            {loading
              ? "Loading…"
              : `${total} order${total === 1 ? "" : "s"}${dateSummary ? ` · ${dateSummary}` : " total"}`}
          </p>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="button button--outline"
            onClick={handleExport}
            disabled={exporting || loading || total === 0}
            title="Download the orders you're currently viewing as a CSV file"
          >
            <Icon name="download" size={16} />
            {exporting ? "Exporting…" : "Export CSV"}
          </button>
          <button
            type="button"
            className="button button--primary"
            onClick={() => setModalOpen(true)}
          >
            <Icon name="plus" size={16} />
            New order
          </button>
        </div>
      </header>

      <FreeLimitBanner stats={planStats} />

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}

      <div className="toolbar">
        <div className="toolbar-search-wrap">
          <span className="toolbar-search-icon" aria-hidden="true">
            <Icon name="search" size={16} />
          </span>
          <input
            type="search"
            className="toolbar-search"
            placeholder="Search name, phone, or order #…"
            aria-label="Search orders"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          className="toolbar-select"
          aria-label="Filter by status"
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setOffset(0);
            syncUrlParams({ status: e.target.value });
          }}
        >
          {STATUS_FILTER_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <div
          className="range-tabs"
          role="tablist"
          aria-label="Filter by date range"
        >
          {DATE_RANGE_TABS.map((tab) => (
            <button
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={rangeTab === tab.value}
              className={`range-tab${rangeTab === tab.value ? " range-tab--active" : ""}`}
              onClick={() => handleRangeTab(tab.value)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        {rangeTab === "custom" && (
          <div className="toolbar-dates" role="group" aria-label="Custom date range">
            <input
              type="date"
              className="toolbar-date"
              aria-label="From date"
              title="From date"
              max={dateTo || undefined}
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setOffset(0);
                syncUrlParams({ start: e.target.value });
              }}
            />
            <span className="toolbar-date-sep" aria-hidden="true">–</span>
            <input
              type="date"
              className="toolbar-date"
              aria-label="To date"
              title="To date"
              min={dateFrom || undefined}
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                setOffset(0);
                syncUrlParams({ end: e.target.value });
              }}
            />
          </div>
        )}
        {hasActiveFilters && (
          <button
            type="button"
            className="button button--ghost button--small"
            onClick={clearFilters}
            title="Clear search, status and date filters"
          >
            <Icon name="x" size={13} />
            Clear
          </button>
        )}
      </div>

      {loading && orders.length === 0 ? (
        <SkeletonRows rows={6} />
      ) : orders.length === 0 ? (
        hasActiveFilters ? (
          <EmptyState icon="search" title="No matching orders">
            <p>Try a different search or clear the filters.</p>
          </EmptyState>
        ) : (
          <EmptyState
            icon="package"
            title="No orders yet"
            action={
              <button
                type="button"
                className="button button--primary"
                onClick={() => setModalOpen(true)}
              >
                <Icon name="plus" size={16} />
                New order
              </button>
            }
          >
            <p>Create your first order — it takes 20 seconds.</p>
          </EmptyState>
        )
      ) : isMobile ? (
        <ul className="order-card-list">
          {orders.map((order) => (
            <li key={order.id}>
              <Link to={`/dashboard/orders/${order.id}`} className="order-card">
                <div className="order-card-top">
                  <span className="order-card-number">#{order.order_number}</span>
                  <StatusBadge status={order.status} />
                </div>
                <div className="order-card-customer">
                  <span className="order-card-name">{order.customer_name}</span>
                  {order.source === "form" && (
                    <span className="source-badge" title="Submitted by the customer via your public order form">
                      Form
                    </span>
                  )}
                </div>
                <div className="order-card-meta">
                  <span>
                    {order.items.length} item{order.items.length === 1 ? "" : "s"}
                  </span>
                  <span className="order-card-total">{formatTk(order.total_price)}</span>
                </div>
                <div className="order-card-foot">
                  <span>{formatRelativeTime(order.created_at)}</span>
                  <span className="order-card-go" aria-hidden="true">
                    <Icon name="chevronRight" size={16} />
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <div className="table-wrap">
          <table className="orders-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Customer</th>
                <th>Phone</th>
                <th className="th-num">Items</th>
                <th className="th-num">Total</th>
                <th>Status</th>
                <th>Created</th>
                <th className="th-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id}>
                  <td className="td-mono">#{order.order_number}</td>
                  <td className="td-strong">
                    {order.customer_name}
                    {order.source === "form" && (
                      <span className="source-badge" title="Submitted by the customer via your public order form">
                        Form
                      </span>
                    )}
                  </td>
                  <td className="td-mono">{order.customer_phone}</td>
                  <td className="td-num">{order.items.length}</td>
                  <td className="td-num td-strong">{formatTk(order.total_price)}</td>
                  <td>
                    <StatusBadge status={order.status} />
                  </td>
                  <td className="td-muted">{formatDateTime(order.created_at)}</td>
                  <td className="td-actions">
                    <div className="table-actions">
                      <Link
                        to={`/dashboard/orders/${order.id}`}
                        className="table-action"
                        title="View order"
                      >
                        <Icon name="eye" size={13} />
                        View
                      </Link>
                      <button
                        type="button"
                        className="table-action"
                        onClick={() => handleCopyLink(order.tracking_code)}
                        title="Copy customer tracking link"
                      >
                        <Icon
                          name={copiedCode === order.tracking_code ? "check" : "link"}
                          size={13}
                          className={copiedCode === order.tracking_code ? "table-action-icon--ok" : undefined}
                        />
                        {copiedCode === order.tracking_code ? "Copied" : "Copy link"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {total > PAGE_SIZE && (
        <div className="pagination">
          <span className="pagination-info">
            Showing {showingFrom}–{showingTo} of {total}
          </span>
          <div className="pagination-buttons">
            <button
              type="button"
              className="button button--outline button--small"
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              disabled={offset === 0 || loading}
            >
              <Icon name="chevronLeft" size={15} />
              Previous
            </button>
            <button
              type="button"
              className="button button--outline button--small"
              onClick={() => setOffset(offset + PAGE_SIZE)}
              disabled={offset + PAGE_SIZE >= total || loading}
            >
              Next
              <Icon name="chevronRight" size={15} />
            </button>
          </div>
        </div>
      )}

      {modalOpen && (
        <OrderFormModal onClose={() => setModalOpen(false)} onCreated={handleCreated} />
      )}
    </div>
  );
}
