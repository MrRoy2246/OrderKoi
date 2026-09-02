"""Security probe script — read-mostly, non-destructive.

Runs against the live dev server (localhost:8000) and reports what an
attacker would learn. Creates one throwaway account to test with.
"""

import json
import urllib.error
import urllib.request

BASE = "http://localhost:8000"


def call(method, path, body=None, token=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


print("=== 1. AUTH EDGE CASES ===")
s, _ = call("POST", "/auth/login", {"email": "nobody@x.com", "password": "wrong"})
print(f"unknown email + wrong pw        -> {s} (want 401)")
s, r = call("POST", "/auth/login", {"email": "", "password": ""})
print(f"empty credentials               -> {s}")
s, r = call("POST", "/auth/login", {"email": "not-an-email", "password": "x"})
print(f"invalid email format            -> {s}")
s, r = call("POST", "/auth/login", {"email": "a@b.co", "password": "x" * 5000})
print(f"5000-char password              -> {s}")

print()
print("=== 2. JWT TAMPERING ===")
s, _ = call("GET", "/auth/me")
print(f"no token                        -> {s} (want 401)")
s, _ = call("GET", "/auth/me", token="garbage.token.here")
print(f"garbage token                   -> {s} (want 401)")
# forge: valid format, wrong signature, role claim injected
import base64
import time

def b64(d):
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

forged = (
    b64({"alg": "HS256", "typ": "JWT"}) + "."
    + b64({"sub": "1", "role": "admin", "exp": int(time.time()) + 9999}) + "."
    + "invalidsignature"
)
s, r = call("GET", "/auth/me", token=forged)
print(f"forged token (role=admin claim) -> {s} (want 401)")
# alg=none attempt
none_tok = b64({"alg": "none", "typ": "JWT"}) + "." + b64({"sub": "1", "exp": int(time.time()) + 9999}) + "."
s, r = call("GET", "/auth/me", token=none_tok)
print(f"alg=none token                  -> {s} (want 401)")

print()
print("=== 3. MASS ASSIGNMENT ON SIGNUP ===")
s, r = call("POST", "/auth/signup", {
    "email": "probe-account@audit-test.com", "password": "probepass123",
    "store_name": "Probe Store", "role": "admin", "plan": "pro",
})
if s == 409:
    print("signup (already exists from earlier run) -> 409")
else:
    print(f"signup with role/plan injected  -> {s}, role={r.get('role')}, plan={r.get('plan')} (want seller/free)")
s, r = call("POST", "/auth/login", {"email": "probe-account@audit-test.com", "password": "probepass123"})
PROBE_TOKEN = r["access_token"]
s, r = call("GET", "/auth/me", token=PROBE_TOKEN)
print(f"probe account identity          -> role={r['role']}, plan={r['plan']}, slug={r['store_slug']}")

print()
print("=== 4. IDOR / CROSS-TENANT ACCESS ===")
# victim: the other known seller
s, r = call("POST", "/auth/login", {"email": "other@test.com", "password": "newotherpass77"})
VICTIM_TOKEN = r["access_token"]
s, r = call("GET", "/orders?limit=1", token=VICTIM_TOKEN)
victim_order = r["orders"][0] if r.get("orders") else None
if victim_order:
    vid, vnum = victim_order["id"], victim_order["order_number"]
    s, _ = call("GET", f"/orders/{vid}", token=PROBE_TOKEN)
    print(f"GET  victim order #{vnum} (id={vid})     -> {s} (want 404)")
    s, _ = call("PATCH", f"/orders/{vid}", {"notes": "hax"}, token=PROBE_TOKEN)
    print(f"PATCH victim order              -> {s} (want 404)")
    s, _ = call("DELETE", f"/orders/{vid}", token=PROBE_TOKEN)
    print(f"DELETE victim order             -> {s} (want 404)")
    s, _ = call("PATCH", f"/orders/{vid}/status", {"status": "cancelled"}, token=PROBE_TOKEN)
    print(f"status-change victim order      -> {s} (want 404)")
    s, r = call("GET", "/orders", token=PROBE_TOKEN)
    print(f"probe's own order list          -> {s}, total={r.get('total')} (want 0 — isolation)")
else:
    print("victim has no orders — skipped")

print()
print("=== 5. PRIVILEGE ESCALATION ===")
s, _ = call("GET", "/admin/sellers", token=PROBE_TOKEN)
print(f"seller -> GET /admin/sellers    -> {s} (want 403)")
s, _ = call("GET", "/admin/subscription-events", token=PROBE_TOKEN)
print(f"seller -> subscription-events   -> {s} (want 403)")
s, _ = call("PATCH", "/admin/sellers/2/plan", {"plan": "pro"}, token=PROBE_TOKEN)
print(f"seller -> set own plan pro      -> {s} (want 403)")
s, _ = call("POST", "/auth/cancel-subscription", token=PROBE_TOKEN)
print(f"seller -> cancel subscription   -> {s} (want 409, not pro)")

print()
print("=== 6. ORDER VALIDATION / INJECTION ===")
s, r = call("POST", "/orders", {
    "customer_name": "x", "customer_phone": "123", "items": [],
}, token=PROBE_TOKEN)
print(f"empty items list                -> {s}")
s, r = call("POST", "/orders", {
    "customer_name": "x", "customer_phone": "01700",
    "items": [{"name": "n", "quantity": -5, "price": -100}],
}, token=PROBE_TOKEN)
print(f"negative qty+price             -> {s}")
s, r = call("POST", "/orders", {
    "customer_name": "x", "customer_phone": "01700",
    "items": [{"name": "n", "quantity": 1000, "price": 99999999999}],
}, token=PROBE_TOKEN)
print(f"qty=1000, price=1e11           -> {s}")
s, r = call("POST", "/orders", {
    "customer_name": "x" * 500, "customer_phone": "01700",
    "items": [{"name": "n", "quantity": 1, "price": 10}],
}, token=PROBE_TOKEN)
print(f"500-char customer name         -> {s}")
s, r = call("GET", "/orders?q=%27%20OR%201%3D1%20--", token=PROBE_TOKEN)
print(f"SQLi in search q               -> {s}, total={r.get('total')} (want 0)")
s, r = call("POST", "/orders", {
    "customer_name": "<script>alert('xss')</script>", "customer_phone": "01700000000",
    "items": [{"name": "<img src=x onerror=alert(1)>", "quantity": 1, "price": 10}],
}, token=PROBE_TOKEN)
print(f"XSS payload stored             -> {s} (stored; rendering safety checked separately)")
if s == 201:
    XSS_CODE = r["tracking_code"]
    s, r = call("GET", f"/track/{XSS_CODE}")
    leaked = [k for k in r.keys()]
    print(f"tracking response fields       -> {leaked}")

print()
print("=== 7. TRACKING ENUMERATION INFO ===")
s, r = call("GET", "/track/ZZZZZZZZ")
print(f"random tracking code           -> {s}")
s, r = call("GET", "/track/")
print(f"empty tracking code            -> {s}")
s, r = call("GET", "/track/" + "A" * 500)
print(f"500-char tracking code         -> {s}")
s, r = call("GET", "/orders/stats/summary?range=custom&start=2026-01-01&end=2026-01-02", token=PROBE_TOKEN)
print(f"custom stats as seller         -> {s} range={r.get('range')}")

print()
print("=== 8. PUBLIC FORM SLUG PROBES ===")
s, r = call("GET", "/public/stores/orderkoi-platform")
print(f"admin's slug via public form   -> {s} (want 404 — admins have no store)")
s, r = call("POST", "/public/stores/orderkoi-platform/orders", {
    "customer_name": "a", "customer_phone": "01700", "customer_address": "b",
    "items": [{"name": "n", "quantity": 1, "price": 1}],
})
print(f"order via admin slug           -> {s} (want 404)")
s, r = call("GET", "/public/stores/%27%20OR%20%271%27%3D%271")
print(f"SQLi in slug                   -> {s}")

print()
print("=== 9. RATE LIMITS (destructive to limits only) ===")
codes = []
for i in range(25):
    s, r = call("GET", "/public/stores/probe-store")
    if s == 429:
        print(f"public form rate limit kicked in at request #{i+1} -> 429  Retry-After present")
        break
else:
    print("NO rate limit hit after 25 public requests!")
