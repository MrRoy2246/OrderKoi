/**
 * The OrderKoi brand mark — a vermilion rounded square with a white
 * "koi curl": an open swirl that reads as a fish turning in water,
 * i.e. an order moving through its flow. Subtle, not cartoonish.
 *
 * <Logo size={32} />          — just the mark
 * <Logo size={32} withWordmark /> — mark + "OrderKoi" wordmark lockup
 */

export function KoiMark({ size = 32, className = "" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      className={className}
      role="img"
      aria-label="OrderKoi"
      focusable="false"
    >
      <defs>
        <linearGradient id="koi-mark-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#F0661F" />
          <stop offset="1" stopColor="#D9480F" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#koi-mark-bg)" />
      {/* the koi curl: an open counter-clockwise swirl + head dot */}
      <path
        d="M19.6 8.9a7.4 7.4 0 1 0 2.6 12.4"
        fill="none"
        stroke="#fff"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <circle cx="20.2" cy="12.4" r="2.1" fill="#fff" />
    </svg>
  );
}

export default function Logo({ size = 32, withWordmark = false, className = "" }) {
  if (!withWordmark) return <KoiMark size={size} className={className} />;
  return (
    <span className={`logo-lockup ${className}`.trim()}>
      <KoiMark size={size} />
      <span className="logo-wordmark">OrderKoi</span>
    </span>
  );
}
