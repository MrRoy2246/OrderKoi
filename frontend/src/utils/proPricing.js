/**
 * Public business configuration — fetched live from the backend
 * (GET /public/stores/pricing), with current defaults as fallback so
 * the UI still renders if the API is briefly unreachable.
 *
 * Everything here is env-driven on the backend (PRO_PRICE_1M/6M/12M,
 * FREE_PLAN_ORDERS, BKASH_NUMBER, BKASH_TYPE, SUPPORT_EMAIL in
 * the repo-root .env): change a value there, restart the backend, and every
 * surface — Settings pricing cards, free-plan meter and banners,
 * payment instructions, legal-page contact details, admin
 * expected-payment checks — follows. No frontend rebuild, no code
 * edit; offers can change any time.
 */

import { API_URL } from "../api/client";

/** Fallback values when the config endpoint can't be reached (also the
 * documented defaults in the repo-root .env.example). */
export const PRO_OPTIONS_FALLBACK = [
  { months: 1, price: 350, note: "try Pro out" },
  { months: 6, price: 1750, note: "save 17%" },
  { months: 12, price: 2900, note: "save 31%" },
];

export const PUBLIC_CONFIG_FALLBACK = {
  pro: PRO_OPTIONS_FALLBACK,
  free_plan_orders: 15,
  bkash_number: "01736060259",
  bkash_type: "Personal",
  support_email: "abinroy510@gmail.com",
};

/** Marketing notes per duration — presentation copy, not price. */
const PRO_NOTES = {
  1: "try Pro out",
  6: "save 17%",
  12: "save 31%",
};

/** Decorate server price entries with their display notes. */
function withNotes(entries) {
  return entries.map((e) => ({
    months: e.months,
    price: e.price,
    note: PRO_NOTES[e.months] ?? "",
  }));
}

let cachedConfig = null;
let inflight = null;

/**
 * Normalize the config response. Accepts the current shape
 * ({pro: [...], free_plan_orders, bkash_number, ...}) and the
 * historical prices-only array (a stale backend deploy) — the latter
 * falls back to defaults for the non-price fields.
 */
function normalize(data) {
  if (Array.isArray(data)) {
    // Old shape: [{months, price}] — prices only
    const options = withNotes(data.slice().sort((a, b) => a.months - b.months));
    return { ...PUBLIC_CONFIG_FALLBACK, pro: options.length ? options : PRO_OPTIONS_FALLBACK };
  }
  const options = withNotes(
    (data.pro ?? []).slice().sort((a, b) => a.months - b.months)
  );
  return {
    pro: options.length ? options : PRO_OPTIONS_FALLBACK,
    free_plan_orders: data.free_plan_orders ?? PUBLIC_CONFIG_FALLBACK.free_plan_orders,
    bkash_number: data.bkash_number ?? PUBLIC_CONFIG_FALLBACK.bkash_number,
    bkash_type: data.bkash_type ?? PUBLIC_CONFIG_FALLBACK.bkash_type,
    support_email: data.support_email ?? PUBLIC_CONFIG_FALLBACK.support_email,
  };
}

/**
 * Fetch the current public config from the backend. Returns a promise;
 * resolves with the live values or (on any error) the fallback.
 * Concurrent callers share one request; the result is cached for the
 * page lifetime (config is cheap to re-fetch per load, the cache just
 * de-dupes concurrent mounts).
 */
export function fetchPublicConfig() {
  if (cachedConfig) return Promise.resolve(cachedConfig);
  if (inflight) return inflight;

  inflight = fetch(`${API_URL}/public/stores/pricing`)
    .then((response) => {
      if (!response.ok) throw new Error(`config: ${response.status}`);
      return response.json();
    })
    .then((data) => {
      cachedConfig = normalize(data);
      return cachedConfig;
    })
    .catch(() => PUBLIC_CONFIG_FALLBACK) // offline → defaults, UI keeps working
    .finally(() => {
      inflight = null;
    });

  return inflight;
}

/** The Pro options most recently fetched (fallback before first load). */
export function getProOptions() {
  return cachedConfig?.pro ?? PRO_OPTIONS_FALLBACK;
}

/** The price a seller should have paid for a given duration — from the
 * most recently fetched config (fallback before the first load). */
export function proPriceFor(months) {
  return getProOptions().find((option) => option.months === months)?.price ?? null;
}

/** The free-plan order allowance (one-time, lifetime). */
export function getFreePlanOrders() {
  return cachedConfig?.free_plan_orders ?? PUBLIC_CONFIG_FALLBACK.free_plan_orders;
}

/** The bKash number + account type sellers send Pro payments to. */
export function getBkash() {
  return {
    number: cachedConfig?.bkash_number ?? PUBLIC_CONFIG_FALLBACK.bkash_number,
    type: cachedConfig?.bkash_type ?? PUBLIC_CONFIG_FALLBACK.bkash_type,
  };
}

/** The public support/contact email. */
export function getSupportEmail() {
  return cachedConfig?.support_email ?? PUBLIC_CONFIG_FALLBACK.support_email;
}

/** Reset the cache (tests). */
export function _resetConfigCache() {
  cachedConfig = null;
  inflight = null;
}
