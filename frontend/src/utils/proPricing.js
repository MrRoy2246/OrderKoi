/**
 * Pro pricing — fetched live from the backend (GET /public/stores/pricing),
 * with the current defaults as a fallback so the UI still renders if the
 * API is briefly unreachable.
 *
 * Prices are env-driven on the backend (PRO_PRICE_1M/6M/12M in
 * backend/.env): change a value there, restart the backend, and every
 * surface (Settings pricing cards, admin's expected-payment check,
 * subscription revenue stats) follows. No frontend rebuild, no code
 * edit — offers can change any time.
 */

import { API_URL } from "../api/client";

/** Fallback when the pricing endpoint can't be reached (also the
 * documented defaults of PRO_PRICE_1M/6M/12M). */
export const PRO_OPTIONS_FALLBACK = [
  { months: 1, price: 350, note: "try Pro out" },
  { months: 6, price: 1750, note: "save 17%" },
  { months: 12, price: 2900, note: "save 31%" },
];

/** Marketing notes per duration — these are presentation, not price. */
const PRO_NOTES = {
  1: "try Pro out",
  6: "save 17%",
  12: "save 31%",
};

let cachedOptions = null;
let inflight = null;

/**
 * Fetch the current Pro options (months, price) from the backend.
 * Returns a promise; resolves with the live prices or (on any error)
 * the fallback. Subsequent calls share one request (cached after it
 * settles — prices are cheap to re-fetch per page load, the cache
 * just de-dupes concurrent mounts).
 */
export function fetchProOptions() {
  if (cachedOptions) return Promise.resolve(cachedOptions);
  if (inflight) return inflight;

  inflight = fetch(`${API_URL}/public/stores/pricing`)
    .then((response) => {
      if (!response.ok) throw new Error(`pricing: ${response.status}`);
      return response.json();
    })
    .then((entries) => {
      const options = entries
        .slice()
        .sort((a, b) => a.months - b.months)
        .map((e) => ({ months: e.months, price: e.price, note: PRO_NOTES[e.months] ?? "" }));
      cachedOptions = options.length ? options : PRO_OPTIONS_FALLBACK;
      return cachedOptions;
    })
    .catch(() => PRO_OPTIONS_FALLBACK) // offline → defaults, UI keeps working
    .finally(() => {
      inflight = null;
    });

  return inflight;
}

/** The price a seller should have paid for a given duration — from the
 * most recently fetched options (fallback before the first load). */
export function proPriceFor(months) {
  const options = cachedOptions || PRO_OPTIONS_FALLBACK;
  return options.find((option) => option.months === months)?.price ?? null;
}

/** Reset the cache (tests). */
export function _resetProPricingCache() {
  cachedOptions = null;
  inflight = null;
}
