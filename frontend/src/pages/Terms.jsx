import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../components/icons";
import Logo from "../components/Logo";
import { fetchPublicConfig, getSupportEmail } from "../utils/proPricing";

/**
 * Terms of Service — the deal between OrderKoi, its sellers, and their
 * customers: plans and the free allowance, manual bKash payments,
 * acceptable use, and cancellation.
 */

const LAST_UPDATED = "6 September 2026";

export default function Terms() {
  // Support email comes from the live backend config (SUPPORT_EMAIL in
  // the repo-root .env) — falls back to the default until it loads
  const [supportEmail, setSupportEmail] = useState(getSupportEmail());

  useEffect(() => {
    let cancelled = false;
    fetchPublicConfig().then(() => {
      if (!cancelled) setSupportEmail(getSupportEmail());
    });
    return () => {
      cancelled = true;
    };
  }, []);
  const CONTACT_EMAIL = supportEmail;

  return (
    <div className="page-centered">
      <div className="auth-card" style={{ maxWidth: "640px", textAlign: "left" }}>
        <div className="auth-brand">
          <span className="auth-logo">
            <Logo size={38} />
          </span>
          <h1>Terms of Service</h1>
          <p>Last updated: {LAST_UPDATED}</p>
        </div>

        <section>
          <h2>1. The service</h2>
          <p>
            OrderKoi lets online sellers record, manage, and track customer
            orders, and gives customers a public link to follow their order
            status. Using OrderKoi means you accept these terms.
          </p>
        </section>

        <section>
          <h2>2. Accounts</h2>
          <p>
            You need an account to manage orders. Keep your password safe —
            you&apos;re responsible for what happens through your account. One
            store per account; tell us if you need a change.
          </p>
        </section>

        <section>
          <h2>3. Plans and the free allowance</h2>
          <ul>
            <li>
              The <strong>Free plan</strong> includes a one-time allowance of 15
              non-cancelled orders. Cancelled orders return their allowance.
            </li>
            <li>
              <strong>Pro</strong> removes the order limit for the paid period
              (1, 6, or 12 months). When Pro expires, the account returns to
              the Free plan&apos;s rules.
            </li>
          </ul>
        </section>

        <section>
          <h2>4. Payments</h2>
          <p>
            Pro is paid manually via bKash to the number shown at checkout.
            After paying, you submit an upgrade request with the transaction
            reference; we verify the payment and activate Pro. Payments are
            verified by hand, so activation can take a little time. Refunds
            for mistakes are handled case by case — email us.
          </p>
        </section>

        <section>
          <h2>5. Cancellation</h2>
          <p>
            You can cancel Pro any time from Settings. Cancellation takes
            effect immediately — your store returns to the Free plan and your
            existing orders stay intact. Paid-for time doesn&apos;t roll over.
          </p>
        </section>

        <section>
          <h2>6. Acceptable use</h2>
          <ul>
            <li>Use OrderKoi for lawful commerce only — no illegal goods.</li>
            <li>
              Don&apos;t submit other people&apos;s personal data into order
              forms without their knowledge.
            </li>
            <li>
              Don&apos;t attempt to break, overload, or get around the
              service&apos;s limits or security.
            </li>
          </ul>
          <p>
            We can suspend accounts that break these rules, with notice where
            practical.
          </p>
        </section>

        <section>
          <h2>7. Your data and orders</h2>
          <p>
            Your orders belong to you — export them any time as CSV from the
            Orders page. See the{" "}
            <Link to="/privacy">Privacy Policy</Link> for how data is handled
            and deleted.
          </p>
        </section>

        <section>
          <h2>8. Service availability</h2>
          <p>
            We work to keep OrderKoi available, but the service is provided
            &quot;as is&quot; without guarantees of uninterrupted operation.
            Back up important records (CSV export makes this easy).
          </p>
        </section>

        <section>
          <h2>9. Contact</h2>
          <p>
            Anything unclear or unfair in these terms? Email{" "}
            <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> — we&apos;re
            a small team and we answer.
          </p>
        </section>

        <p className="auth-back">
          <Link to="/">
            <Icon name="chevronLeft" size={14} />
            Back to home
          </Link>
        </p>
      </div>
    </div>
  );
}
