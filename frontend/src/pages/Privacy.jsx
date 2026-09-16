import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../components/icons";
import Logo from "../components/Logo";
import { fetchPublicConfig, getSupportEmail } from "../utils/proPricing";

/**
 * Privacy Policy — what data OrderKoi collects (seller accounts and
 * customer orders), why, how long, and how to get it deleted.
 * Kept in plain language; the store data it describes is exactly what
 * the backend stores (see app/models.py).
 */

const LAST_UPDATED = "6 September 2026";

export default function Privacy() {
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
          <h1>Privacy Policy</h1>
          <p>Last updated: {LAST_UPDATED}</p>
        </div>

        <section>
          <h2>Who we are</h2>
          <p>
            OrderKoi (&quot;we&quot;, &quot;us&quot;) is an order-tracking service for online
            sellers in Bangladesh. This policy explains what data we collect and
            what we do with it. Questions? Email us at{" "}
            <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
          </p>
        </section>

        <section>
          <h2>What we collect</h2>
          <p>
            <strong>Seller accounts:</strong> your store name, email address,
            phone number (optional), and a bcrypt-hashed password (we never see
            or store your actual password).
          </p>
          <p>
            <strong>Customer orders:</strong> when a customer orders through a
            seller&apos;s OrderKoi form, we store the name, phone number, email
            address, delivery address, ordered items, and any notes they
            submitted — so the seller can fulfil and track that order.
          </p>
          <p>
            <strong>Subscription records:</strong> if you upgrade to Pro, we
            store the duration paid for and the bKash transaction reference you
            submit, so the payment can be verified. We never see or store your
            bKash PIN or full payment credentials.
          </p>
          <p>
            We do not run advertising trackers, and we do not sell your data to
            anyone.
          </p>
        </section>

        <section>
          <h2>Why we collect it</h2>
          <ul>
            <li>To create and secure your account (email verification, password reset).</li>
            <li>To let sellers manage orders and let customers track theirs.</li>
            <li>To send transactional emails: order confirmations and status updates.</li>
            <li>To verify Pro payments and keep a subscription history.</li>
          </ul>
        </section>

        <section>
          <h2>Who can see it</h2>
          <p>
            Order data is visible only to the seller whose store received it,
            and to OrderKoi platform administration. Customers can see their own
            order status via the tracking link the seller shares with them —
            that link shows status only, never the delivery address or phone
            number.
          </p>
        </section>

        <section>
          <h2>How long we keep it</h2>
          <p>
            Account and order data is kept while your account is active, so
            your order history stays useful. If you want your account and its
            data deleted, email us at{" "}
            <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> and we will
            remove it.
          </p>
        </section>

        <section>
          <h2>Security</h2>
          <p>
            Passwords are hashed (never stored in readable form), reset and
            verification links are single-use and expire, and access to orders
            is restricted to the owning seller. No system is perfect — if you
            ever spot a security problem, please tell us and we&apos;ll act on
            it quickly.
          </p>
        </section>

        <section>
          <h2>Changes to this policy</h2>
          <p>
            If we change this policy we&apos;ll update the date at the top of
            this page.
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
