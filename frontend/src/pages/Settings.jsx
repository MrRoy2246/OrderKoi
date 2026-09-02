import { useRef, useState } from "react";
import { useAuth } from "../auth/AuthContext";
import { api, getErrorMessage } from "../api/client";
import Icon from "../components/icons";
import PlanSection from "../components/PlanSection";
import { parseServerDate } from "../utils/orderStatus";

export default function Settings() {
  const { seller, refresh } = useAuth();

  const [storeName, setStoreName] = useState(seller?.store_name ?? "");
  const [phone, setPhone] = useState(seller?.phone ?? "");
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const [copiedLink, setCopiedLink] = useState(false);
  const copyTimer = useRef(null);

  const formUrl = seller?.store_slug
    ? `${window.location.origin}/order/${seller.store_slug}`
    : null;

  async function handleCopyFormLink() {
    try {
      await navigator.clipboard.writeText(formUrl);
      setCopiedLink(true);
      clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopiedLink(false), 2000);
    } catch {
      window.open(formUrl, "_blank");
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();

    const trimmedName = storeName.trim();
    if (trimmedName.length < 2) {
      setError("Store name must be at least 2 characters.");
      return;
    }

    setError(null);
    setSuccess(null);
    setSubmitting(true);
    try {
      await api.auth.updateMe({
        store_name: trimmedName,
        phone: phone.trim() || null,
      });
      await refresh(); // updates the sidebar + tracking pages immediately
      setSuccess("Store profile updated. Your tracking pages now show the new name.");
    } catch (err) {
      setError(getErrorMessage(err, "Could not save your settings."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="settings-page">
      <header className="page-header">
        <h1>Store settings</h1>
        <p>Your store profile appears on every customer tracking page.</p>
      </header>

      {error && (
        <div className="alert alert--error" role="alert">
          {error}
        </div>
      )}
      {success && (
        <div className="alert alert--success" role="status">
          {success}
        </div>
      )}

      <section className="card">
        <h3>Your public order form</h3>
        <p>
          Share this link on your Facebook page or in post comments. Customers
          fill it in themselves — the order lands straight in your Orders page,
          and they get a tracking link instantly. No more retyping messages.
        </p>
        {formUrl ? (
          <div className="share-link-row">
            <code className="share-link">{formUrl}</code>
            <button
              type="button"
              className="button button--outline button--small"
              onClick={handleCopyFormLink}
            >
              <Icon name={copiedLink ? "check" : "link"} size={14} />
              {copiedLink ? "Copied" : "Copy link"}
            </button>
            <a
              href={formUrl}
              target="_blank"
              rel="noreferrer"
              className="button button--outline button--small"
            >
              <Icon name="externalLink" size={14} />
              Preview
            </a>
          </div>
        ) : (
          <p className="muted-note">Your form link will appear here once your account is fully set up.</p>
        )}
      </section>

      <PlanSection />

      <section className="card">
        <h3>Store profile</h3>
        <form onSubmit={handleSubmit} noValidate>
          <div className="field">
            <label htmlFor="store_name">Store name</label>
            <input
              id="store_name"
              type="text"
              placeholder="e.g. Abin Fashion House"
              value={storeName}
              onChange={(e) => setStoreName(e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="phone">
              Phone <span className="field-optional">(shown to customers is up to you — currently not displayed)</span>
            </label>
            <input
              id="phone"
              type="tel"
              placeholder="01XXXXXXXXX"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </div>

          <button type="submit" className="button button--primary" disabled={submitting}>
            <Icon name="check" size={16} />
            {submitting ? "Saving…" : "Save changes"}
          </button>
        </form>
      </section>

      <section className="card">
        <h3>Account</h3>
        <dl className="detail-list">
          <div>
            <dt>Email (login)</dt>
            <dd>{seller?.email}</dd>
          </div>
          <div>
            <dt>Member since</dt>
            <dd>
              {seller?.created_at
                ? parseServerDate(seller.created_at).toLocaleDateString(undefined, {
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                  })
                : "—"}
            </dd>
          </div>
        </dl>
        <p className="muted-note">
          Need to change your email or password? Contact support — self-service
          for that comes in a future update.
        </p>
      </section>
    </div>
  );
}
