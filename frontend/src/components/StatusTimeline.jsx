import Icon from "./icons";
import { STATUS_META, formatDateTime } from "../utils/orderStatus";

/** The four steps of the happy-path order flow. */
const FLOW = ["placed", "confirmed", "shipped", "delivered"];

/**
 * The one shared status timeline — the seller's OrderDetail page and
 * the customer's public tracking page render this same component, so
 * both experiences tell one consistent story.
 *
 * Steps already passed show a check and their timestamp; the current
 * step pulses softly; upcoming steps are quiet. Cancelled orders show
 * however far they got, then a red terminal node.
 */
export default function StatusTimeline({ status, history = [] }) {
  const times = {};
  history.forEach((event) => {
    times[event.status] = event.changed_at;
  });

  let nodes;
  if (status === "cancelled") {
    // However far the order got (steps with timestamps), then the end.
    nodes = FLOW.map((step) => ({ status: step, done: Boolean(times[step]) }));
    nodes.push({ status: "cancelled", done: true, terminal: true });
  } else {
    const currentIndex = FLOW.indexOf(status);
    nodes = FLOW.map((step, index) => ({
      status: step,
      done: index <= currentIndex,
      current: index === currentIndex,
    }));
  }

  return (
    <ol className="timeline">
      {nodes.map((node) => {
        const meta = STATUS_META[node.status] ?? { label: node.status };
        const classes = [
          "timeline-item",
          node.done ? "timeline-item--done" : "",
          node.current ? "timeline-item--current" : "",
          node.terminal ? "timeline-item--terminal" : "",
        ]
          .filter(Boolean)
          .join(" ");
        return (
          <li key={node.status} className={classes}>
            <span className="timeline-marker" aria-hidden="true">
              {node.terminal ? (
                <Icon name="x" size={11} />
              ) : node.done && !node.current ? (
                <Icon name="check" size={11} />
              ) : null}
            </span>
            <div className="timeline-body">
              <span className="timeline-label">{meta.label}</span>
              {node.current && meta.description && (
                <span className="timeline-desc"> — {meta.description}</span>
              )}
              {times[node.status] && (
                <time className="timeline-time">{formatDateTime(times[node.status])}</time>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
