"""SQLite-backed command journal for deterministic engine recovery."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any


class SQLiteJournal:
    """Stores accepted submissions and successful cancellations in command order.

    The engine is rebuilt by replaying these commands at startup. This preserves
    order IDs, sequence priority, fills, trades, and active book state.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS command_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL CHECK(action IN ('submit', 'cancel')),
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def append(self, action: str, payload: dict[str, Any]) -> None:
        if action not in {"submit", "cancel"}:
            raise ValueError(f"Unsupported journal action: {action}")
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO command_log(action, payload) VALUES (?, ?)",
                (action, encoded),
            )

    def actions(self) -> list[tuple[str, dict[str, Any]]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT action, payload FROM command_log ORDER BY id ASC"
            ).fetchall()
        return [(row["action"], json.loads(row["payload"])) for row in rows]

    def replay(self, engine: Any) -> int:
        """Replay the journal into a fresh MatchingEngine; returns command count."""
        commands = self.actions()
        for action, payload in commands:
            if action == "submit":
                engine.submit(
                    symbol=payload["symbol"],
                    side=payload["side"],
                    price=payload["price"],
                    quantity=payload["quantity"],
                    order_id=payload["order_id"],
                )
            elif action == "cancel":
                # Historical cancellations should always replay against a valid order.
                result = engine.cancel(payload["order_id"])
                if not result.ok:
                    raise RuntimeError(
                        f"Could not replay cancellation for {payload['order_id']}: {result.message}"
                    )
        engine.check_invariants()
        return len(commands)

    def close(self) -> None:
        # Connections are short-lived per operation, so nothing persistent to close.
        return None
