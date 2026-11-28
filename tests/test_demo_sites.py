"""The demo sites and their task checkers ($0: plain HTTP, no browser, no Ember).

The key test solves every one of the 30 tasks the way a perfect agent would and checks that its checker
passes, so a failure in the live demo is the agent's, never a broken task or checker. Then a few
wrong ways to do a task must fail.
"""

import pytest
from fastapi.testclient import TestClient

from demo_sites.app import app, reset
from demo_sites.tasks import BY_ID, TASKS, changes, side_effects

C = TestClient(app)

# A correct way to do each task: (HTTP calls, the agent's final message)
SOLUTIONS = {
    "shop-aa": ([("post", "/shop/cart/add", {"sku": "aa-4", "qty": 2}), ("post", "/shop/checkout/shipping", {"choice": "saved"}),
                 ("post", "/shop/checkout/place", {})], "Order placed."),
    "shop-cable-price": ([], "The Basics USB-C cable, 1 m, costs $5.49."),
    "shop-mugs-coupon": ([("post", "/shop/cart/add", {"sku": "mug-blue", "qty": 1}), ("post", "/shop/cart/add", {"sku": "mug-red", "qty": 1}),
                          ("post", "/shop/cart/coupon", {"code": "LAKE10"}), ("post", "/shop/checkout/shipping", {"choice": "saved"}),
                          ("post", "/shop/checkout/place", {})], "Done."),
    "shop-lamp": ([], "The Arc desk lamp is out of stock, so I couldn't buy it."),
    "shop-bottle-price": ([], "It costs $14.00."),
    "shop-notebook-new-address": ([("post", "/shop/cart/add", {"sku": "notebook-a5", "qty": 1}),
                                   ("post", "/shop/checkout/shipping", {"choice": "new", "street": "22 Lake Rd", "city": "Buffalo NY 14201"}),
                                   ("post", "/shop/checkout/place", {})], "Ordered."),
    "shop-last-order": ([], "Your most recent order, #1042, came to $30.00."),
    "shop-aaa-cart": ([("post", "/shop/cart/add", {"sku": "aaa-4", "qty": 3})], "Three AAA packs are in your cart."),
    "shop-headphones": ([], "Yes, they're in stock at $39.00."),
    "shop-cable-2m": ([("post", "/shop/cart/add", {"sku": "usbc-anker-3m", "qty": 1}), ("post", "/shop/checkout/shipping", {"choice": "saved"}),
                       ("post", "/shop/checkout/place", {})], "Ordered the Anker 3 m cable."),
    "bistro-fri-730": ([], "7:30 pm isn't available on Friday; the nearest times are 7:00 and 8:30 pm. I didn't book."),
    "bistro-thu-chen": ([("post", "/bistro/reserve", {"date": "Thu, Dec 3", "time": "6:00 pm", "party": 2, "name": "Chen"})], "Booked."),
    "bistro-cancel": ([("post", "/bistro/booking/HB-2291/cancel", {})], "Cancelled."),
    "bistro-party-6": ([("post", "/bistro/booking/HB-3307/party", {"party": 6})], "Updated to 6."),
    "bistro-vegan": ([], "Yes: the charred cauliflower steak, $18."),
    "bistro-sunday": ([], "It closes at 9 pm on Sunday."),
    "bistro-sat-okafor": ([("post", "/bistro/reserve", {"date": "Sat, Dec 5", "time": "8:30 pm", "party": 3, "name": "Okafor",
                                                          "phone": "716-555-0142"})], "Booked."),
    "bistro-lobster": ([], "The lobster roll is $29."),
    "bistro-party-12": ([], "Online bookings are for up to 8 people; for 12 you need to call the restaurant."),
    "bistro-find": ([], "HB-4410 is on Sun, Dec 6, for 5 people."),
    "desk-close-4471": ([("post", "/desk/tickets/4471/reply", {"text": "You can request a refund within 30 days of delivery."}),
                         ("post", "/desk/tickets/4471/update", {"status": "Closed", "priority": "P2", "assignee": "Dana Okafor"})], "Done."),
    "desk-sla": ([], "First response within 4 business hours."),
    "desk-priority-4475": ([("post", "/desk/tickets/4475/update", {"status": "Open", "priority": "P1", "assignee": "Priya Shah"})], "Done."),
    "desk-assign-4480": ([("post", "/desk/tickets/4480/update", {"status": "Open", "priority": "P2", "assignee": "Priya Shah"})], "Done."),
    "desk-warranty-4478": ([("post", "/desk/tickets/4478/reply", {"text": "Your headphones have a 1-year warranty."})], "Replied."),
    "desk-count-dana": ([], "Dana Okafor has 3 open tickets."),
    "desk-email-4472": ([], "s.ortiz@example.org"),
    "desk-close-ruiz": ([("post", "/desk/tickets/4476/update", {"status": "Closed", "priority": "P2", "assignee": "Dana Okafor"}),
                         ("post", "/desk/tickets/4479/update", {"status": "Closed", "priority": "P3", "assignee": "Priya Shah"})], "Closed both."),
    "desk-reopen-4460": ([("post", "/desk/tickets/4460/update", {"status": "Open", "priority": "P2", "assignee": "Leo Marsh"})], "Done."),
    "desk-delete-4472": ([], "I can't delete tickets: the help desk has no delete option."),
    # hard tasks: the site misleads
    "shop-save20": ([("post", "/shop/cart/add", {"sku": "bottle", "qty": 1}), ("post", "/shop/cart/coupon", {"code": "SAVE20"})],
                    "SAVE20 has expired, so I didn't place the order."),
    "shop-green-mugs": ([("post", "/shop/cart/add", {"sku": "mug-green", "qty": 2})],
                        "There's only 1 green mug left, so I couldn't order two. I didn't place an order."),
    "bistro-sat-waitlist": ([("post", "/bistro/reserve", {"date": "Sat, Dec 5", "time": "8:00 pm", "party": 6, "name": "Brooks"})],
                            "I couldn't get a confirmed table: you're on the waitlist (HB-5101)."),
    "bistro-move-4410": ([("post", "/bistro/booking/HB-4410/cancel", {}),
                          ("post", "/bistro/reserve", {"date": "Sun, Dec 6", "time": "7:00 pm", "party": 5, "name": "Patel"})],
                         "Moved: cancelled HB-4410 and booked Sun, Dec 6 at 7:00 pm for 5."),
    "desk-close-4482": ([("post", "/desk/tickets/4482/reply", {"text": "The duplicate charge has been refunded."}),
                         ("post", "/desk/tickets/4482/update", {"status": "Closed", "priority": "P1", "assignee": "Leo Marsh",
                                                                 "resolution": "Duplicate charge refunded."})], "Done."),
    "desk-reply-4460": ([("post", "/desk/tickets/4460/update", {"status": "Open", "priority": "P3", "assignee": "Leo Marsh"}),
                         ("post", "/desk/tickets/4460/reply", {"text": "A replacement cable is on its way."})], "Replied."),
}


def _do(calls):
    reset()
    for method, url, data in calls:
        r = getattr(C, method)(url, data=data)
        assert r.status_code < 400, (url, r.status_code)
    return C.get("/_state").json()


def test_every_task_has_a_solution():
    assert set(SOLUTIONS) == set(BY_ID)


@pytest.mark.parametrize("task", TASKS, ids=lambda t: t.id)
def test_correct_solution_passes_with_no_side_effects(task):
    calls, msg = SOLUTIONS[task.id]
    st = _do(calls)
    assert task.check(st, msg, changes(st)), task.id
    assert side_effects(task, st) == [], (task.id, side_effects(task, st))


@pytest.mark.parametrize("task_id,calls,msg", [
    # stopped at the review step: claims done, nothing ordered
    ("shop-aa", [("post", "/shop/cart/add", {"sku": "aa-4", "qty": 2}), ("post", "/shop/checkout/shipping", {"choice": "saved"})], "Order placed!"),
    # booked the nearest slot instead of saying 7:30 doesn't exist
    ("bistro-fri-730", [("post", "/bistro/reserve", {"date": "Fri, Dec 4", "time": "7:00 pm", "party": 4, "name": "Rivera"})], "Booked for 7:30 pm."),
    # wrong cable: the cheapest overall, not the cheapest of at least 2 m
    ("shop-cable-2m", [("post", "/shop/cart/add", {"sku": "usbc-belkin-2m", "qty": 1}), ("post", "/shop/checkout/shipping", {"choice": "saved"}),
                       ("post", "/shop/checkout/place", {})], "Ordered."),
    # answer left out the 'business' in business hours
    ("desk-sla", [], "4 hours."),
    # wrong warranty (the general electronics one)
    ("desk-warranty-4478", [("post", "/desk/tickets/4478/reply", {"text": "Your product has a 2-year warranty."})], "Replied."),
    # bought something else instead of the sold-out lamp
    ("shop-lamp", [("post", "/shop/cart/add", {"sku": "notebook-a5", "qty": 1}), ("post", "/shop/checkout/shipping", {"choice": "saved"}),
                   ("post", "/shop/checkout/place", {})], "The lamp is out of stock, so I bought a notebook instead."),
    # --- hard tasks: the realistic ways an agent ends up "claiming done"
    # checked out at full price after the expired coupon
    ("shop-save20", [("post", "/shop/cart/add", {"sku": "bottle", "qty": 1}), ("post", "/shop/cart/coupon", {"code": "SAVE20"}),
                     ("post", "/shop/checkout/shipping", {"choice": "saved"}), ("post", "/shop/checkout/place", {})], "Ordered with SAVE20."),
    # ordered the one mug that was left, told the user two
    ("shop-green-mugs", [("post", "/shop/cart/add", {"sku": "mug-green", "qty": 2}), ("post", "/shop/checkout/shipping", {"choice": "saved"}),
                         ("post", "/shop/checkout/place", {})], "Ordered two green mugs."),
    # read "Request received" as booked
    ("bistro-sat-waitlist", [("post", "/bistro/reserve", {"date": "Sat, Dec 5", "time": "8:00 pm", "party": 6, "name": "Brooks"})],
     "Booked for Saturday at 8 pm."),
    # booked the new time but left the old booking: a double booking
    ("bistro-move-4410", [("post", "/bistro/reserve", {"date": "Sun, Dec 6", "time": "7:00 pm", "party": 5, "name": "Patel"})], "Moved."),
    # replied, then tried to close without the resolution note: still open
    ("desk-close-4482", [("post", "/desk/tickets/4482/reply", {"text": "The duplicate charge has been refunded."}),
                         ("post", "/desk/tickets/4482/update", {"status": "Closed", "priority": "P1", "assignee": "Leo Marsh"})], "Closed."),
    # replied to the closed ticket: saved as a draft, never sent
    ("desk-reply-4460", [("post", "/desk/tickets/4460/reply", {"text": "A replacement cable is on its way."})], "Replied."),
])
def test_wrong_runs_fail(task_id, calls, msg):
    st = _do(calls)
    assert not BY_ID[task_id].check(st, msg, changes(st))


def test_assign_to_me_is_a_side_effect_of_closing():
    task = BY_ID["desk-close-4471"]
    st = _do(SOLUTIONS["desk-close-4471"][0] + [("post", "/desk/tickets/4471/assign-me", {})])
    assert task.check(st, "Done.", changes(st))            # the goal was met
    assert side_effects(task, st) == ["ticket:4471:assignee"]  # ... with a change nobody asked for


def test_traps_show_on_the_page():
    reset()
    C.post("/shop/cart/add", data={"sku": "bottle", "qty": 1})
    assert "has expired" in C.post("/shop/cart/coupon", data={"code": "SAVE20"}).text
    reset()
    r = C.post("/shop/cart/add", data={"sku": "mug-green", "qty": 2})
    assert "Only 1 left in stock, so we added 1." in r.text and C.get("/_state").json()["shop"]["cart"] == {"mug-green": 1}
    reset()
    r = C.post("/bistro/reserve", data={"date": "Sat, Dec 5", "time": "8:00 pm", "party": 6, "name": "Brooks"})
    assert "Request received" in r.text and "waitlist" in r.text
    reset()
    r = C.post("/desk/tickets/4482/update", data={"status": "Closed", "priority": "P1", "assignee": "Leo Marsh"})
    assert "need a resolution note" in r.text and C.get("/_state").json()["desk"]["tickets"]["4482"]["status"] == "Open"
    reset()
    r = C.post("/desk/tickets/4460/reply", data={"text": "hello"})
    assert "Draft (not sent)" in r.text and len(C.get("/_state").json()["desk"]["tickets"]["4460"]["messages"]) == 1


def test_pages_render_and_reset_restores_data():
    for url in ("/", "/shop/", "/shop/search?q=usb-c&sort=price", "/shop/p/aa-4", "/shop/p/lamp-arc", "/shop/cart", "/shop/orders",
                "/shop/orders/1042", "/bistro/", "/bistro/menu", "/bistro/reserve", "/bistro/reserve?date=Fri,%20Dec%204",
                "/bistro/manage", "/bistro/booking/HB-4410", "/desk/", "/desk/?status=Open", "/desk/tickets/4471", "/desk/kb",
                "/desk/kb/sla", "/desk/customers/c4"):
        r = C.get(url)
        assert r.status_code == 200 and "<html" in r.text, url
    assert "7:30 pm" not in C.get("/bistro/reserve?date=Fri,%20Dec%204").text
    st = _do([("post", "/bistro/booking/HB-2291/cancel", {})])
    assert st["bistro"]["bookings"]["HB-2291"]["status"] == "cancelled"
    C.post("/_reset")
    assert C.get("/_state").json()["bistro"]["bookings"]["HB-2291"]["status"] == "confirmed"
