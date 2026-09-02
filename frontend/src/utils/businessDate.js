/**
 * Business-date helpers — the frontend mirror of backend app/timezone.py.
 *
 * "Today" is the calendar day in Asia/Dhaka (fixed +06:00 since 2009,
 * no DST), so the dashboard's links match what the backend's date
 * filters consider today. Never use toISOString() for "today" — that
 * is UTC and flips the day at 6am Dhaka time.
 */

/** Today in the business timezone as YYYY-MM-DD. */
export function businessToday() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Dhaka" }).format(
    new Date()
  );
}

/** Shift a YYYY-MM-DD string by N days (negative = past). */
export function shiftDays(isoDate, days) {
  const [year, month, day] = isoDate.split("-").map(Number);
  const shifted = new Date(Date.UTC(year, month - 1, day) + days * 86_400_000);
  return shifted.toISOString().slice(0, 10);
}

/**
 * The date window a dashboard range stands for.
 * Returns { start, end } YYYY-MM-DD, or {} for "all time".
 */
export function rangeToDates(range, customRange = null) {
  const today = businessToday();
  if (range === "today") return { start: today, end: today };
  if (range === "7d") return { start: shiftDays(today, -6), end: today };
  if (range === "30d") return { start: shiftDays(today, -29), end: today };
  if (range === "custom" && customRange) return customRange;
  return {}; // all
}

/**
 * Build the /dashboard/orders link for a dashboard card — carries the
 * selected date window (and optionally a status filter) so the orders
 * list shows exactly the orders behind the number the seller clicked.
 */
export function ordersLink(range, customRange = null, status = null) {
  const { start, end } = rangeToDates(range, customRange);
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const query = params.toString();
  return `/dashboard/orders${query ? `?${query}` : ""}`;
}
