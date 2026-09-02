/** Order status metadata shared across the UI. Mirrors the backend workflow. */

export const STATUS_META = {
  placed: {
    label: "Placed",
    className: "badge--placed",
    description: "Order received",
    icon: "inbox",
  },
  confirmed: {
    label: "Confirmed",
    className: "badge--confirmed",
    description: "Seller confirmed the order",
    icon: "check",
  },
  shipped: {
    label: "Shipped",
    className: "badge--shipped",
    description: "On the way to the customer",
    icon: "truck",
  },
  delivered: {
    label: "Delivered",
    className: "badge--delivered",
    description: "Order delivered",
    icon: "packageCheck",
  },
  cancelled: {
    label: "Cancelled",
    className: "badge--cancelled",
    description: "Order cancelled",
    icon: "x",
  },
};

/** Valid next statuses — must stay in sync with the backend's VALID_TRANSITIONS. */
export const NEXT_STATUSES = {
  placed: ["confirmed", "cancelled"],
  confirmed: ["shipped", "cancelled"],
  shipped: ["delivered", "cancelled"],
  delivered: [],
  cancelled: [],
};

export const STATUS_FILTER_OPTIONS = [
  { value: "", label: "All statuses" },
  // "Pending" = the seller's current workload (placed + confirmed)
  { value: "pending", label: "Pending (awaiting action)" },
  ...Object.keys(STATUS_META).map((value) => ({ value, label: STATUS_META[value].label })),
];

export function formatTk(amount) {
  return `৳${Number(amount).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

/**
 * Parse a backend timestamp into a Date.
 *
 * The API sends some timestamps with a UTC marker ("...Z", e.g.
 * status_history) and some without (e.g. created_at — naive UTC).
 * Without a marker, JavaScript would read the value as LOCAL time,
 * making displayed times 6 hours early (Dhaka is UTC+6). This parser
 * stamps marker-less values as UTC so every page agrees.
 */
export function parseServerDate(iso) {
  const hasTimezone = /Z$|[+-]\d{2}:?\d{2}$/.test(iso);
  return new Date(hasTimezone ? iso : `${iso}Z`);
}

export function formatDateTime(iso) {
  if (!iso) return "—";
  return parseServerDate(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** "2 hours ago" / "just now" — used on mobile order cards where
 * space is tight and the exact minute matters less than the recency. */
export function formatRelativeTime(iso) {
  if (!iso) return "—";
  const seconds = Math.floor((Date.now() - parseServerDate(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} day${days === 1 ? "" : "s"} ago`;
  return formatDateTime(iso);
}

/** Full public tracking URL for an order (page built in Phase 5). */
export function trackingUrl(code) {
  return `${window.location.origin}/track/${code}`;
}
