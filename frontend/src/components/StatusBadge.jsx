import { STATUS_META } from "../utils/orderStatus";

/** Colored dot + soft pill showing an order's status. */
export default function StatusBadge({ status }) {
  const meta = STATUS_META[status] ?? { label: status, className: "" };
  return (
    <span className={`badge ${meta.className}`}>
      <span className="badge-dot" aria-hidden="true" />
      {meta.label}
    </span>
  );
}
