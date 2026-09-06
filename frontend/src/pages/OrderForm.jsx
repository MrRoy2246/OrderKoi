import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import Icon from "../components/icons";
import QtyStepper from "../components/QtyStepper";
import { SkeletonCard } from "../components/States";
import { formatTk } from "../utils/orderStatus";

const EMPTY_ITEM = { name: "", quantity: 1, price: "" };

/**
 * The public order form — what customers see when they open the
 * seller's form link (shared on the seller's Facebook page).
 * No login, no account: fill it in, place the order, get a
 * tracking link. The order lands in the seller's dashboard.
 */
export default function OrderForm() {
  const { slug } = useParams();

  const [store, setStore] = useState(null);
  const [loadError, setLoadError] = useState(null);

  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [customerAddress, setCustomerAddress] = useState("");
  const [items, setItems] = useState([{ ...EMPTY_ITEM }]);
  const [notes, setNotes] = useState("");
  // Honeypot — off-screen field bots fill and humans never see.
  // Submitted as `website`; the backend silently drops such orders.
  const [website, setWebsite] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [confirmation, setConfirmation] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.publicForm
      .getStore(slug)
      .then((data) => {
        if (!cancelled) setStore(data);
      })
      .catch((err) => {
        if (!cancelled) setLoadError(getErrorMessage(err, "Could not load this store."));
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  const total = useMemo(
    () =>
      items.reduce(
        (sum, item) => sum + (Number(item.quantity) || 0) * (Number(item.price) || 0),
        0
      ),
    [items]
  );

  function setItem(index, field, value) {
    setItems((current) =>
      current.map((item, i) => (i === index ? { ...item, [field]: value } : item))
    );
  }

  function addItem() {
    setItems((current) => [...current, { ...EMPTY_ITEM }]);
  }

  function removeItem(index) {
    setItems((current) => current.filter((_, i) => i !== index));
  }

  function validate() {
    if (!customerName.trim()) return "Please enter your name.";
    if (!customerPhone.trim()) return "Please enter your phone number.";
    const email = customerEmail.trim();
    // Light check — the backend re-validates with a proper email parser
    if (!email) return "Please enter your email address.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return "Please enter a valid email address (e.g. you@gmail.com).";
    }
    if (!customerAddress.trim()) return "Please enter your delivery address.";

    const filled = items.filter((item) => item.name.trim());
    if (filled.length === 0) return "Please add at least one item to your order.";

    for (const item of filled) {
      const quantity = Number(item.quantity);
      const price = Number(item.price);
      if (!Number.isInteger(quantity) || quantity < 1) {
        return `Quantity for "${item.name}" must be at least 1.`;
      }
      if (Number.isNaN(price) || price < 0) {
        return `Please enter a valid price for "${item.name}".`;
      }
    }
    return null;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError(null);

    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        customer_name: customerName.trim(),
        customer_phone: customerPhone.trim(),
        customer_email: customerEmail.trim(),
        customer_address: customerAddress.trim(),
        items: items
          .filter((item) => item.name.trim())
          .map((item) => ({
            name: item.name.trim(),
            quantity: Number(item.quantity),
            price: Number(item.price) || 0,
          })),
        notes: notes.trim() || null,
        website: website || null,
      };
      const result = await api.publicForm.submitOrder(slug, payload);
      setConfirmation(result);
      window.scrollTo(0, 0);
    } catch (err) {
      // 402 = the store hit its free-plan allowance mid-fill — swap to
      // the paused state (the customer can't fix this; the seller got
      // a clear error on their side)
      if (err?.status === 402) {
        setStore((prev) => (prev ? { ...prev, is_accepting_orders: false } : prev));
        window.scrollTo(0, 0);
      } else {
        setError(getErrorMessage(err, "Could not place your order. Please try again."));
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCopyLink() {
    const url = `${window.location.origin}/track/${confirmation.tracking_code}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.open(url, "_blank");
    }
  }

  function handleShareWhatsApp() {
    const message =
      `I placed order #${confirmation.order_number} at ${confirmation.store_name}! ` +
      `Track it here: ${window.location.origin}/track/${confirmation.tracking_code}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(message)}`, "_blank");
  }

  // ----- Not-found / loading states -----

  if (loadError) {
    return (
      <div className="page-centered">
        <div className="orderform-card">
          <div className="orderform-header">
            <span className="orderform-logo">
              <Icon name="search" size={26} />
            </span>
            <h1>Store not found</h1>
            <p>{loadError}</p>
          </div>
          <p className="orderform-power">
            Powered by <strong>OrderKoi</strong> — order tracking for online stores
          </p>
        </div>
      </div>
    );
  }

  if (!store) {
    return (
      <div className="page-centered">
        <div className="orderform-card">
          <div className="orderform-loading" aria-hidden="true">
            <SkeletonCard lines={4} />
          </div>
        </div>
      </div>
    );
  }

  // ----- Store paused (free-plan limit reached) — show a proper
  // notice instead of letting the customer fill the whole form in
  // only to be rejected at submit -----

  if (!store.is_accepting_orders) {
    return (
      <div className="page-centered">
        <div className="orderform-card">
          <div className="orderform-header">
            <span className="orderform-logo orderform-logo--paused" aria-hidden="true">
              <Icon name="clock" size={26} />
            </span>
            <h1>{store.store_name}</h1>
            <p>
              This store is <strong>temporarily paused</strong> for new orders and
              will be back soon.
            </p>
          </div>

          <div className="orderform-paused-box" role="status">
            <p>
              The seller isn&apos;t taking new orders through this link right now. If
              you&apos;ve already placed an order, it&apos;s unaffected — track it
              with the link the seller shared with you.
            </p>
          </div>

          <p className="orderform-power">
            Powered by <strong>OrderKoi</strong> — order tracking for online stores
          </p>
        </div>
      </div>
    );
  }

  // ----- Success screen -----

  if (confirmation) {
    const trackUrl = `${window.location.origin}/track/${confirmation.tracking_code}`;
    return (
      <div className="page-centered">
        <div className="orderform-card">
          <div className="orderform-header">
            <span className="orderform-success-icon" aria-hidden="true">
              <Icon name="check" size={26} />
            </span>
            <h1>Order placed!</h1>
            <p>
              Order <strong>#{confirmation.order_number}</strong> at{" "}
              <strong>{confirmation.store_name}</strong>. We&apos;ll contact you to
              confirm.
            </p>
          </div>

          <div className="orderform-track-box">
            <p className="orderform-track-label">Your tracking code</p>
            <code className="orderform-track-code">{confirmation.tracking_code}</code>
            <a href={trackUrl} className="orderform-track-link">
              Track your order anytime
              <Icon name="arrowRight" size={14} />
            </a>
          </div>

          <p className="orderform-hint">
            Save this link — check it anytime to see your order status, no login needed.
          </p>

          <div className="orderform-actions">
            <button
              type="button"
              className="button button--outline"
              onClick={handleCopyLink}
            >
              <Icon name={copied ? "check" : "link"} size={15} />
              {copied ? "Copied" : "Copy tracking link"}
            </button>
            <button
              type="button"
              className="button button--outline"
              onClick={handleShareWhatsApp}
            >
              <Icon name="send" size={15} />
              Share on WhatsApp
            </button>
            <Link to={`/track/${confirmation.tracking_code}`} className="button button--primary">
              Track now
            </Link>
          </div>

          <p className="orderform-power">
            Powered by <strong>OrderKoi</strong> — order tracking for online stores
          </p>
        </div>
      </div>
    );
  }

  // ----- The form -----

  return (
    <div className="page-centered">
      <div className="orderform-card">
        <div className="orderform-header">
          <span className="orderform-logo">
            <Icon name="store" size={26} />
          </span>
          <h1>{store.store_name}</h1>
          <p>
            Fill this form to place your order. We&apos;ll confirm on phone or
            Messenger.
          </p>
        </div>

        {error && (
          <div className="alert alert--error" role="alert">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>
          {/* Honeypot — visually and programmatically out of reach for
              humans (off-screen, no tab stop, hidden from AT); bots
              that auto-fill forms type into it and get dropped. */}
          <div aria-hidden="true" style={{ position: "absolute", left: "-9999px", top: 0 }}>
            <label htmlFor="website">Leave this field empty</label>
            <input
              id="website"
              type="text"
              name="website"
              tabIndex={-1}
              autoComplete="off"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="customer_name">Your name *</label>
            <input
              id="customer_name"
              type="text"
              autoComplete="name"
              placeholder="e.g. Rahim Ahmed"
              value={customerName}
              onChange={(e) => setCustomerName(e.target.value)}
            />
          </div>

          <div className="field">
            <label htmlFor="customer_phone">Phone number *</label>
            <input
              id="customer_phone"
              type="tel"
              autoComplete="tel"
              inputMode="tel"
              placeholder="01XXXXXXXXX"
              value={customerPhone}
              onChange={(e) => setCustomerPhone(e.target.value)}
            />
            <p className="field-help">We call this number to confirm your order.</p>
          </div>

          <div className="field">
            <label htmlFor="customer_email">Email address *</label>
            <input
              id="customer_email"
              type="email"
              autoComplete="email"
              inputMode="email"
              placeholder="you@gmail.com"
              value={customerEmail}
              onChange={(e) => setCustomerEmail(e.target.value)}
            />
            <p className="field-help">
              We email you when your order status changes (confirmed,
              shipped, delivered).
            </p>
          </div>

          <div className="field">
            <label htmlFor="customer_address">Delivery address *</label>
            <textarea
              id="customer_address"
              rows={2}
              placeholder="House, road, area, city"
              value={customerAddress}
              onChange={(e) => setCustomerAddress(e.target.value)}
            />
          </div>

          <fieldset className="orderform-items">
            <legend>Your order *</legend>

            {items.map((item, index) => (
              <div className="orderform-item-row" key={index}>
                <input
                  type="text"
                  className="orderform-item-name"
                  placeholder="Item name"
                  aria-label={`Item ${index + 1} name`}
                  value={item.name}
                  onChange={(e) => setItem(index, "name", e.target.value)}
                />
                <QtyStepper
                  value={item.quantity}
                  onChange={(v) => setItem(index, "quantity", v)}
                  ariaLabel={`item ${index + 1} quantity`}
                />
                <input
                  type="number"
                  className="orderform-item-price"
                  placeholder="Price"
                  aria-label={`Item ${index + 1} price`}
                  min="0"
                  step="any"
                  inputMode="decimal"
                  value={item.price}
                  onChange={(e) => setItem(index, "price", e.target.value)}
                />
                <button
                  type="button"
                  className="orderform-item-remove"
                  onClick={() => removeItem(index)}
                  aria-label={`Remove item ${index + 1}`}
                  title={items.length === 1 ? "Keep at least one item" : "Remove this item"}
                  disabled={items.length === 1}
                >
                  <Icon name="x" size={14} />
                </button>
              </div>
            ))}

            <button
              type="button"
              className="button button--outline button--small orderform-add-item"
              onClick={addItem}
            >
              <Icon name="plus" size={14} />
              Add another item
            </button>

            <div className="orderform-total">
              <span>Total</span>
              <strong>{formatTk(total)}</strong>
            </div>
          </fieldset>

          <div className="field">
            <label htmlFor="notes">
              Notes <span className="field-optional">(optional)</span>
            </label>
            <textarea
              id="notes"
              rows={2}
              placeholder="e.g. size, color, delivery time…"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          <button
            type="submit"
            className="button button--primary button--full"
            disabled={submitting}
          >
            <Icon name="packageCheck" size={16} />
            {submitting ? "Placing your order…" : "Place order"}
          </button>
        </form>

        <p className="orderform-power">
          Powered by <strong>OrderKoi</strong> — order tracking for online stores
        </p>
      </div>
    </div>
  );
}
