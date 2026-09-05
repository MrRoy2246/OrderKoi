import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, getErrorMessage } from "../api/client";
import Icon from "./icons";
import QtyStepper from "./QtyStepper";
import { formatTk } from "../utils/orderStatus";

const EMPTY_ITEM = { name: "", quantity: 1, price: "" };

/**
 * Modal form for creating a new order.
 * Item rows are dynamic — add/remove as needed, total is live.
 */
export default function OrderFormModal({ onClose, onCreated }) {
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [customerAddress, setCustomerAddress] = useState("");
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState([{ ...EMPTY_ITEM }]);
  const [error, setError] = useState(null);
  const [limitReached, setLimitReached] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const total = useMemo(
    () =>
      items.reduce(
        (sum, item) =>
          sum + (Number(item.quantity) || 0) * (Number(item.price) || 0),
        0
      ),
    [items]
  );

  function updateItem(index, field, value) {
    setItems((prev) =>
      prev.map((item, i) => (i === index ? { ...item, [field]: value } : item))
    );
  }

  function addItem() {
    setItems((prev) => [...prev, { ...EMPTY_ITEM }]);
  }

  function removeItem(index) {
    setItems((prev) => prev.filter((_, i) => i !== index));
  }

  function validate() {
    if (!customerName.trim()) return "Customer name is required.";
    if (customerPhone.trim().length < 6) return "Customer phone looks too short.";
    const email = customerEmail.trim();
    // Light check — the backend re-validates with a proper email parser
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      return "Customer email doesn't look valid (e.g. rahim@gmail.com).";
    }
    if (items.length === 0) return "Add at least one item.";
    for (const item of items) {
      if (!item.name.trim()) return "Every item needs a name.";
      if (!item.quantity || Number(item.quantity) < 1) return "Item quantities must be at least 1.";
      if (item.price === "" || Number(item.price) < 0) return "Item prices must be 0 or more.";
    }
    return null;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const validationError = validate();
    if (validationError) {
      setError(validationError);
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      const order = await api.orders.create({
        customer_name: customerName.trim(),
        customer_phone: customerPhone.trim(),
        customer_email: customerEmail.trim() || null,
        customer_address: customerAddress.trim() || null,
        notes: notes.trim() || null,
        items: items.map((item) => ({
          name: item.name.trim(),
          quantity: Number(item.quantity),
          price: Number(item.price),
        })),
      });
      onCreated(order);
    } catch (err) {
      // 402 = free-plan monthly allowance used up — point at Pro
      if (err?.status === 402) {
        setLimitReached(true);
        setError(null);
      } else {
        setError(getErrorMessage(err, "Could not create the order. Please try again."));
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Create order">
      <div className="modal">
        <div className="modal-header">
          <h2>New order</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            <Icon name="x" size={18} />
          </button>
        </div>

        {error && (
          <div className="alert alert--error" role="alert">
            {error}
          </div>
        )}

        {/* The form body scrolls on short screens; header + buttons stay
            pinned via the flex layout on .modal (see CSS). The submit
            button lives outside the form but is linked via the form attr. */}
        {limitReached ? (
          <div className="modal-form">
            <div className="alert alert--error" role="alert">
              <strong>Monthly free order limit reached</strong>
              <p style={{ margin: "6px 0 0" }}>
                The Free plan includes 15 orders per month. Upgrade to Pro for
                unlimited orders — your existing orders and data stay exactly
                as they are.
              </p>
            </div>
            <div className="modal-actions" style={{ justifyContent: "center" }}>
              <Link to="/dashboard/settings" className="button button--primary" onClick={onClose}>
                <Icon name="sparkles" size={16} />
                Upgrade to Pro
              </Link>
            </div>
          </div>
        ) : (
          <>
        <form id="new-order-form" className="modal-form" onSubmit={handleSubmit} noValidate>
          <div className="form-row">
            <div className="field">
              <label htmlFor="customer_name">Customer name</label>
              <input
                id="customer_name"
                type="text"
                placeholder="e.g. Rahim Uddin"
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="customer_phone">Phone</label>
              <input
                id="customer_phone"
                type="tel"
                placeholder="01XXXXXXXXX"
                value={customerPhone}
                onChange={(e) => setCustomerPhone(e.target.value)}
              />
            </div>
          </div>

          <div className="field">
            <label htmlFor="customer_email">
              Email <span className="field-optional">(optional)</span>
            </label>
            <input
              id="customer_email"
              type="email"
              autoComplete="email"
              placeholder="customer@gmail.com"
              value={customerEmail}
              onChange={(e) => setCustomerEmail(e.target.value)}
            />
            <p className="field-help">Used to notify the customer when the order status changes.</p>
          </div>

          <div className="field">
            <label htmlFor="customer_address">
              Delivery address <span className="field-optional">(optional)</span>
            </label>
            <textarea
              id="customer_address"
              className="textarea"
              rows={2}
              placeholder="House, road, area, city"
              value={customerAddress}
              onChange={(e) => setCustomerAddress(e.target.value)}
            />
          </div>

          <div className="items-editor">
            <div className="items-editor-header">
              <span>Items</span>
              <button type="button" className="button button--outline button--small" onClick={addItem}>
                <Icon name="plus" size={14} />
                Add item
              </button>
            </div>

            {items.map((item, index) => (
              <div key={index} className="item-row">
                <input
                  type="text"
                  className="item-name"
                  placeholder="Item name"
                  aria-label={`Item ${index + 1} name`}
                  value={item.name}
                  onChange={(e) => updateItem(index, "name", e.target.value)}
                />
                <QtyStepper
                  value={item.quantity}
                  onChange={(v) => updateItem(index, "quantity", v)}
                  ariaLabel={`item ${index + 1} quantity`}
                />
                <input
                  type="number"
                  className="item-price"
                  min="0"
                  step="0.01"
                  placeholder="Price"
                  aria-label={`Item ${index + 1} unit price`}
                  value={item.price}
                  onChange={(e) => updateItem(index, "price", e.target.value)}
                />
                <button
                  type="button"
                  className="item-remove"
                  onClick={() => removeItem(index)}
                  disabled={items.length === 1}
                  aria-label={`Remove item ${index + 1}`}
                  title={items.length === 1 ? "Keep at least one item" : "Remove item"}
                >
                  <Icon name="x" size={14} />
                </button>
              </div>
            ))}

            <div className="items-total">
              Total: <strong>{formatTk(total)}</strong>
            </div>
          </div>

          <div className="field">
            <label htmlFor="notes">
              Notes <span className="field-optional">(optional)</span>
            </label>
            <textarea
              id="notes"
              className="textarea"
              rows={2}
              placeholder="e.g. Deliver after 5pm"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
        </form>
          </>
        )}

        {limitReached ? null : (
          <div className="modal-actions">
            <button type="button" className="button button--outline" onClick={onClose} disabled={submitting}>
              Cancel
            </button>
            {/* form="new-order-form" keeps this outside the scrollable body
                while still submitting that form */}
            <button type="submit" form="new-order-form" className="button button--primary" disabled={submitting}>
              <Icon name="check" size={16} />
              {submitting ? "Creating…" : "Create order"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
