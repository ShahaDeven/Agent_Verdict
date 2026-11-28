"""Three small local websites for the live demo: a shop, a restaurant, a help desk.

They exist so every agent run has a TRUE outcome: each site keeps its own records (orders, bookings,
tickets), and a task's checker reads those records after the run. Public sites can't give that, and
they change, block bots and may forbid automation.
"""
