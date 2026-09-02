/**
 * Quantity stepper — minus/plus buttons around a plain number input.
 * Clamps between 1 and max (default 999); typing a value still works.
 */
export default function QtyStepper({ value, onChange, ariaLabel, max = 999 }) {
  const current = Number(value) || 0;

  function step(delta) {
    onChange(String(Math.min(max, Math.max(1, current + delta))));
  }

  return (
    <div className="qty-stepper">
      <button
        type="button"
        className="qty-btn"
        onClick={() => step(-1)}
        aria-label={`Decrease ${ariaLabel}`}
        disabled={current <= 1}
      >
        −
      </button>
      <input
        type="number"
        className="qty-input"
        aria-label={ariaLabel}
        min="1"
        max={max}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <button
        type="button"
        className="qty-btn"
        onClick={() => step(1)}
        aria-label={`Increase ${ariaLabel}`}
        disabled={current >= max}
      >
        +
      </button>
    </div>
  );
}
