import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import AdminProModal from "../components/AdminProModal";
import Icon from "../components/icons";
import { SkeletonRows } from "../components/States";
import { formatDateTime, formatTk, parseServerDate } from "../utils/orderStatus";

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

/** Active Pro — same rule as the overview's counts: a Pro plan with a
 * past expiry counts as Free. Keeps tile numbers and list in sync. */
function isProActive(seller) {
  if (seller.plan !== "pro") return false;
  return !seller.plan_expires_at || new Date(seller.plan_expires_at) >= new Date();
}

function RoleBadge({ role }) {
  if (role !== "admin") return null;
  return <span className="badge badge--shipped">Admin</span>;
}

/** Seller directory for the platform admin — with plan management. */
export default function AdminSellers() {
  const { seller: me } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  // ?plan=pro from the overview's "Pro sellers" tile seeds the filter
  const initialTab = searchParams.get("plan") === "pro" ? "pro" : "all";
  const [planTab, setPlanTab] = useState(initialTab);
  const [sellers, setSellers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  // The shop whose Pro-grant modal is open (seller object, or null)
  const [grantTarget, setGrantTarget] = useState(null);

  useEffect(() => {
    let cancelled = false;

    api.admin
      .sellers()
      .then((data) => {
        if (!cancelled) setSellers(data);
      })
      .catch((err) => {
        if (!cancelled) setError(getErrorMessage(err, "Could not load sellers."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

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

  if (loading) {
    return (
      <div className="admin-page">
        <SkeletonRows rows={6} />
      </div>
    );
  }

  // Platform shops only — your own admin account isn't a seller, so it
  // stays off the list (this also matches the overview's seller count)
  const shops = sellers.filter((s) => s.role !== "admin");
  const filtered =
    planTab === "all"
      ? shops
      : shops.filter((s) => (planTab === "pro" ? isProActive(s) : !isProActive(s)));

  const planSummary =
    planTab === "all"
      ? `${shops.length} account${shops.length === 1 ? "" : "s"} on your platform`
      : `${filtered.length} ${planTab === "pro" ? "Pro" : "Free"} seller${filtered.length === 1 ? "" : "s"}`;

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
              setSearchParams(tab.value === "all" ? {} : { plan: tab.value }, { replace: true });
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <p className="muted-note">
          {planTab === "pro"
            ? "No sellers on an active Pro plan yet."
            : "No sellers on the Free plan."}
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
            {filtered.map((seller) => (
              <tr key={seller.id}>
                <td className="td-strong">{seller.store_name}</td>
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
