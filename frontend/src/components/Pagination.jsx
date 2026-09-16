import Icon from "./icons";

/**
 * Previous / Next controls for a paginated list.
 *
 * One implementation behind every list that pages: the seller's orders,
 * the admin's seller list, and the admin's upgrade-request queue. Each
 * of those three used to carry its own copy of this markup, which meant
 * three copies of the same off-by-one arithmetic — "Showing 21–40 of
 * 137" — waiting to disagree about the boundary.
 *
 * Renders nothing when everything already fits on one page, so callers
 * do not have to repeat that test around it.
 *
 * Deliberately absent: numbered pages, a page-size selector, and URL
 * sync. Each list is designed around one page size, and the backend
 * caps how large a page it will serve (MAX_PAGE_SIZE /
 * MAX_ADMIN_PAGE_SIZE) — those are separate features, not a refactor
 * of this one.
 */
export default function Pagination({
  total,
  offset,
  pageSize,
  onChange,
  disabled = false,
}) {
  if (total <= pageSize) return null;

  // `from` is guarded against total === 0 so an empty list can never
  // render "Showing 1–0 of 0".
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + pageSize, total);

  return (
    <div className="pagination">
      <span className="pagination-info">
        Showing {from}–{to} of {total}
      </span>
      <div className="pagination-buttons">
        <button
          type="button"
          className="button button--outline button--small"
          onClick={() => onChange(Math.max(0, offset - pageSize))}
          disabled={offset === 0 || disabled}
        >
          <Icon name="chevronLeft" size={15} />
          Previous
        </button>
        <button
          type="button"
          className="button button--outline button--small"
          onClick={() => onChange(offset + pageSize)}
          disabled={offset + pageSize >= total || disabled}
        >
          Next
          <Icon name="chevronRight" size={15} />
        </button>
      </div>
    </div>
  );
}
