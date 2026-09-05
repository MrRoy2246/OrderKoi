import { useMemo } from "react";
import { formatTk } from "../utils/orderStatus";

/**
 * Shared, dependency-free charts — the design system's visual language
 * (koi vermilion bars, soft tints, quiet labels), like the dashboard's
 * original pure-CSS bar chart but reusable across pages.
 *
 * All charts accept a series of { key, count, value? } buckets in
 * oldest-first order and render an accessible, responsive chart with
 * hover tooltips (via native title attributes) and empty states.
 */

/** Human label for a YYYY-MM month key. */
function monthLabel(key, { short = true } = {}) {
  const [year, month] = key.split("-").map(Number);
  return new Date(year, month - 1).toLocaleDateString(undefined, {
    month: short ? "short" : "long",
    year: short ? "2-digit" : "numeric",
  });
}

/** Thin out labels so long series stay readable. */
function labelEvery(total, target = 10) {
  return Math.max(1, Math.ceil(total / target));
}

/** A bar chart with an optional second series (value) shown as a line. */
export function BarChart({ data, valuePrefix = "" }) {
  const max = Math.max(...data.map((d) => d.count), 1);
  const maxValue = Math.max(...data.map((d) => d.value ?? 0), 1);
  const every = labelEvery(data.length);

  // SVG polyline for the value series, scaled to the chart area
  const points = data
    .map((d, i) => {
      const x = ((i + 0.5) / data.length) * 100;
      const y = 100 - ((d.value ?? 0) / maxValue) * 100;
      return `${x},${Math.max(y, 2)}`;
    })
    .join(" ");

  return (
    <div
      className="chart"
      role="img"
      aria-label="Bar chart with revenue line overlay"
    >
      {data.map((d, i) => {
        const isMonth = d.key.includes("-");
        const label = isMonth ? monthLabel(d.key) : d.key;
        const tip = valuePrefix
          ? `${label}: ${d.count} · ${valuePrefix}${d.value?.toLocaleString()}`
          : `${label}: ${d.count}`;
        return (
          <div key={d.key} className="chart-bar-wrap" title={tip}>
            <span className="chart-count">{d.count > 0 ? d.count : ""}</span>
            <div
              className={`chart-bar${d.count > 0 ? "" : " chart-bar--empty"}`}
              style={{ height: `${Math.max((d.count / max) * 100, d.count > 0 ? 6 : 2)}%` }}
            />
            <span className="chart-label">
              {i % every === 0 || i === data.length - 1 ? label.split(" ")[0] : ""}
            </span>
          </div>
        );
      })}
      {valuePrefix && (
        <svg
          className="chart-line-svg"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <polyline points={points} className="chart-line" />
        </svg>
      )}
    </div>
  );
}

/**
 * A month-bucket bar chart with money labels — used on the admin
 * overview for GMV and subscription revenue.
 */
export function MonthlyBars({ data, valueLabel = "value" }) {
  const max = Math.max(...data.map((d) => d.count), 1);
  const every = labelEvery(data.length, 12);

  return (
    <div className="chart" role="img" aria-label={`${valueLabel} by month`}>
      {data.map((d, i) => (
        <div
          key={d.key}
          className="chart-bar-wrap"
          title={`${monthLabel(d.key, { short: false })}: ${valueLabel} ${formatTk(d.value)} · ${d.count} orders`}
        >
          <span className="chart-count">{d.count > 0 ? d.count : ""}</span>
          <div
            className={`chart-bar${d.count > 0 ? "" : " chart-bar--empty"}`}
            style={{ height: `${Math.max((d.count / max) * 100, d.count > 0 ? 6 : 2)}%` }}
          />
          <span className="chart-label">
            {i % every === 0 || i === data.length - 1 ? monthLabel(d.key) : ""}
          </span>
        </div>
      ))}
    </div>
  );
}

/**
 * A donut chart — proportions of a whole (plan mix, status mix).
 * `slices: [{ label, value, color }]` — CSS conic-gradient, no JS math
 * libraries needed. Center shows a caption.
 */
export function DonutChart({ slices, caption, size = 150 }) {
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  // Build conic-gradient stops via reduce — cumulative percentages
  const stops = slices
    .filter((s) => s.value > 0)
    .reduce(
      (acc, s) => {
        const end = acc.cursor + s.value;
        const gradient = `${s.color} ${(acc.cursor / total) * 100}% ${(end / total) * 100}%`;
        return { cursor: end, list: [...acc.list, gradient] };
      },
      { cursor: 0, list: [] }
    )
    .list.join(", ");

  const gradient = stops.length > 0 ? stops : "var(--border) 0% 100%";

  return (
    <div className="donut-wrap">
      <div
        className="donut"
        style={{
          width: size,
          height: size,
          background: `conic-gradient(${gradient})`,
        }}
        role="img"
        aria-label={slices
          .filter((s) => s.value > 0)
          .map((s) => `${s.label}: ${s.value}`)
          .join(", ")}
      >
        <div className="donut-hole">
          <span className="donut-caption">{caption}</span>
        </div>
      </div>
      <ul className="donut-legend">
        {slices.map(
          (s) =>
            s.value > 0 && (
              <li key={s.label} className="donut-legend-item">
                <span
                  className="badge-dot"
                  style={{ background: s.color }}
                  aria-hidden="true"
                />
                <span className="donut-legend-label">{s.label}</span>
                <span className="donut-legend-value">
                  {total > 0 ? Math.round((s.value / total) * 100) : 0}%
                </span>
              </li>
            )
        )}
      </ul>
    </div>
  );
}

/**
 * Compact sparkline for stat tiles — a tiny SVG line chart with a
 * subtle area fill. Purely decorative context, so aria-hidden.
 */
export function Sparkline({ data, color = "var(--primary)", width = 90, height = 28 }) {
  const { line, area } = useMemo(() => {
    if (!data.length) return { line: "", area: "" };
    const max = Math.max(...data, 1);
    const min = Math.min(...data, 0);
    const range = max - min || 1;
    const stepX = width / Math.max(data.length - 1, 1);
    const pts = data.map((v, i) => {
      const x = i * stepX;
      const y = height - ((v - min) / range) * (height - 4) - 2;
      return [x, y];
    });
    const linePts = pts.map(([x, y]) => `${x},${y}`).join(" ");
    return {
      line: linePts,
      area: `0,${height} ${linePts} ${width},${height}`,
    };
  }, [data, width, height]);

  if (!data.length) return null;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="sparkline"
      aria-hidden="true"
      focusable="false"
    >
      <polygon points={area} fill={color} opacity="0.12" />
      <polyline
        points={line}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
