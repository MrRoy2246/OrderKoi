"""CSV export — one implementation behind every "Download" button.

Both exports (a seller's own orders, and an admin's export of one
seller over a window) write the same columns from the same rows. The
column list, the encoding, and the Excel-facing date handling therefore
live here once, instead of in two copies that agree only by luck.

Two things here are deliberate and worth not "tidying" back:

The UTF-8 BOM
    `\\ufeff` at the head of the file is what tells Excel the bytes are
    UTF-8. Without it Excel guesses the system's legacy codepage and
    every Bengali name arrives as mojibake.

The date split into two columns
    A single `2026-09-16 17:21` cell is exactly what Excel cannot
    handle. Opening the file through Data -> From Text/CSV lets Excel
    type the column as Date, and a Date column silently renders as
    EMPTY anything its own parser rejects — which a space-separated
    date/time is, under any locale whose short date is not ISO. The
    download looks like it worked and the Date column looks missing.
    So the two facts ship separately: `Date` as pure ISO 8601
    (`YYYY-MM-DD`, the one form Excel's parser accepts in every
    locale), and `Time` as `HH:MM`.
"""

import csv
import io

from fastapi.responses import StreamingResponse

from app.models import Order
from app.timezone import to_business_time

# The header row a spreadsheet shows, in order. Changed only together
# with _row() below — they are the same contract.
COLUMNS = (
    "Order #",
    "Date",
    "Time",
    "Customer name",
    "Phone",
    "Email",
    "Address",
    "Items",
    "Total (Tk)",
    "Status",
    "Source",
    "Tracking code",
    "Notes",
)


def _row(order: Order) -> list[str]:
    """One order as one row, in COLUMNS order.

    Times are business-local (Asia/Dhaka), not UTC: the operator
    reading this spreadsheet is looking at their own day, and a row
    filed under the previous date because the database stores UTC is a
    support ticket waiting to happen.
    """
    placed = to_business_time(order.created_at)
    return [
        order.order_number,
        placed.strftime("%Y-%m-%d"),
        placed.strftime("%H:%M"),
        order.customer_name,
        order.customer_phone,
        order.customer_email or "",
        order.customer_address or "",
        "; ".join(f"{item['name']} x{item['quantity']}" for item in order.items),
        f"{order.total_price:.2f}",
        order.status,
        order.source,
        order.tracking_code,
        order.notes or "",
    ]


def orders_csv_response(orders: list[Order], filename: str) -> StreamingResponse:
    """Render `orders` as a downloadable CSV.

    Built in memory rather than streamed row by row on purpose: the row
    count is already capped by the caller (EXPORT_MAX_ROWS /
    ADMIN_EXPORT_MAX_ROWS), so the whole file is bounded, and a
    spreadsheet that fails halfway through is worse than one that takes
    an extra moment to start.
    """
    buffer = io.StringIO()
    buffer.write("﻿")  # UTF-8 BOM — see the module docstring
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS)
    for order in orders:
        writer.writerow(_row(order))

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
