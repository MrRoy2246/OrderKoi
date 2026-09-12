import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";

/**
 * Pending-upgrade-request notifications for the admin.
 *
 * Polls the pending count every 60s while an admin is logged in (a seller
 * submitting a Pro request must surface without a page refresh), and
 * whenever the window regains focus — a back-to-tab moment is exactly
 * when "did anything happen?" matters. Failure is silent: the badge
 * just keeps its last known value (a notification counter must never
 * take a dashboard down).
 *
 * The poll asks for a single pending row and reads the total from the
 * response envelope — never the whole queue.
 */
const POLL_MS = 60 * 1000;

export default function usePendingRequests() {
  const { seller } = useAuth();
  const isAdmin = seller?.role === "admin";
  const [pending, setPending] = useState(0);

  useEffect(() => {
    if (!isAdmin) {
      setPending(0);
      return undefined;
    }

    let cancelled = false;

    async function refresh() {
      try {
        const data = await api.admin.upgradeRequests({ status: "pending", limit: 1 });
        if (!cancelled) {
          setPending(data.total);
        }
      } catch {
        // Keep the last known count — the badge must never error out loud
      }
    }

    refresh();
    const interval = setInterval(refresh, POLL_MS);
    const onFocus = () => refresh();
    window.addEventListener("focus", onFocus);

    return () => {
      cancelled = true;
      clearInterval(interval);
      window.removeEventListener("focus", onFocus);
    };
  }, [isAdmin]);

  return pending;
}
