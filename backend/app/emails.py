"""Email templates — one function per email the system sends.

Each returns (subject, body); the routes call send_email() with the
result. Keeping copy here means routes stay thin and tests can assert
on subject/body shape. All bodies are plain text (the project's email
style); HTML templates are a future enhancement.
"""

from app.models import OrderStatus

# Friendly phrasing per order status — what the customer reads
STATUS_ANNOUNCEMENTS = {
    OrderStatus.CONFIRMED.value: "has been confirmed",
    OrderStatus.SHIPPED.value: "is on its way",
    OrderStatus.DELIVERED.value: "has been delivered",
    OrderStatus.CANCELLED.value: "was cancelled",
}


def welcome_verification(store_name: str, verify_url: str, expiry_hours: int) -> tuple[str, str]:
    """Signup: welcome + email verification, one email."""
    subject = f"Welcome to OrderKoi, {store_name}! Verify your email"
    body = (
        f"Welcome to OrderKoi, {store_name}!\n\n"
        "Your store is ready — one last step: verify your email address "
        "so you can log in and start taking orders.\n\n"
        f"Verify your email (link valid for {expiry_hours} hours):\n"
        f"{verify_url}\n\n"
        "You'll get order notifications, password resets and important "
        "updates on this address.\n\n"
        "If you didn't create this account, you can safely ignore this "
        "email.\n\n"
        "— OrderKoi"
    )
    return subject, body


def order_received(
    store_name: str, customer_name: str, order_number: int, tracking_code: str, tracking_url: str
) -> tuple[str, str]:
    """Public form: the customer's confirmation right after submitting."""
    subject = f"Order #{order_number} received — {store_name}"
    body = (
        f"Hi {customer_name},\n\n"
        f"Thanks for your order from {store_name}!\n\n"
        f"Your order number: #{order_number}\n"
        f"Your tracking code: {tracking_code}\n\n"
        "Track your order any time here:\n"
        f"{tracking_url}\n\n"
        "We'll email you whenever the status of your order changes "
        "(confirmed, shipped, delivered).\n\n"
        f"— {store_name} via OrderKoi"
    )
    return subject, body


def status_changed(
    store_name: str,
    customer_name: str,
    order_number: int,
    new_status: str,
    tracking_url: str,
) -> tuple[str, str]:
    """The killer feature: notify the customer when the seller advances
    the order. new_status is an OrderStatus value (e.g. "shipped")."""
    phrase = STATUS_ANNOUNCEMENTS.get(new_status, f"is now {new_status}")
    subject = f"Order #{order_number} update — {phrase}"
    body = (
        f"Hi {customer_name},\n\n"
        f"Your order #{order_number} from {store_name} {phrase}.\n\n"
        "See the full history and latest status here:\n"
        f"{tracking_url}\n\n"
        "If you have any questions, just reply to the seller through the "
        "contact they shared with you.\n\n"
        f"— {store_name} via OrderKoi"
    )
    return subject, body
