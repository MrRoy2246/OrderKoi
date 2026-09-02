/**
 * Pro pricing — one source of truth for what each duration costs.
 * Sellers see these on the Settings page; the admin sees the expected
 * amount on upgrade requests (to check against the bKash/Nagad
 * statement). Edit here and both stay in sync.
 */
export const PRO_OPTIONS = [
  { months: 1, price: 299, note: "try Pro out" },
  { months: 6, price: 1499, note: "save 16%" },
  { months: 12, price: 2499, note: "save 30%" },
];

/** The price a seller should have paid for a given duration. */
export function proPriceFor(months) {
  return PRO_OPTIONS.find((option) => option.months === months)?.price ?? null;
}
