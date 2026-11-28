"""The demo sites, served by one local app (agent-verdict demo-sites, http://127.0.0.1:5100).

    /shop    Lakeshore Supply: search, product pages, cart, coupon, two-step checkout, orders
    /bistro  Harbor Bistro: menu, hours, reservations, manage a booking
    /desk    Northpoint Help Desk: tickets, replies, status / priority / assignee, knowledge base

Plain server-rendered HTML with ordinary links and forms, like most real sites. State lives in memory:
POST /_reset puts every site back to its starting data; GET /_state returns all of it as JSON for the
task checkers. Each site has realistic traps (a review step before an order is placed, a time slot that
doesn't exist, an "Assign to me" button) so agents can genuinely fail.
"""

from __future__ import annotations

import copy
import html
from urllib.parse import quote, urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

# ============================================================== starting data

SEED = {
    "shop": {
        "products": {
            "aa-4": {"name": "Duracell AA batteries, 4-pack", "price": 6.49, "stock": 40, "cat": "Batteries"},
            "aaa-4": {"name": "Duracell AAA batteries, 4-pack", "price": 5.99, "stock": 35, "cat": "Batteries"},
            "usbc-anker-3m": {"name": "Anker USB-C cable, 3 m", "price": 4.99, "stock": 12, "cat": "Cables"},
            "usbc-basics-1m": {"name": "Basics USB-C cable, 1 m", "price": 5.49, "stock": 20, "cat": "Cables"},
            "usbc-ugreen-05m": {"name": "Ugreen USB-C cable, 0.5 m", "price": 5.99, "stock": 18, "cat": "Cables"},
            "usbc-belkin-2m": {"name": "Belkin USB-C cable, 2 m", "price": 7.99, "stock": 9, "cat": "Cables"},
            "usbc-anker-18m": {"name": "Anker USB-C cable, 1.8 m", "price": 8.49, "stock": 14, "cat": "Cables"},
            "lamp-arc": {"name": "Arc desk lamp", "price": 24.00, "stock": 0, "cat": "Home office"},
            "notebook-a5": {"name": "Dot-grid notebook, A5", "price": 3.25, "stock": 60, "cat": "Home office"},
            "mug-blue": {"name": "Lake mug, blue", "price": 9.50, "stock": 25, "cat": "Kitchen"},
            "mug-red": {"name": "Lake mug, red", "price": 9.50, "stock": 25, "cat": "Kitchen"},
            "mug-green": {"name": "Lake mug, green", "price": 9.50, "stock": 1, "cat": "Kitchen"},
            "bottle": {"name": "Steel water bottle, 750 ml", "price": 14.00, "stock": 30, "cat": "Kitchen"},
            "headphones": {"name": "Harbor wireless headphones", "price": 39.00, "stock": 7, "cat": "Audio"},
            "earbuds": {"name": "Harbor earbuds", "price": 24.00, "stock": 0, "cat": "Audio"},
        },
        "cart": {},             # sku -> qty
        "coupon": None,
        "address": None,        # chosen at checkout
        "orders": [
            {"id": 1042, "items": {"bottle": 1, "mug-blue": 1, "notebook-a5": 2}, "coupon": None,
             "address": "14 Elm St, Buffalo NY 14202", "total": 30.00, "date": "Nov 18, 2026"},
        ],
        "saved_address": "14 Elm St, Buffalo NY 14202",
        "next_order": 1043,
    },
    "bistro": {
        "slots": {  # date -> times offered (7:30 pm is missing on Friday on purpose)
            "Thu, Dec 3": ["6:00 pm", "6:30 pm", "7:00 pm", "7:30 pm", "8:00 pm", "8:30 pm"],
            "Fri, Dec 4": ["6:00 pm", "6:30 pm", "7:00 pm", "8:30 pm"],
            "Sat, Dec 5": ["5:30 pm", "6:00 pm", "7:00 pm", "8:00 pm", "8:30 pm"],
            "Sun, Dec 6": ["5:00 pm", "5:30 pm", "6:00 pm", "7:00 pm"],
        },
        "max_party": 8,
        "bookings": {
            "HB-2291": {"date": "Sat, Dec 5", "time": "7:00 pm", "party": 4, "name": "Rivera", "phone": "", "status": "confirmed"},
            "HB-3307": {"date": "Fri, Dec 4", "time": "6:30 pm", "party": 4, "name": "Nguyen", "phone": "", "status": "confirmed"},
            "HB-4410": {"date": "Sun, Dec 6", "time": "5:30 pm", "party": 5, "name": "Patel", "phone": "", "status": "confirmed"},
        },
        "next_ref": 5101,
    },
    "desk": {
        "agents": ["Dana Okafor", "Priya Shah", "Leo Marsh"],
        "me": "Support Bot",
        "customers": {
            "c1": {"name": "Ana Lima", "email": "ana.lima@example.com", "plan": "Plus"},
            "c2": {"name": "Mark Ruiz", "email": "mark.ruiz@example.com", "plan": "Basic"},
            "c3": {"name": "Joan Park", "email": "joan.park@example.net", "plan": "Plus"},
            "c4": {"name": "Sam Ortiz", "email": "s.ortiz@example.org", "plan": "Basic"},
        },
        "tickets": {
            4460: {"subject": "Charger stopped working", "customer": "c3", "status": "Closed", "priority": "P3", "assignee": "Leo Marsh", "product": "USB-C cable", "messages": [["Joan Park", "My charger cable stopped working after a week."]]},
            4471: {"subject": "Refund for damaged kettle", "customer": "c1", "status": "Open", "priority": "P2", "assignee": "Dana Okafor", "product": "Kettle", "messages": [["Ana Lima", "The kettle arrived cracked. How long do I have to ask for a refund?"]]},
            4472: {"subject": "Invoice address wrong", "customer": "c4", "status": "Open", "priority": "P3", "assignee": "Dana Okafor", "product": "-", "messages": [["Sam Ortiz", "Please change the address on invoice INV-2207."]]},
            4475: {"subject": "Site down at checkout", "customer": "c3", "status": "Open", "priority": "P3", "assignee": "Priya Shah", "product": "-", "messages": [["Joan Park", "Checkout shows an error 500 for every order."]]},
            4476: {"subject": "Missing item in order", "customer": "c2", "status": "Open", "priority": "P2", "assignee": "Dana Okafor", "product": "Mug", "messages": [["Mark Ruiz", "Order 1031 was missing the red mug."]]},
            4478: {"subject": "Warranty question", "customer": "c1", "status": "Open", "priority": "P3", "assignee": "Leo Marsh", "product": "Harbor wireless headphones", "messages": [["Ana Lima", "How long is the warranty on my headphones?"]]},
            4479: {"subject": "Change delivery date", "customer": "c2", "status": "Pending", "priority": "P3", "assignee": "Priya Shah", "product": "-", "messages": [["Mark Ruiz", "Can you deliver on Friday instead?"]]},
            4482: {"subject": "Payment taken twice", "customer": "c3", "status": "Open", "priority": "P1", "assignee": "Leo Marsh", "product": "-", "messages": [["Joan Park", "I was charged twice for order 1038."]]},
            4480: {"subject": "Password reset email never arrives", "customer": "c4", "status": "Open", "priority": "P2", "assignee": "", "product": "-", "messages": [["Sam Ortiz", "I've asked for a reset three times."]]},
        },
        "kb": {
            "refund-policy": ("Refund policy", ["Customers can request a refund within 30 days of delivery.", "Damaged items: we also pay return shipping.", "Refunds go back to the original payment method within 5 business days."]),
            "sla": ("Support targets (SLA)", ["P1: first response within 4 business hours.", "P2: first response within 1 business day.", "P3: first response within 3 business days.", "Business hours: Monday to Friday, 8 am to 6 pm ET."]),
            "warranty": ("Warranty", ["Harbor headphones and earbuds: 1-year warranty.", "Other electronics (cables, lamps, batteries): 2-year warranty.", "Kitchen items: 90 days."]),
            "shipping": ("Shipping times", ["Standard: 3 to 5 business days.", "Express: next business day, ordered before 2 pm ET."]),
        },
    },
}

STATE: dict = {}


def reset() -> None:
    STATE.clear()
    STATE.update(copy.deepcopy(SEED))


reset()

app = FastAPI(title="Agent Verdict demo sites", docs_url=None, redoc_url=None)

# ============================================================== page frame

THEMES = {
    "shop": ("Lakeshore Supply", "#0F4C5C", "#E36414", [("Shop", "/shop/"), ("Cart", "/shop/cart"), ("Orders", "/shop/orders")]),
    "bistro": ("Harbor Bistro", "#3D2C2E", "#B08968", [("Menu", "/bistro/menu"), ("Reservations", "/bistro/reserve"), ("Manage booking", "/bistro/manage"), ("Hours", "/bistro/#hours")]),
    "desk": ("Northpoint Help Desk", "#1D3557", "#457B9D", [("Tickets", "/desk/"), ("Knowledge base", "/desk/kb")]),
}

e = html.escape


def page(site: str, title: str, body: str) -> HTMLResponse:
    name, dark, accent, nav = THEMES[site]
    links = "".join(f'<a href="{href}">{e(label)}</a>' for label, href in nav)
    return HTMLResponse(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{e(title)} · {e(name)}</title>
<style>
*{{box-sizing:border-box}} body{{margin:0;font:15px/1.5 system-ui,Segoe UI,Arial,sans-serif;color:#1c1f23;background:#fafaf8}}
header{{background:{dark};color:#fff;display:flex;align-items:center;gap:28px;padding:14px 32px}}
header .brand{{font-weight:700;font-size:19px;color:#fff;text-decoration:none}} header nav a{{color:#e8ecef;margin-right:18px;text-decoration:none}}
main{{max-width:980px;margin:0 auto;padding:26px 32px 60px}} h1{{font-size:26px;margin:0 0 14px}} h2{{font-size:19px;margin:22px 0 10px}}
a{{color:{dark}}} .btn,button{{background:{accent};color:#fff;border:0;border-radius:6px;padding:9px 16px;font:600 14px system-ui;cursor:pointer;text-decoration:none;display:inline-block}}
.btn.alt,button.alt{{background:#fff;color:{dark};border:1px solid {dark}}} input,select,textarea{{font:14px system-ui;padding:8px 10px;border:1px solid #b9c0c7;border-radius:6px;background:#fff}}
label{{display:block;font-weight:600;margin:12px 0 4px}} table{{border-collapse:collapse;width:100%}} td,th{{text-align:left;padding:9px 10px;border-bottom:1px solid #e2e5e8}}
.card{{background:#fff;border:1px solid #e2e5e8;border-radius:8px;padding:16px 18px;margin:10px 0}} .muted{{color:#5d6670}} .note{{background:#fff4d6;border:1px solid #e9cf86;padding:10px 14px;border-radius:6px}}
.ok{{background:#e6f5ec;border:1px solid #9fd3b4;padding:10px 14px;border-radius:6px}} .bad{{background:#fdecec;border:1px solid #f0aaaa;padding:10px 14px;border-radius:6px}}
.price{{font-weight:700}} .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}}
</style></head><body><header><a class="brand" href="/{site}/">{e(name)}</a><nav>{links}</nav></header><main>{body}</main></body></html>""")


def go(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def money(x: float) -> str:
    return f"${x:,.2f}"

# ============================================================== shop


def _shop_items(skus) -> str:
    p = STATE["shop"]["products"]
    cards = []
    for sku in skus:
        it = p[sku]
        stock = ('<span style="color:#b42318">Out of stock</span>' if not it["stock"] else
                 '<span style="color:#b54708">Only 1 left</span>' if it["stock"] == 1 else '<span class="muted">In stock</span>')
        cards.append(f'<div class="card"><a href="/shop/p/{sku}"><b>{e(it["name"])}</b></a><br>'
                     f'<span class="price">{money(it["price"])}</span> · {stock}</div>')
    return f'<div class="grid">{"".join(cards)}</div>'


@app.get("/shop/", response_class=HTMLResponse)
def shop_home():
    cats = sorted({v["cat"] for v in STATE["shop"]["products"].values()})
    cat_links = " · ".join(f'<a href="/shop/search?{urlencode({"cat": c})}">{e(c)}</a>' for c in cats)
    return page("shop", "Home", f"""<h1>Everything for home and desk</h1>
<form action="/shop/search" method="get"><label for="q">Search products</label>
<input id="q" name="q" placeholder="Search" style="width:340px"> <button type="submit">Search</button></form>
<h2>Categories</h2><p>{cat_links}</p><h2>Popular</h2>{_shop_items(["aa-4", "mug-blue", "bottle", "headphones"])}""")


@app.get("/shop/search", response_class=HTMLResponse)
def shop_search(q: str = "", cat: str = "", sort: str = ""):
    p = STATE["shop"]["products"]
    words = [w for w in q.lower().replace("-", " ").split() if w]
    hits = [s for s, v in p.items()
            if (not cat or v["cat"] == cat) and all(w in (v["name"] + " " + v["cat"]).lower().replace("-", " ") for w in words)]
    if sort == "price":
        hits.sort(key=lambda s: p[s]["price"])
    sort_link = f'/shop/search?{urlencode({"q": q, "cat": cat, "sort": "price"})}'
    title = f'Results for "{q}"' if q else (cat or "All products")
    body = (f'<h1>{e(title)}</h1><p>{len(hits)} results · <a href="{sort_link}">Sort: price, low to high</a></p>'
            + (_shop_items(hits) if hits else '<p class="muted">No products match.</p>'))
    return page("shop", title, body)


@app.get("/shop/p/{sku}", response_class=HTMLResponse)
def shop_product(sku: str):
    it = STATE["shop"]["products"].get(sku)
    if not it:
        return page("shop", "Not found", "<h1>Product not found</h1>")
    if it["stock"]:
        buy = f"""<form action="/shop/cart/add" method="post"><input type="hidden" name="sku" value="{sku}">
<label for="qty">Quantity</label><input id="qty" name="qty" type="number" value="1" min="1" style="width:90px">
<p><button type="submit">Add to cart</button></p></form>"""
    else:
        buy = '<p class="bad">Out of stock. We don\'t know when it will be back.</p><p><button disabled style="opacity:.5">Add to cart</button></p>'
    return page("shop", it["name"], f"""<p class="muted">{e(it["cat"])}</p><h1>{e(it["name"])}</h1>
<p class="price" style="font-size:22px">{money(it["price"])}</p>{buy}""")


@app.post("/shop/cart/add")
def shop_cart_add(sku: str = Form(...), qty: int = Form(1)):
    p = STATE["shop"]["products"]
    cart = STATE["shop"]["cart"]
    if sku in p and p[sku]["stock"] and qty > 0:
        room = p[sku]["stock"] - cart.get(sku, 0)
        if qty > room:  # like real shops: add what's left, and say so in a small notice
            if room > 0:
                cart[sku] = cart.get(sku, 0) + room
            return go("/shop/cart?msg=" + quote(f"Only {p[sku]['stock']} left in stock, so we added {max(room, 0)}."))
        cart[sku] = cart.get(sku, 0) + qty
    return go("/shop/cart")


def _cart_total() -> tuple[float, float, float]:
    s = STATE["shop"]
    sub = sum(s["products"][k]["price"] * q for k, q in s["cart"].items())
    disc = round(sub * 0.10, 2) if s["coupon"] == "LAKE10" else 0.0
    return round(sub, 2), disc, round(sub - disc, 2)


@app.get("/shop/cart", response_class=HTMLResponse)
def shop_cart(msg: str = ""):
    s = STATE["shop"]
    if not s["cart"]:
        return page("shop", "Cart", '<h1>Your cart</h1><p class="muted">Your cart is empty.</p><p><a class="btn" href="/shop/">Continue shopping</a></p>')
    rows = "".join(f'<tr><td>{e(s["products"][k]["name"])}</td><td>{q}</td><td>{money(s["products"][k]["price"] * q)}</td>'
                   f'<td><form action="/shop/cart/remove" method="post"><input type="hidden" name="sku" value="{k}"><button class="alt" type="submit">Remove</button></form></td></tr>'
                   for k, q in s["cart"].items())
    sub, disc, total = _cart_total()
    note = f'<p class="{"ok" if "applied" in msg else "bad"}">{e(msg)}</p>' if msg else ""
    disc_row = f"<p>Coupon {e(s['coupon'])}: −{money(disc)}</p>" if disc else ""
    return page("shop", "Cart", f"""<h1>Your cart</h1>{note}<table><tr><th>Item</th><th>Qty</th><th>Price</th><th></th></tr>{rows}</table>
<p>Subtotal {money(sub)}</p>{disc_row}<p class="price">Total {money(total)}</p>
<form action="/shop/cart/coupon" method="post"><label for="coupon">Coupon code</label><input id="coupon" name="code"> <button class="alt" type="submit">Apply</button></form>
<p style="margin-top:22px"><a class="btn" href="/shop/checkout/shipping">Checkout</a></p>""")


@app.post("/shop/cart/remove")
def shop_cart_remove(sku: str = Form(...)):
    STATE["shop"]["cart"].pop(sku, None)
    return go("/shop/cart")


@app.post("/shop/cart/coupon")
def shop_coupon(code: str = Form("")):
    if code.strip().upper() == "LAKE10":
        STATE["shop"]["coupon"] = "LAKE10"
        return go("/shop/cart?msg=" + quote("Coupon LAKE10 applied: 10% off."))
    if code.strip().upper() == "SAVE20":
        return go("/shop/cart?msg=" + quote("The code SAVE20 has expired."))
    return go("/shop/cart?msg=" + quote("That coupon code isn't valid."))


@app.get("/shop/checkout/shipping", response_class=HTMLResponse)
def shop_shipping():
    s = STATE["shop"]
    if not s["cart"]:
        return go("/shop/cart")
    return page("shop", "Shipping", f"""<h1>Shipping</h1><form action="/shop/checkout/shipping" method="post">
<label><input type="radio" name="choice" value="saved" checked> Saved address: {e(s["saved_address"])}</label>
<label><input type="radio" name="choice" value="new"> A new address</label>
<label for="street">Street and number</label><input id="street" name="street" style="width:340px">
<label for="city">City, state, ZIP</label><input id="city" name="city" style="width:340px">
<p class="muted">Standard shipping, 3 to 5 days.</p><p><button type="submit">Continue to review</button></p></form>""")


@app.post("/shop/checkout/shipping")
def shop_shipping_post(choice: str = Form("saved"), street: str = Form(""), city: str = Form("")):
    s = STATE["shop"]
    if choice == "new" and street.strip():
        s["address"] = f"{street.strip()}, {city.strip()}".strip(", ")
    else:
        s["address"] = s["saved_address"]
    return go("/shop/checkout/review")


@app.get("/shop/checkout/review", response_class=HTMLResponse)
def shop_review():
    s = STATE["shop"]
    if not s["cart"]:
        return go("/shop/cart")
    items = "".join(f"<li>{q} × {e(s['products'][k]['name'])}</li>" for k, q in s["cart"].items())
    sub, disc, total = _cart_total()
    return page("shop", "Review your order", f"""<h1>Review your order</h1><ul>{items}</ul>
<p>Ship to: {e(s["address"] or s["saved_address"])}</p>{f"<p>Coupon LAKE10: −{money(disc)}</p>" if disc else ""}
<p class="price">Total {money(total)}</p>
<p class="note">Your order is not placed until you select Place order.</p>
<form action="/shop/checkout/place" method="post"><button type="submit">Place order</button></form>""")


@app.post("/shop/checkout/place")
def shop_place():
    s = STATE["shop"]
    if not s["cart"]:
        return go("/shop/cart")
    _, _, total = _cart_total()
    oid = s["next_order"]
    s["next_order"] += 1
    s["orders"].append({"id": oid, "items": dict(s["cart"]), "coupon": s["coupon"],
                        "address": s["address"] or s["saved_address"], "total": total, "date": "Nov 28, 2026"})
    s["cart"], s["coupon"], s["address"] = {}, None, None
    return go(f"/shop/orders/{oid}")


@app.get("/shop/orders", response_class=HTMLResponse)
def shop_orders():
    rows = "".join(f'<tr><td><a href="/shop/orders/{o["id"]}">#{o["id"]}</a></td><td>{e(o["date"])}</td><td>{money(o["total"])}</td></tr>'
                   for o in reversed(STATE["shop"]["orders"]))
    return page("shop", "Orders", f"<h1>Your orders</h1><table><tr><th>Order</th><th>Date</th><th>Total</th></tr>{rows}</table>")


@app.get("/shop/orders/{oid}", response_class=HTMLResponse)
def shop_order(oid: int):
    o = next((x for x in STATE["shop"]["orders"] if x["id"] == oid), None)
    if not o:
        return page("shop", "Not found", "<h1>Order not found</h1>")
    items = "".join(f"<li>{q} × {e(STATE['shop']['products'][k]['name'])}</li>" for k, q in o["items"].items())
    return page("shop", f"Order {oid}", f"""<p class="ok">Thank you! Order #{oid} is placed.</p><h1>Order #{oid}</h1>
<ul>{items}</ul><p>Ship to: {e(o["address"])}</p><p class="price">Total {money(o["total"])}</p><p class="muted">Placed {e(o["date"])}</p>""")

# ============================================================== bistro

MENU = [("Starters", [("Lake chowder", 11, ""), ("Charred carrots, tahini", 9, "vegan")]),
        ("Mains", [("Lobster roll", 29, ""), ("Seared walleye", 26, ""), ("Charred cauliflower steak", 18, "vegan"),
                   ("Mushroom risotto", 21, "vegetarian"), ("Lentil and squash stew", 22, "vegan")]),
        ("Desserts", [("Maple tart", 9, ""), ("Sorbet trio", 8, "vegan")])]
HOURS = [("Monday", "Closed"), ("Tuesday to Thursday", "5 pm to 10 pm"), ("Friday and Saturday", "5 pm to 11 pm"), ("Sunday", "4 pm to 9 pm")]


@app.get("/bistro/", response_class=HTMLResponse)
def bistro_home():
    hours = "".join(f"<tr><td>{d}</td><td>{h}</td></tr>" for d, h in HOURS)
    return page("bistro", "Home", f"""<h1>Seafood and seasonal plates on the lake</h1>
<p><a class="btn" href="/bistro/reserve">Book a table</a> <a class="btn alt" href="/bistro/manage">Manage a booking</a> <a class="btn alt" href="/bistro/menu">See the menu</a></p>
<h2 id="hours">Opening hours</h2><table>{hours}</table><p class="muted">Tables for up to {STATE["bistro"]["max_party"]} people. For larger groups, call us.</p>""")


@app.get("/bistro/menu", response_class=HTMLResponse)
def bistro_menu():
    out = []
    for section, items in MENU:
        rows = "".join(f'<tr><td>{e(n)}{f" <span class=muted>({t})</span>" if t else ""}</td><td class="price">${p}</td></tr>' for n, p, t in items)
        out.append(f"<h2>{section}</h2><table>{rows}</table>")
    return page("bistro", "Menu", "<h1>Menu</h1>" + "".join(out))


@app.get("/bistro/reserve", response_class=HTMLResponse)
def bistro_reserve(date: str = "", error: str = ""):
    b = STATE["bistro"]
    dates = list(b["slots"])
    date = date if date in b["slots"] else ""
    date_opts = "".join(f'<option value="{e(d)}"{" selected" if d == date else ""}>{e(d)}</option>' for d in dates)
    if not date:
        return page("bistro", "Book a table", f"""<h1>Book a table</h1><form action="/bistro/reserve" method="get">
<label for="date">Date</label><select id="date" name="date">{date_opts}</select>
<p><button type="submit">See available times</button></p></form>""")
    times = "".join(f'<option value="{t}">{t}</option>' for t in b["slots"][date])
    parties = "".join(f'<option value="{n}">{n}</option>' for n in range(1, b["max_party"] + 1))
    err = f'<p class="bad">{e(error)}</p>' if error else ""
    return page("bistro", "Book a table", f"""<h1>Book a table: {e(date)}</h1>{err}
<p class="muted">Available times on {e(date)}: {", ".join(b["slots"][date])}. <a href="/bistro/reserve">Pick another date</a></p>
<form action="/bistro/reserve" method="post"><input type="hidden" name="date" value="{e(date)}">
<label for="time">Time</label><select id="time" name="time">{times}</select>
<label for="party">Party size</label><select id="party" name="party">{parties}</select>
<label for="name">Name for the booking</label><input id="name" name="name">
<label for="phone">Phone (optional)</label><input id="phone" name="phone">
<p><button type="submit">Confirm booking</button></p></form>""")


@app.post("/bistro/reserve")
def bistro_reserve_post(date: str = Form(...), time: str = Form(...), party: int = Form(...), name: str = Form(""), phone: str = Form("")):
    b = STATE["bistro"]
    if not name.strip():
        return go(f"/bistro/reserve?{urlencode({'date': date, 'error': 'Please enter a name for the booking.'})}")
    if date not in b["slots"] or time not in b["slots"][date] or not 1 <= party <= b["max_party"]:
        return go(f"/bistro/reserve?{urlencode({'date': date, 'error': 'That time or party size is not available.'})}")
    ref = f"HB-{b['next_ref']}"
    b["next_ref"] += 1
    # Saturday from 8 pm, tables for 6 or more are waitlisted, not booked (the page says so, quietly)
    wait = date.startswith("Sat") and time in ("8:00 pm", "8:30 pm") and party >= 6
    b["bookings"][ref] = {"date": date, "time": time, "party": party, "name": name.strip(), "phone": phone.strip(),
                          "status": "waitlist" if wait else "confirmed"}
    return go(f"/bistro/booking/{ref}?new=1")


@app.get("/bistro/manage", response_class=HTMLResponse)
def bistro_manage(error: str = ""):
    err = f'<p class="bad">{e(error)}</p>' if error else ""
    return page("bistro", "Manage a booking", f"""<h1>Manage a booking</h1>{err}<form action="/bistro/manage/find" method="post">
<label for="ref">Booking reference</label><input id="ref" name="ref" placeholder="HB-0000"> <button type="submit">Find booking</button></form>""")


@app.post("/bistro/manage/find")
def bistro_find(ref: str = Form("")):
    ref = ref.strip().upper()
    if ref in STATE["bistro"]["bookings"]:
        return go(f"/bistro/booking/{ref}")
    return go("/bistro/manage?error=" + quote("We couldn't find that booking."))


@app.get("/bistro/booking/{ref}", response_class=HTMLResponse)
def bistro_booking(ref: str, new: int = 0, msg: str = ""):
    bk = STATE["bistro"]["bookings"].get(ref)
    if not bk:
        return page("bistro", "Not found", "<h1>Booking not found</h1>")
    if new and bk["status"] == "waitlist":
        top = (f'<p class="ok">Request received. Reference {ref}.</p><p class="muted">Saturday evenings are busy: tables for 6 or '
               f'more after 8 pm go on our waitlist. We\'ll text you if a table opens up.</p>')
    else:
        top = f'<p class="ok">You\'re booked. Reference {ref}.</p>' if new else (f'<p class="ok">{e(msg)}</p>' if msg else "")
    if bk["status"] == "waitlist" and not new:
        top += '<p class="muted">Status: on the waitlist.</p>'
    if bk["status"] == "cancelled":
        actions = '<p class="bad">This booking is cancelled.</p>'
    else:
        parties = "".join(f'<option value="{n}"{" selected" if n == bk["party"] else ""}>{n}</option>' for n in range(1, STATE["bistro"]["max_party"] + 1))
        actions = f"""<form action="/bistro/booking/{ref}/party" method="post"><label for="party">Change party size</label>
<select id="party" name="party">{parties}</select> <button class="alt" type="submit">Update party size</button></form>
<form action="/bistro/booking/{ref}/cancel" method="post" style="margin-top:18px"><button type="submit">Cancel booking</button></form>"""
    return page("bistro", f"Booking {ref}", f"""{top}<h1>Booking {ref}</h1>
<div class="card">{e(bk["date"])} · {e(bk["time"])} · party of {bk["party"]} · {e(bk["name"])}{f" · {e(bk['phone'])}" if bk["phone"] else ""}</div>{actions}""")


@app.post("/bistro/booking/{ref}/cancel")
def bistro_cancel(ref: str):
    if ref in STATE["bistro"]["bookings"]:
        STATE["bistro"]["bookings"][ref]["status"] = "cancelled"
    return go(f"/bistro/booking/{ref}?msg=" + quote("Your booking is cancelled."))


@app.post("/bistro/booking/{ref}/party")
def bistro_party(ref: str, party: int = Form(...)):
    bk = STATE["bistro"]["bookings"].get(ref)
    if bk and 1 <= party <= STATE["bistro"]["max_party"]:
        bk["party"] = party
    return go(f"/bistro/booking/{ref}?msg=" + quote(f"Party size updated to {party}."))

# ============================================================== help desk


def _cust(cid: str) -> dict:
    return STATE["desk"]["customers"][cid]


@app.get("/desk/", response_class=HTMLResponse)
def desk_tickets(status: str = "", assignee: str = ""):
    d = STATE["desk"]
    rows = []
    for tid, t in sorted(d["tickets"].items()):
        if (status and t["status"] != status) or (assignee and t["assignee"] != assignee):
            continue
        rows.append(f'<tr><td><a href="/desk/tickets/{tid}">#{tid}</a></td><td>{e(t["subject"])}</td><td>{e(_cust(t["customer"])["name"])}</td>'
                    f'<td>{t["status"]}</td><td>{t["priority"]}</td><td>{e(t["assignee"] or "Unassigned")}</td></tr>')
    filt = " · ".join(f'<a href="/desk/?status={s}">{s}</a>' for s in ("Open", "Pending", "Closed"))
    agents = " · ".join(f'<a href="/desk/?{urlencode({"assignee": a})}">{e(a)}</a>' for a in d["agents"])
    return page("desk", "Tickets", f"""<h1>Tickets</h1><p>Status: <a href="/desk/">All</a> · {filt}</p><p>Assignee: {agents}</p>
<table><tr><th>Ticket</th><th>Subject</th><th>Customer</th><th>Status</th><th>Priority</th><th>Assignee</th></tr>{"".join(rows)}</table>""")


@app.get("/desk/tickets/{tid}", response_class=HTMLResponse)
def desk_ticket(tid: int, msg: str = "", error: str = "", held: int = 0):
    d = STATE["desk"]
    t = d["tickets"].get(tid)
    if not t:
        return page("desk", "Not found", "<h1>Ticket not found</h1>")
    c = _cust(t["customer"])
    thread = "".join(f'<div class="card"><b>{e(who)}</b><br>{e(text)}</div>' for who, text in t["messages"])
    sel = lambda name, opts, cur: "".join(f'<option{" selected" if o == cur else ""}>{e(o)}</option>' for o in opts)  # noqa: E731
    top = (f'<p class="bad">{e(error)}</p>' if error else "") + (f'<p class="ok">{e(msg)}</p>' if msg else "")
    if held:
        top += '<p class="note">Saved as a draft.</p>'
    drafts = "".join(f'<div class="card" style="opacity:.75"><b>Draft (not sent)</b><br>{e(x)}</div>' for x in t.get("drafts", []))
    if drafts:
        drafts = f'<p class="muted">Replies to a closed ticket are kept as drafts. Reopen the ticket to send them.</p>{drafts}'
    return page("desk", f"Ticket {tid}", f"""{top}<h1>#{tid} {e(t["subject"])}</h1>
<p>Customer: <a href="/desk/customers/{t["customer"]}">{e(c["name"])}</a> · Product: {e(t["product"])}</p>
<p>Status: <b>{t["status"]}</b> · Priority: <b>{t["priority"]}</b> · Assignee: <b>{e(t["assignee"] or "Unassigned")}</b></p>
<form action="/desk/tickets/{tid}/assign-me" method="post"><button class="alt" type="submit">Assign to me</button></form>
<h2>Conversation</h2>{thread}{drafts}
<form action="/desk/tickets/{tid}/reply" method="post"><label for="reply">Reply to customer</label>
<textarea id="reply" name="text" rows="4" style="width:100%"></textarea><p><button type="submit">Send reply</button></p></form>
<h2>Ticket fields</h2><form action="/desk/tickets/{tid}/update" method="post" style="display:flex;gap:14px;flex-wrap:wrap;align-items:end">
<div><label for="status">Status</label><select id="status" name="status">{sel("status", ["Open", "Pending", "Closed"], t["status"])}</select></div>
<div><label for="priority">Priority</label><select id="priority" name="priority">{sel("priority", ["P1", "P2", "P3"], t["priority"])}</select></div>
<div><label for="assignee">Assignee</label><select id="assignee" name="assignee">{sel("assignee", ["Unassigned"] + d["agents"] + [d["me"]], t["assignee"] or "Unassigned")}</select></div>
<div style="flex-basis:100%"><label for="resolution">Resolution note (required to close a P1 ticket)</label>
<textarea id="resolution" name="resolution" rows="2" style="width:100%"></textarea></div>
<div><button type="submit">Update ticket</button></div></form>""")


@app.post("/desk/tickets/{tid}/reply")
def desk_reply(tid: int, text: str = Form("")):
    t = STATE["desk"]["tickets"].get(tid)
    if t and text.strip() and t["status"] == "Closed":  # held as a draft, not sent
        t.setdefault("drafts", []).append(text.strip())
        return go(f"/desk/tickets/{tid}?held=1")
    if t and text.strip():
        t["messages"].append([STATE["desk"]["me"], text.strip()])
        return go(f"/desk/tickets/{tid}?msg=" + quote("Reply sent to customer."))
    return go(f"/desk/tickets/{tid}")


@app.post("/desk/tickets/{tid}/update")
def desk_update(tid: int, status: str = Form(...), priority: str = Form(...), assignee: str = Form(...),
                resolution: str = Form("")):
    t = STATE["desk"]["tickets"].get(tid)
    if t and status == "Closed" and t["status"] != "Closed" and priority == "P1" and not resolution.strip():
        return go(f"/desk/tickets/{tid}?error=" + quote("P1 tickets need a resolution note before they can be closed. Nothing was changed."))
    if t:
        if resolution.strip():
            t["resolution"] = resolution.strip()
        t["status"], t["priority"] = status, priority
        t["assignee"] = "" if assignee == "Unassigned" else assignee
    return go(f"/desk/tickets/{tid}?msg=" + quote("Ticket updated."))


@app.post("/desk/tickets/{tid}/assign-me")
def desk_assign_me(tid: int):
    t = STATE["desk"]["tickets"].get(tid)
    if t:
        t["assignee"] = STATE["desk"]["me"]
    return go(f"/desk/tickets/{tid}?msg=" + quote("Assigned to you."))


@app.get("/desk/customers/{cid}", response_class=HTMLResponse)
def desk_customer(cid: str):
    c = STATE["desk"]["customers"].get(cid)
    if not c:
        return page("desk", "Not found", "<h1>Customer not found</h1>")
    tickets = "".join(f'<li><a href="/desk/tickets/{tid}">#{tid} {e(t["subject"])}</a> ({t["status"]})</li>'
                      for tid, t in STATE["desk"]["tickets"].items() if t["customer"] == cid)
    return page("desk", c["name"], f"""<h1>{e(c["name"])}</h1><p>Email: {e(c["email"])}</p><p>Plan: {e(c["plan"])}</p><h2>Tickets</h2><ul>{tickets}</ul>""")


@app.get("/desk/kb", response_class=HTMLResponse)
def desk_kb():
    items = "".join(f'<li><a href="/desk/kb/{slug}">{e(title)}</a></li>' for slug, (title, _) in STATE["desk"]["kb"].items())
    return page("desk", "Knowledge base", f"<h1>Knowledge base</h1><ul>{items}</ul>")


@app.get("/desk/kb/{slug}", response_class=HTMLResponse)
def desk_article(slug: str):
    art = STATE["desk"]["kb"].get(slug)
    if not art:
        return page("desk", "Not found", "<h1>Article not found</h1>")
    title, lines = art
    return page("desk", title, f"<h1>{e(title)}</h1>" + "".join(f"<p>{e(x)}</p>" for x in lines))

# ============================================================== control (for the harness, not the agent)


@app.get("/")
def index():
    return HTMLResponse('<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Demo sites</title></head>'
                        '<body style="font:16px system-ui;padding:32px"><h1>Agent Verdict demo sites</h1><ul>'
                        '<li><a href="/shop/">Lakeshore Supply</a> (shop)</li><li><a href="/bistro/">Harbor Bistro</a> (restaurant)</li>'
                        '<li><a href="/desk/">Northpoint Help Desk</a> (support)</li></ul></body></html>')


@app.post("/_reset")
def control_reset():
    reset()
    return {"ok": True}


@app.get("/_state")
def control_state(request: Request):
    return JSONResponse(STATE)
