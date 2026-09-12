/**
 * API client — single place where the frontend talks to the backend.
 * Handles the auth token, JSON encoding, and error normalization.
 */

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const TOKEN_KEY = "orderkoi_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

/**
 * Extract a human-readable message from an API error.
 * FastAPI returns {"detail": "..."} or {"detail": [{loc, msg}, ...]} for 422s.
 */
export function getErrorMessage(error, fallback = "Something went wrong. Please try again.") {
  const detail = error?.data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    const field = Array.isArray(first.loc) ? first.loc.at(-1) : null;
    const message = first.msg || "Invalid value";
    return field ? `${field}: ${message}` : message;
  }
  return fallback;
}

/**
 * Endpoints that can legitimately return 401 as a *result* (wrong
 * password, bad reset token) — a 401 from these is a form error the
 * page displays, not an expired session.
 */
const AUTH_RESULT_PATHS = [
  "/auth/login",
  "/auth/signup",
  "/auth/forgot-password",
  "/auth/reset-password",
  "/auth/verify-email",
  "/auth/resend-verification",
];

function isAuthResultPath(path) {
  return AUTH_RESULT_PATHS.some((prefix) => path === prefix || path.startsWith(`${prefix}?`));
}

/** Expired/invalid session: drop the token and return to login.
 * A full page load is deliberate — it resets all React state cleanly. */
function handleExpiredSession() {
  clearToken();
  window.location.assign("/login");
}

/**
 * Perform a JSON request to the backend.
 * @param {string} path - e.g. "/auth/login" or "/orders"
 * @param {RequestInit} options - fetch options (method, body, ...)
 * @returns {Promise<any>} parsed JSON response
 * @throws {Error} with `.status` and `.data` when the API returns an error
 */
export async function request(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (!response.ok) {
    // A 401 on a protected endpoint means the token expired (24h) or
    // was revoked. Show the login page instead of a cryptic error —
    // but never on the auth forms themselves (wrong password is a 401
    // there and must stay a visible form error).
    if (response.status === 401 && !isAuthResultPath(path)) {
      handleExpiredSession();
    }

    const error = new Error(`API request failed: ${response.status}`);
    error.status = response.status;
    try {
      error.data = await response.json();
    } catch {
      error.data = null; // response had no JSON body
    }
    throw error;
  }

  // 204 No Content (e.g. delete endpoints)
  if (response.status === 204) return null;

  return response.json();
}

/**
 * Fetch a file with auth and trigger a browser download of it.
 * Uses the server's Content-Disposition filename when present.
 * @param {string} path - e.g. "/orders/export?status=placed"
 * @param {string} fallbackName - filename if the server sends none
 * @throws {Error} with `.status` and `.data` when the API returns an error
 */
export async function downloadFile(path, fallbackName) {
  const headers = {};
  const token = getToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, { headers });

  if (!response.ok) {
    const error = new Error(`API request failed: ${response.status}`);
    error.status = response.status;
    try {
      error.data = await response.json();
    } catch {
      error.data = null;
    }
    throw error;
  }

  const disposition = response.headers.get("Content-Disposition") || "";
  const filename = disposition.match(/filename="?([^";]+)"?/)?.[1] || fallbackName;

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/** Build a query string, skipping empty values and repeating arrays
 * (e.g. ?status=placed&status=confirmed). */
function toQueryString(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    if (Array.isArray(value)) {
      value.forEach((v) => search.append(key, v));
    } else {
      search.append(key, value);
    }
  });
  const query = search.toString();
  return query ? `?${query}` : "";
}

/** Namespaced API methods — one entry per backend endpoint group. */
export const api = {
  auth: {
    signup: (payload) =>
      request("/auth/signup", { method: "POST", body: JSON.stringify(payload) }),
    login: (email, password) =>
      request("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      }),
    me: () => request("/auth/me"),
    updateMe: (payload) =>
      request("/auth/me", { method: "PATCH", body: JSON.stringify(payload) }),
    forgotPassword: (email) =>
      request("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email }),
      }),
    resetPassword: (token, newPassword) =>
      request("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, new_password: newPassword }),
      }),
    // Consumes the token from the signup email's verification link
    verifyEmail: (token) =>
      request(`/auth/verify-email?token=${encodeURIComponent(token)}`),
    // Sends a fresh verification link (anti-enumeration: same response
    // whether or not the account exists)
    resendVerification: (email) =>
      request("/auth/resend-verification", {
        method: "POST",
        body: JSON.stringify({ email }),
      }),
    upgradeRequests: () => request("/auth/upgrade-requests"),
    // My subscription events — activations, renewals, cancellations
    subscriptionHistory: () => request("/auth/subscription-history"),
    requestUpgrade: (payload) =>
      request("/auth/upgrade-requests", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    cancelSubscription: () =>
      request("/auth/cancel-subscription", { method: "POST" }),
  },
  stats: {
    // params: { range: "today"|"7d"|"30d"|"all"|"custom", start, end } —
    // start/end are YYYY-MM-DD, required when range is "custom"
    summary: (params = {}) => {
      const query = new URLSearchParams(
        Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== "")
      ).toString();
      return request(`/orders/stats/summary${query ? `?${query}` : ""}`);
    },
  },
  orders: {
    list: (params = {}) => request(`/orders${toQueryString(params)}`),
    // Downloads the current filter's orders as a CSV file
    exportCsv: (params = {}) =>
      downloadFile(`/orders/export${toQueryString(params)}`, "orders.csv"),
    get: (id) => request(`/orders/${id}`),
    create: (payload) =>
      request("/orders", { method: "POST", body: JSON.stringify(payload) }),
    update: (id, payload) =>
      request(`/orders/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
    updateStatus: (id, status) =>
      request(`/orders/${id}/status`, { method: "PATCH", body: JSON.stringify({ status }) }),
    remove: (id) => request(`/orders/${id}`, { method: "DELETE" }),
  },
  tracking: {
    // Phase 5 will use this
    get: (code) => request(`/track/${encodeURIComponent(code)}`),
  },
  publicForm: {
    // The customer-facing order form (no login involved)
    getStore: (slug) => request(`/public/stores/${encodeURIComponent(slug)}`),
    submitOrder: (slug, payload) =>
      request(`/public/stores/${encodeURIComponent(slug)}/orders`, {
        method: "POST",
        body: JSON.stringify(payload),
      }),
  },
  admin: {
    sellers: (params = {}) => request(`/admin/sellers${toQueryString(params)}`),
    stats: (params = {}) => request(`/admin/stats${toQueryString(params)}`),
    setPlan: (sellerId, plan, months, comp = false) =>
      request(`/admin/sellers/${sellerId}/plan`, {
        method: "PATCH",
        body: JSON.stringify({ plan, ...(months ? { months } : {}), comp }),
      }),
    upgradeRequests: () => request("/admin/upgrade-requests"),
    handleUpgradeRequest: (requestId, action) =>
      request(`/admin/upgrade-requests/${requestId}`, {
        method: "PATCH",
        body: JSON.stringify({ action }),
      }),
    // Subscription ledger — every subscribe/renew/cancel, newest first
    subscriptionEvents: () => request("/admin/subscription-events"),
    // One shop's performance over a date window (daily orders/revenue
    // series, totals, AOV, status counts) — powers the shop-detail page
    sellerStats: (sellerId, params = {}) =>
      request(`/admin/sellers/${sellerId}/stats${toQueryString(params)}`),
    // The same window's orders as a downloadable CSV report
    exportSellerOrdersCsv: (sellerId, params = {}) =>
      downloadFile(
        `/admin/sellers/${sellerId}/orders.csv${toQueryString(params)}`,
        "orders.csv",
      ),
  },
};
