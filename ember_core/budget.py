"""Spend ledger with a hard cap.

Every Ember call is appended to a JSONL ledger (usage_log.jsonl is the submission's proof of
usage). Before a request is sent, its worst-case cost is reserved; if spent + reserved + this
request would pass the cap, the request is refused and never sent.

The ledger only knows about calls made through this code. The Meta Usage page is the source of
truth: compare the two every day. Run one process at a time against a given ledger file.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CAP_USD = 7.00  # $10 credit minus margin for Usage-page lag and unknown image billing


class BudgetExceeded(RuntimeError):
    pass


class Ledger:
    def __init__(self, path: str | Path, cap_usd: float = DEFAULT_CAP_USD,
                 session_cap_usd: float | None = None):
        self.path = Path(path)
        self.cap_usd = cap_usd
        self.session_cap_usd = session_cap_usd
        self._lock = threading.Lock()
        self._reserved = 0.0
        self.session_spent = 0.0
        self.prior_spent = self._read_prior()

    def _read_prior(self) -> float:
        if not self.path.exists():
            return 0.0
        total = 0.0
        for n, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                total += float(json.loads(line).get("cost_usd", 0.0))
            except (ValueError, TypeError) as e:
                # A corrupt ledger means we can't trust the spend total; stop rather than guess.
                raise ValueError(f"{self.path}:{n} is not a valid ledger line: {e}") from e
        return total

    @property
    def total_spent(self) -> float:
        return self.prior_spent + self.session_spent

    @property
    def remaining(self) -> float:
        return self.cap_usd - self.total_spent

    @contextmanager
    def reserve(self, usd: float):
        with self._lock:
            if self.total_spent + self._reserved + usd > self.cap_usd:
                raise BudgetExceeded(
                    f"cap ${self.cap_usd:.2f}: spent ${self.total_spent:.4f}, "
                    f"in flight ${self._reserved:.4f}, this call up to ${usd:.4f}")
            if (self.session_cap_usd is not None
                    and self.session_spent + self._reserved + usd > self.session_cap_usd):
                raise BudgetExceeded(
                    f"session cap ${self.session_cap_usd:.2f}: spent ${self.session_spent:.4f}, "
                    f"in flight ${self._reserved:.4f}, this call up to ${usd:.4f}")
            self._reserved += usd
        try:
            yield
        finally:
            with self._lock:
                self._reserved -= usd

    def record(self, entry: dict) -> None:
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
        with self._lock:
            self.session_spent += float(entry.get("cost_usd", 0.0))
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
