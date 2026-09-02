"""Benchmark for fix #6: SQL aggregates vs the old load-everything loop."""

import json
import os
import tempfile
import time
import urllib.request
from datetime import datetime

from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker

from app.models import Base, Order, Seller
from app.security import hash_password

# --- live check against the running dev server ---
BASE = "http://localhost:8000"
req = urllib.request.Request(BASE + "/auth/login", method="POST")
req.add_header("Content-Type", "application/json")
with urllib.request.urlopen(
    req, json.dumps({"email": "other@test.com", "password": "newotherpass77"}).encode()
) as r:
    token = json.loads(r.read())["access_token"]
req = urllib.request.Request(BASE + "/orders/stats/summary?range=30d")
req.add_header("Authorization", f"Bearer {token}")
with urllib.request.urlopen(req) as r:
    body = json.loads(r.read())
print(
    f"live /stats/summary?range=30d -> {r.status} | total: {body['total_orders']}"
    f" | pending: {body['pending_orders']} | revenue: {body['revenue']}"
    f" | daily bars: {len(body['daily'])}"
)

# --- scale benchmark: 50k synthetic orders in a temp DB ---
dbfile = tempfile.mktemp(suffix=".db")
engine = create_engine(f"sqlite:///{dbfile}", connect_args={"check_same_thread": False})
Base.metadata.create_all(engine)
S = sessionmaker(bind=engine)
db = S()
db.add(
    Seller(
        email="bench@x.co",
        store_name="B",
        store_slug="bench",
        hashed_password=hash_password("x" * 12),
    )
)
db.commit()
sid = db.query(Seller).first().id
now = datetime.utcnow().isoformat(sep=" ")

insert_sql = (
    "INSERT INTO orders (seller_id, order_number, tracking_code, customer_name, "
    "customer_phone, items, total_price, status, source, status_history, created_at, updated_at) "
    "SELECT :sid, n, 'B' || printf('%07d', n), 'c', '017', '[]', 100, "
    "CASE WHEN n % 5 = 0 THEN 'delivered' WHEN n % 7 = 0 THEN 'cancelled' "
    "ELSE 'placed' END, 'form', '[]', :now, :now "
    "FROM (SELECT rowid + 1 AS n FROM orders LIMIT 0) "
)
# simpler generator: use a recursive CTE
insert_sql = (
    "INSERT INTO orders (seller_id, order_number, tracking_code, customer_name, "
    "customer_phone, items, total_price, status, source, status_history, created_at, updated_at) "
    "WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 50000) "
    "SELECT :sid, n, 'B' || printf('%07d', n), 'c', '017', '[]', 100, "
    "CASE WHEN n % 5 = 0 THEN 'delivered' WHEN n % 7 = 0 THEN 'cancelled' "
    "ELSE 'placed' END, 'form', '[]', :now, :now FROM seq"
)
db.execute(text(insert_sql), {"sid": sid, "now": now})
db.commit()
count = db.query(func.count(Order.id)).filter(Order.seller_id == sid).scalar()
print(f"seeded {count} orders")

# NEW approach: SQL aggregates (what the endpoint now does)
t0 = time.perf_counter()
rows = (
    db.query(
        Order.status,
        func.count(Order.id),
        func.coalesce(func.sum(Order.total_price), 0.0),
    )
    .filter(Order.seller_id == sid)
    .group_by(Order.status)
    .all()
)
t_sql = time.perf_counter() - t0

# OLD approach: load everything into Python (what the endpoint used to do)
t0 = time.perf_counter()
orders = db.query(Order).filter(Order.seller_id == sid).all()
_ = sum(o.total_price or 0 for o in orders if o.status != "cancelled")
t_python = time.perf_counter() - t0

print(
    f"50k orders: SQL aggregate {t_sql * 1000:.0f}ms vs old load-all "
    f"{t_python * 1000:.0f}ms ({t_python / t_sql:.0f}x slower, {len(orders)} rows loaded)"
)
db.close()
engine.dispose()
os.remove(dbfile)
