import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import AdminProModal from "../components/AdminProModal";
import Icon from "../components/icons";
import { SkeletonRows } from "../components/States";
import { formatDateTime, formatTk, parseServerDate } from "../utils/orderStatus";

const PAGE_SIZE = 20;

const PLAN_TABS = [
  { value: "all", label: "All" },
  { value: "pro", label: "Pro" },
  { value: "free", label: "Free" },
];

function PlanBadge({ plan, expiresAt }) {
  const expired = plan === "pro" && expiresAt && new Date(expiresAt) < new Date();
  return (
    <span className={`badge ${plan === "pro" ? "badge--delivered" : "badge--placed"}`}>
      {plan === "pro" ? (expired ? "Pro (expired)" : "Pro") : "Free"}
    </span>
  );
}

/** Active Pro — same rule as the backend's plan filter: a Pro plan with a
 * past expiry counts as Free. Keeps badges, actions, and the tab counts
 * in sync with what the server returned for the current filter. */
function isProActive(seller) {
  if (seller.plan !== "pro") return false;
  return !seller.plan_expires_at || new Date(seller.plan_expires_at) >= new Date();
}

/** Seller directory for the platform admin — with plan management.
 *
 * Paginated and server-side filtered: the plan tab and search box are
 * query parameters on /admin/sellers, so the page costs the same with
 * 50 sellers or 500,000. */
export default function AdminSellers() {
  const { seller: me } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  // ?plan=pro from the overview's "Pro sellers" tile seeds the filter
  const [planTab, setPlanTab] = useState(searchParams.get("plan") === "pro" ? "pro" : "all");
  const [sellers, setSellers] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  // The shop whose Pro-grant modal is open (seller object, or null)
  const [grantTarget, setGrantTarget] = useState(null);

  // Debounce the search box so we don't hammer the API on every keystroke
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setOffset(0);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const fetchSellers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.admin.sellers({
        plan: planTab,
        q: debouncedSearch,
        limit: PAGE_SIZE,
        offset,
      });
      setSellers(data.sellers);
      setTotal(data.total);
    } catch (err) {
      setError(getErrorMessage(err, "Could not load sellers."));
    } finally {
      setLoading(false);
    }
  }, [planTab, debouncedSearch, offset]);

  useEffect(() => {
    fetchSellers();
  }, [fetchSellers]);

  async function handleTogglePlan(seller) {
    const newPlan = seller.plan === "pro" ? "free" : "pro";
    if (
      newPlan === "free" &&
      !window.confirm(`Downgrade ${seller.store_name} to the free plan?`)
    ) {
      return;
    }

    setBusyId(seller.id);
    setError(null);
    try {
      const updated = await api.admin.setPlan(seller.id, newPlan);
      setSellers((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
    } catch (err) {
      setError(getErrorMessage(err, "Could not update the plan."));
    } finally {
      setBusyId(null);
    }
  }

  /** Apply the modal's result to the list and close it. */
  function handleGranted(updated) {
    setSellers((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
    setGrantTarget(null);
  }

  const showingFrom = total === 0 ? 0 : offset + 1;
  const showingTo = Math.min(offset + PAGE_SIZE, total);

  const planSummary =
    planTab === "all"
      ? `${total} account${total === 1 ? "" : "s"} on your platform`
      : `${total} ${planTab === "pro" ? "Pro" : "Free"} seller${total === 1 ? "" : "s"}`;

  return (
    <div className="admin-page">
      <header className="page-header">
        <h1>Sellers &amp; Plans</h1>
        <p>{planSummary}.</p>
      </header>

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
            placeholder="Search store, email, or slug…"
            aria-label="Search sellers"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      <div className="range-tabs" role="tablist" aria-label="Filter by plan">
        {PLAN_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={planTab === tab.value}
            className={`range-tab${planTab === tab.value ? " range-tab--active" : ""}`}
            onClick={() => {
              setPlanTab(tab.value);
              setOffset(0);
              setSearchParams(tab.value === "all" ? {} : { plan: tab.value }, { replace: true });
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading ? (
        <SkeletonRows rows={6} />
      ) : sellers.length === 0 ? (
        <p className="muted-note">
          {debouncedSearch
            ? "No sellers match that search."
            : planTab === "pro"
              ? "No sellers on an active Pro plan yet."
              : planTab === "free"
                ? "No sellers on the Free plan."
                : "No sellers yet."}
        </p>
      ) : (
      <div className="table-wrap">
        <table className="orders-table">
          <thead>
            <tr>
              <th>Store</th>
              <th>Email</th>
              <th>Role</th>
              <th>Plan</th>
              <th>Orders</th>
              <th>Order value</th>
              <th>Joined</th>
              <th className="th-actions">Plan action</th>
            </tr>
          </thead>
          <tbody>
            {sellers.map((seller) => (
              <tr key={seller.id}>
                <td className="td-strong">
                  <Link
                    to={`/admin/sellers/${seller.id}`}
                    className="shop-link"
                    title={`Open ${seller.store_name}'s performance, revenue, and report`}
                  >
                    {seller.store_name}
                  </Link>
                </td>
                <td className="td-muted">{seller.email}</td>
                <td>
                  <RoleBadge role={seller.role} />
                </td>
                <td>
                  <PlanBadge plan={seller.plan} expiresAt={seller.plan_expires_at} />
                  {seller.plan === "pro" && seller.plan_expires_at && (
                    <span className="plan-expiry">
                      {" "}
                      until {parseServerDate(seller.plan_expires_at).toLocaleDateString()}
                    </span>
                  )}
                </td>
                <td className="td-strong">{seller.orders_count}</td>
                <td className="td-strong">{formatTk(seller.revenue)}</td>
                <td className="td-muted">{formatDateTime(seller.created_at)}</td>
                <td className="td-actions">
                  {seller.role === "admin" ? (
                    <span className="td-muted">—</span>
                  ) : (
                    <div className="plan-actions">
                      <button
                        type="button"
                        className="table-action"
                        onClick={() => setGrantTarget(seller)}
                        disabled={busyId === seller.id}
                        title={
                          isProActive(seller)
                            ? `Add Pro time for ${seller.store_name}`
                            : `Activate Pro for ${seller.store_name}`
                        }
                      >
                        <Icon name="sparkles" size={13} />
                        {busyId === seller.id
                          ? "Saving…"
                          : isProActive(seller)
                            ? "Extend Pro"
                            : seller.plan === "pro"
                              ? "Renew Pro"
                              : "Upgrade to Pro"}
                      </button>
                      {isProActive(seller) && (
                        <button
                          type="button"
                          className="table-action table-action--danger"
                          onClick={() => handleTogglePlan(seller)}
                          disabled={busyId === seller.id}
                          title={`Downgrade ${seller.store_name} to the free plan`}
                        >
                          <Icon name="x" size={13} />
                        </button>
                      )}
                    </div>
                  )}
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

      <p className="muted-note">
        You are logged in as <strong>{me?.email}</strong> (admin). Admin accounts manage the
        platform; sellers run the shops.
      </p>

      {grantTarget && (
        <AdminProModal
          seller={grantTarget}
          onClose={() => setGrantTarget(null)}
          onDone={handleGranted}
        />
      )}
    </div>
  );
}
