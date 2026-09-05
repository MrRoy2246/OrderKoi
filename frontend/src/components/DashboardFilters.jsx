import { useState } from "react";
import Icon from "./icons";
import { businessToday, shiftDays } from "../utils/businessDate";

/**
 * The dashboard's global filter — a single row scoping every analytics
 * section below it. One control: the date range (the only dimension the
 * admin stats API actually filters by — every other filter would be a
 * lie, so it isn't offered).
 *
 * Presets map to real API params: an explicit start/end window.
 * The chip shows the active range and clears back to the default.
 */

const DAY_MS = 24 * 60 * 60 * 1000;

export const RANGE_OPTIONS = [
  { value: "today", label: "Today", days: 1 },
  { value: "yesterday", label: "Yesterday", yesterday: true },
  { value: "7d", label: "Last 7 days", days: 7 },
  { value: "30d", label: "Last 30 days", days: 30 },
  { value: "90d", label: "Last 90 days", days: 90 },
  { value: "this_year", label: "This year", year: "current" },
  { value: "prev_year", label: "Previous year", year: "previous" },
  { value: "custom", label: "Custom range" },
];

/** Resolve a preset into the { start, end } window it stands for
 * (business-timezone dates — matches how the backend buckets days). */
export function rangeToWindow(range, custom) {
  const today = businessToday();
  switch (range) {
    case "today":
      return { start: today, end: today };
    case "yesterday": {
      const y = shiftDays(today, -1);
      return { start: y, end: y };
    }
    case "7d":
      return { start: shiftDays(today, -6), end: today };
    case "30d":
      return { start: shiftDays(today, -29), end: today };
    case "90d":
      return { start: shiftDays(today, -89), end: today };
    case "this_year": {
      const year = Number(today.slice(0, 4));
      // Cap the year at today — future days have no data
      return { start: `${year}-01-01`, end: today };
    }
    case "prev_year": {
      const year = Number(today.slice(0, 4)) - 1;
      return { start: `${year}-01-01`, end: `${year}-12-31` };
    }
    case "custom":
      return custom || null;
    default:
      return null;
  }
}

/** Human label for the active range (used by chips and headers). */
export function rangeLabel(range, custom) {
  if (range === "custom" && custom) {
    return `${formatDay(custom.start)} – ${formatDay(custom.end)}`;
  }
  return RANGE_OPTIONS.find((o) => o.value === range)?.label ?? "";
}

function formatDay(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/**
 * The filter bar: [Date Range ▼] [chips] [Clear].
 * Desktop: one row. Small screens: the select widens; the custom
 * range panel stacks below when active.
 */
export function DashboardFilters({ range, custom, onApply, defaultRange = "30d" }) {
  const [draftStart, setDraftStart] = useState(custom?.start ?? shiftDays(businessToday(), -29));
  const [draftEnd, setDraftEnd] = useState(custom?.end ?? businessToday());
  const [error, setError] = useState(null);

  const isCustom = range === "custom";
  const applied = rangeToWindow(range, custom);
  const label = rangeLabel(range, custom);
  const isDefault = range === defaultRange && !custom;

  function handleSelect(event) {
    const value = event.target.value;
    if (value === "custom") {
      // Open the panel with the current window as the starting draft
      setDraftStart(applied?.start ?? shiftDays(businessToday(), -29));
      setDraftEnd(applied?.end ?? businessToday());
      onApply({ range: "custom", open: true });
      return;
    }
    onApply({ range: value });
  }

  function handleApplyCustom() {
    setError(null);
    if (!draftStart || !draftEnd) {
      setError("Pick both dates.");
      return;
    }
    if (draftStart > draftEnd) {
      setError("The start date must be before the end date.");
      return;
    }
    if ((new Date(draftEnd) - new Date(draftStart)) / DAY_MS + 1 > 366) {
      setError("Custom ranges can span at most one year.");
      return;
    }
    onApply({ range: "custom", custom: { start: draftStart, end: draftEnd } });
  }

  return (
    <section className="filterbar" aria-label="Dashboard filters">
      <div className="filterbar-row">
        <div className="filterbar-field">
          <label className="filterbar-label" htmlFor="dashboard-range">
            Date range
          </label>
          <div className="filterbar-select-wrap">
            <Icon name="calendar" size={15} className="filterbar-select-icon" />
            <select
              id="dashboard-range"
              className="filterbar-select"
              value={isCustom ? "custom" : range}
              onChange={handleSelect}
            >
              {RANGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <Icon name="chevronDown" size={15} className="filterbar-chevron" />
          </div>
        </div>

        {isCustom && (
          <div className="filterbar-custom">
            <div className="filterbar-field">
              <label className="filterbar-label" htmlFor="filter_start">
                From
              </label>
              <input
                id="filter_start"
                type="date"
                className="filterbar-date"
                max={draftEnd}
                value={draftStart}
                onChange={(e) => setDraftStart(e.target.value)}
              />
            </div>
            <span className="custom-range-sep" aria-hidden="true">
              <Icon name="arrowRight" size={14} />
            </span>
            <div className="filterbar-field">
              <label className="filterbar-label" htmlFor="filter_end">
                To
              </label>
              <input
                id="filter_end"
                type="date"
                className="filterbar-date"
                min={draftStart}
                max={businessToday()}
                value={draftEnd}
                onChange={(e) => setDraftEnd(e.target.value)}
              />
            </div>
            <div className="filterbar-field filterbar-field--actions">
              <button
                type="button"
                className="button button--primary button--small"
                onClick={handleApplyCustom}
              >
                Apply
              </button>
              <button
                type="button"
                className="button button--ghost button--small"
                onClick={() => onApply({ range: defaultRange })}
              >
                Cancel
              </button>
            </div>
            {error && <span className="custom-range-error">{error}</span>}
          </div>
        )}

        {!isCustom && (
          <div className="filterbar-chips">
            {!isDefault && (
              <span className="filter-chip" role="status">
                <span className="filter-chip-dot" aria-hidden="true" />
                {label}
                <button
                  type="button"
                  className="filter-chip-x"
                  aria-label={`Clear ${label} filter`}
                  onClick={() => onApply({ range: defaultRange })}
                >
                  <Icon name="x" size={12} />
                </button>
              </span>
            )}
            {isDefault && <span className="filterbar-hint">Last 30 days by default</span>}
          </div>
        )}
      </div>
    </section>
  );
}
