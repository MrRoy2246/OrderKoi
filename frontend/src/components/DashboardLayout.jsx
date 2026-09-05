import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import Icon from "./icons";
import Logo from "./Logo";

const STORE_NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: "dashboard", end: true },
  { to: "/dashboard/orders", label: "Orders", icon: "package", end: false },
  { to: "/dashboard/settings", label: "Settings", icon: "settings", end: false },
];

/** Admin nav — grouped by section, only routes that exist. */
const ADMIN_NAV_GROUPS = [
  {
    heading: "Overview",
    items: [{ to: "/admin", label: "Platform Overview", icon: "chartBar", end: true }],
  },
  {
    heading: "Sellers",
    items: [
      { to: "/admin/sellers", label: "Sellers & Plans", icon: "users", end: false },
      { to: "/admin/requests", label: "Upgrade Requests", icon: "creditCard", end: false },
    ],
  },
];

function NavLinks({ items, onNavigate }) {
  return items.map((item) => (
    <NavLink
      key={item.to}
      to={item.to}
      end={item.end}
      onClick={onNavigate}
      className={({ isActive }) => `sidebar-link${isActive ? " sidebar-link--active" : ""}`}
    >
      <span className="sidebar-link-icon" aria-hidden="true">
        <Icon name={item.icon} size={19} />
      </span>
      {item.label}
    </NavLink>
  ));
}

function SidebarBody({ isAdmin, seller, onLogout, onNavigate }) {
  return (
    <>
      <div className="sidebar-brand">
        <Logo size={34} withWordmark />
        {isAdmin && <span className="sidebar-role-tag">Admin</span>}
      </div>

      <nav className="sidebar-nav" aria-label={isAdmin ? "Platform navigation" : "Store navigation"}>
        {isAdmin ? (
          ADMIN_NAV_GROUPS.map((group) => (
            <div key={group.heading} className="sidebar-group">
              <span className="sidebar-group-heading">{group.heading}</span>
              <NavLinks items={group.items} onNavigate={onNavigate} />
            </div>
          ))
        ) : (
          <NavLinks items={STORE_NAV_ITEMS} onNavigate={onNavigate} />
        )}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-store">
          <span className="sidebar-store-name">
            {isAdmin ? "Platform Administration" : seller?.store_name}
          </span>
          <span className="sidebar-store-email">{seller?.email}</span>
        </div>
        <button type="button" className="logout-button" onClick={onLogout}>
          <Icon name="logout" size={17} />
          Log out
        </button>
      </div>
    </>
  );
}

/**
 * App shell for logged-in pages. Admins see only the platform panel;
 * sellers see only their store tools — never both.
 *
 * Desktop: fixed sidebar. Mobile: sticky top bar + slide-in drawer
 * (the old horizontal bar crammed nav + logout into one row).
 */
export default function DashboardLayout() {
  const { seller, logout } = useAuth();
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerRef = useRef(null);

  const isAdmin = seller?.role === "admin";

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  function closeDrawer() {
    setDrawerOpen(false);
  }

  // Escape closes the drawer; focus moves into it while it's open
  useEffect(() => {
    if (!drawerOpen) return;
    function onKeyDown(event) {
      if (event.key === "Escape") closeDrawer();
    }
    document.addEventListener("keydown", onKeyDown);
    drawerRef.current?.querySelector("a, button")?.focus();
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [drawerOpen]);

  return (
    <div className="app-shell">
      {/* Desktop sidebar */}
      <aside className="sidebar">
        <SidebarBody isAdmin={isAdmin} seller={seller} onLogout={handleLogout} />
      </aside>

      {/* Mobile top bar */}
      <header className="topbar">
        <button
          type="button"
          className="topbar-menu"
          aria-expanded={drawerOpen}
          aria-controls="mobile-drawer"
          aria-label="Open navigation menu"
          onClick={() => setDrawerOpen(true)}
        >
          <Icon name="menu" size={20} />
        </button>
        <Logo size={26} withWordmark />
        <span className="topbar-spacer" aria-hidden="true" />
      </header>

      {/* Mobile drawer */}
      {drawerOpen && (
        <div className="drawer-root">
          <button
            type="button"
            className="drawer-overlay"
            aria-label="Close navigation menu"
            onClick={closeDrawer}
          />
          <aside className="drawer" id="mobile-drawer" ref={drawerRef} aria-label="Navigation">
            <div className="drawer-header">
              <Logo size={30} withWordmark />
              <button
                type="button"
                className="drawer-close"
                aria-label="Close menu"
                onClick={closeDrawer}
              >
                <Icon name="x" size={18} />
              </button>
            </div>
            <SidebarBody
              isAdmin={isAdmin}
              seller={seller}
              onLogout={handleLogout}
              onNavigate={closeDrawer}
            />
          </aside>
        </div>
      )}

      <main className="app-content">
        <Outlet />
      </main>
    </div>
  );
}
