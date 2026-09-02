import Icon from "./icons";

/**
 * Shared loading / empty / error states — every page uses these so
 * the app never shows a blank screen, a raw spinner-only block, or a
 * cryptic error string.
 */

export function Skeleton({ className = "", style }) {
  return <span aria-hidden="true" className={`skeleton ${className}`.trim()} style={style} />;
}

/** Card-shaped skeleton block (dashboard tiles, detail sections). */
export function SkeletonCard({ lines = 2 }) {
  return (
    <div className="skeleton-card" aria-hidden="true">
      <Skeleton className="skeleton-line skeleton-line--title" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className="skeleton-line" />
      ))}
    </div>
  );
}

/** Row-shaped skeletons for tables and lists. */
export function SkeletonRows({ rows = 5 }) {
  return (
    <div className="skeleton-rows" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton-row">
          <Skeleton className="skeleton-line skeleton-line--sm" style={{ width: "34%" }} />
          <Skeleton className="skeleton-line skeleton-line--sm" style={{ width: "22%" }} />
          <Skeleton className="skeleton-line skeleton-line--sm" style={{ width: "16%" }} />
        </div>
      ))}
    </div>
  );
}

/**
 * A friendly empty state that points to the next action.
 * Usage: <EmptyState icon="package" title="No orders yet" action={<button…/>}>
 */
export function EmptyState({ icon = "inbox", title, children, action }) {
  return (
    <div className="empty-state">
      <span className="empty-icon" aria-hidden="true">
        <Icon name={icon} size={26} />
      </span>
      <h3>{title}</h3>
      {/* Callers pass <p> children — a <p> wrapper here would nest them */}
      {children && <div className="empty-text">{children}</div>}
      {action && <div className="empty-action">{action}</div>}
    </div>
  );
}

/** Human-friendly error block with a retry button. */
export function ErrorState({ message, onRetry }) {
  return (
    <div className="empty-state empty-state--error" role="alert">
      <span className="empty-icon empty-icon--error" aria-hidden="true">
        <Icon name="alertCircle" size={26} />
      </span>
      <h3>Something went wrong</h3>
      <p>{message}</p>
      {onRetry && (
        <div className="empty-action">
          <button type="button" className="button button--outline" onClick={onRetry}>
            <Icon name="refresh" size={16} />
            Try again
          </button>
        </div>
      )}
    </div>
  );
}

/** Screen-reader-only live region so loading/errors announce politely. */
export function LiveMessage({ children }) {
  return (
    <p role="status" aria-live="polite" className="visually-hidden">
      {children}
    </p>
  );
}
