import { useMemo, useState } from "react";
import { formatTk } from "../utils/orderStatus";

/**
 * Shared, dependency-free charts — the design system's visual language
 * (koi vermilion marks on warm paper), built to the chart spec:
 * thin marks (<= 24px), 4px rounded data-ends square at the baseline,
 * hairline solid gridlines, clean y-ticks, per-mark hover tooltips,
 * and a screen-reader table twin for every chart.
 *
 * Every chart is single-series (one mark set per plot — never a
 * dual-axis overlay; two measures become a measure switch, not a
 * second axis). Filter rows live OUTSIDE these components, in one row
 * above the charts they scope.
 *
 * Data contract: buckets shaped { key, value } — key is "YYYY-MM-DD"
 * (daily) or "YYYY-MM" (monthly), value is the number to plot.
 */

/* ---------- scale helpers ---------- */

/** A "nice" axis maximum: 1/2/2.5/5 x 10^n covering the data max. */
function niceMax(value) {
  if (value <= 0) return 1;
  const exponent = Math.floor(Math.log10(value));
  const fraction = value / 10 ** exponent;
  const niceFraction =
    fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
  return niceFraction * 10 ** exponent;
}

/** 3-4 clean tick values from 0 up to the nice max. */
function ticksFor(max) {
  const steps = max <= 2.5 ? 2 : max <= 10 ? 2.5 : 3;
  const step = max / steps;
  return Array.from({ length: steps + 1 }, (_, i) => Math.round(step * i));
}

/** Compact value text for axis ticks and tooltips. */
function compact(value) {
  if (Math.abs(value) >= 100000) return `${Math.round(value / 1000)}K`;
  if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(value % 1000 === 0 ? 0 : 1)}K`;
  return value.toLocaleString();
}

/* ---------- labels ---------- */

/** Human label for a YYYY-MM month key. */
export function monthLabel(key, { short = true } = {}) {
  if (!key) return "";
  const [year, month] = key.split("-").map(Number);
  if (!year || !month) return "";
  return new Date(year, month - 1).toLocaleDateString(undefined, {
    month: short ? "short" : "long",
    year: short ? "2-digit" : "numeric",
  });
}

/** Human label for a YYYY-MM-DD day key. */
function dayLabel(key, { withMonth = false } = {}) {
  if (!key) return "";
  const [year, month, day] = key.split("-").map(Number);
  if (!year || !month || !day) return "";
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    day: "numeric",
    ...(withMonth ? { month: "short" } : {}),
  });
}

/** Label for either key shape. */
function keyLabel(key, { full = false } = {}) {
  if (!key) return "";
  return key.length === 10
    ? dayLabel(key, { withMonth: full })
    : monthLabel(key, { short: !full });
}

/* ---------- the bar chart ---------- */

/**
 * A time-series column chart, rendered as SVG.
 *
 * data: [{ key, value }] oldest-first.
 * measure: "count" (plain numbers) or "money" (Tk formatting).
 * barColor: the series color — one hue per chart (single series, so
 * the chart title names it; no legend box).
 */
export function BarChart({ data, measure = "count", barColor = "var(--primary)", height = 200 }) {
  const [hovered, setHovered] = useState(null);
  const isMoney = measure === "money";

  const values = data.map((d) => d.value);
  const max = niceMax(Math.max(...values, 0));
  const ticks = ticksFor(max);

  const plotHeight = height;
  const leftPad = 42;
  const chartWidth = 1000; // user units; the viewBox scales to the box
  const svgHeight = plotHeight + 6; // room for round caps at the baseline

  const format = (v) => (isMoney ? formatTk(v) : compact(v));

  // Thin the x labels so a 90-day series stays readable
  const every = Math.max(1, Math.ceil(data.length / 10));

  const slotUnits = chartWidth / Math.max(data.length, 1);
  const barWidth = Math.min(slotUnits * 0.62, 24);

  return (
    <div className="barchart">
      <svg
        viewBox={`0 0 ${chartWidth} ${svgHeight}`}
        preserveAspectRatio="none"
        className="barchart-svg"
        style={{ height: svgHeight }}
        aria-hidden="true"
        focusable="false"
      >
        {/* Hairline solid gridlines at each tick — recessive */}
        {ticks.map((tick) => {
          const y = plotHeight - (tick / max) * (plotHeight - 4);
          return (
            <line
              key={tick}
              x1={leftPad}
              x2={chartWidth}
              y1={y}
              y2={y}
              className="barchart-grid"
            />
          );
        })}

        {/* Baseline — slightly stronger than the grid */}
        <line
          x1={leftPad}
          x2={chartWidth}
          y1={plotHeight}
          y2={plotHeight}
          className="barchart-baseline"
        />

        {/* Bars — rounded data-end, square at the baseline */}
        {data.map((d, i) => {
          const x = leftPad + (i + 0.5) * slotUnits - barWidth / 2;
          if (d.value > 0) {
            const barHeight = Math.max((d.value / max) * (plotHeight - 4), 2);
            return (
              <rect
                key={d.key}
                x={x}
                y={plotHeight - barHeight}
                width={barWidth}
                height={barHeight}
                rx={Math.min(4, barWidth / 2)}
                ry={Math.min(4, barWidth / 2)}
                className="barchart-bar"
                style={{
                  fill: barColor,
                  ...(hovered === i ? { opacity: 0.8 } : {}),
                }}
              />
            );
          }
          // A quiet 2-unit stub marks "no data" periods
          return (
            <rect
              key={d.key}
              x={x}
              y={plotHeight - 2}
              width={barWidth}
              height={2}
              className="barchart-stub"
            />
          );
        })}
      </svg>

      {/* Y tick labels — HTML overlay so text stays crisp */}
      <div className="barchart-yaxis" style={{ height: `${plotHeight}px` }} aria-hidden="true">
        {ticks.map((tick) => (
          <span
            key={tick}
            className="barchart-tick"
            style={{ bottom: `${(tick / max) * (plotHeight - 4) + 1}px` }}
          >
            {format(tick)}
          </span>
        ))}
      </div>

      {/* X labels — thinned, HTML overlay, one span per bucket */}
      <div className="barchart-xaxis" style={{ marginLeft: `${leftPad / 10}%` }} aria-hidden="true">
        {data.map((d, i) => (
          <span key={d.key} className="barchart-xlabel">
            {i % every === 0 || i === data.length - 1 ? keyLabel(d.key) : ""}
          </span>
        ))}
      </div>

      {/* Hover layer — hit targets span the full column height, so
          every mark is easy to hit (spec: targets >= 24px).
          Leave is handled on the ROW, not per bar: moving between
          adjacent bars fires leave+enter as two separate events,
          which unmounts and remounts the tooltip — visible blink. */}
      <div
        className="barchart-hover"
        style={{ height: `${plotHeight}px` }}
        onMouseLeave={() => setHovered(null)}
      >
        {data.map((d, i) => (
          <button
            key={d.key}
            type="button"
            className="barchart-hit"
            onMouseEnter={() => setHovered(i)}
            onFocus={() => setHovered(i)}
            onBlur={(e) => {
              // Only clear when focus leaves the whole row — tabbing
              // between bars must not blink either
              if (!e.currentTarget.parentElement?.contains(e.relatedTarget)) {
                setHovered(null);
              }
            }}
            aria-label={`${keyLabel(d.key, { full: true })}: ${format(d.value)}`}
          />
        ))}
      </div>

      {/* Tooltip — value leads, label follows */}
      {hovered !== null && data[hovered] && (
        <div
          className="barchart-tip"
          style={{ left: `${((hovered + 0.5) / data.length) * 88 + 6}%` }}
          role="status"
        >
          <strong className="barchart-tip-value">{format(data[hovered].value)}</strong>
          <span className="barchart-tip-label">
            {keyLabel(data[hovered].key, { full: true })}
          </span>
        </div>
      )}

      {/* Screen-reader twin — every value, no hover needed */}
      <table className="barchart-table">
        <caption>Chart data</caption>
        <thead>
          <tr>
            <th scope="col">Period</th>
            <th scope="col">{isMoney ? "Value (Tk)" : "Count"}</th>
          </tr>
        </thead>
        <tbody>
          {data.map((d) => (
            <tr key={d.key}>
              <td>{keyLabel(d.key, { full: true })}</td>
              <td>{d.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- donut ---------- */

/**
 * A donut chart for part-to-whole at a glance (plan mix).
 * `slices: [{ label, value, color }]` — 2px of surface showing between
 * segments, legend with direct counts and percentages, center caption.
 */
export function DonutChart({ slices, caption, size = 150 }) {
  const total = slices.reduce((sum, s) => sum + s.value, 0);

  // conic-gradient stops: each segment's hue, with a thin band of
  // surface between segments (the 2px gap spec for adjacent fills)
  const stops = slices
    .filter((s) => s.value > 0)
    .reduce(
      (acc, s) => {
        const end = acc.cursor + s.value;
        const startPct = (acc.cursor / total) * 100;
        const endPct = (end / total) * 100;
        const halfGap = Math.min(((2 / 360) * 100) / 2, (endPct - startPct) / 2);
        const seg = [
          `${s.color} ${startPct}% ${endPct - halfGap}%`,
          `var(--surface) ${endPct - halfGap}% ${endPct}%`,
        ];
        return { cursor: end, list: [...acc.list, ...seg] };
      },
      { cursor: 0, list: [] }
    )
    .list.join(", ");

  const gradient = stops.length > 0 ? stops : "var(--border) 0% 100%";
  const pct = (value) => (total > 0 ? Math.round((value / total) * 100) : 0);

  return (
    <div className="donut-wrap">
      <div
        className="donut"
        style={{ width: size, height: size, background: `conic-gradient(${gradient})` }}
        role="img"
        aria-label={slices
          .filter((s) => s.value > 0)
          .map((s) => `${s.label}: ${s.value} (${pct(s.value)}%)`)
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
                <span className="badge-dot" style={{ background: s.color }} aria-hidden="true" />
                <span className="donut-legend-label">{s.label}</span>
                <span className="donut-legend-value">
                  {s.value} · {pct(s.value)}%
                </span>
              </li>
            )
        )}
      </ul>
      {/* Screen-reader twin */}
      <table className="barchart-table">
        <caption>Plan mix</caption>
        <tbody>
          {slices.map(
            (s) =>
              s.value > 0 && (
                <tr key={s.label}>
                  <td>{s.label}</td>
                  <td>{s.value}</td>
                  <td>{pct(s.value)}%</td>
                </tr>
              )
          )}
        </tbody>
      </table>
    </div>
  );
}

/* ---------- sparkline ---------- */

/**
 * Compact sparkline for stat tiles — a tiny SVG line chart with a
 * subtle area fill. Decorative context, so aria-hidden.
 */
export function Sparkline({ data, color = "var(--primary)", width = 90, height = 28 }) {
  const { line, area } = useMemo(() => {
    if (!data || data.length < 2) return { line: "", area: "" };
    const max = Math.max(...data, 1);
    const min = Math.min(...data, 0);
    const range = max - min || 1;
    const stepX = width / (data.length - 1);
    const pts = data.map((v, i) => {
      const x = i * stepX;
      const y = height - ((v - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    });
    return {
      line: pts.join(" "),
      area: `0,${height} ${pts.join(" ")} ${width},${height}`,
    };
  }, [data, width, height]);

  if (!data || data.length < 2) return null;

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
