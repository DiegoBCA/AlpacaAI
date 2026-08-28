"""
SILVERCAWN — SQLite Database Layer.

Async database operations using aiosqlite. Manages schema creation and
CRUD operations for aggressiveness logs, recommendations, orders,
risk gate events, and P&L snapshots.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------
_SCHEMA = """
-- Aggressiveness change history
CREATE TABLE IF NOT EXISTS aggressiveness_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    value INTEGER NOT NULL,
    zone TEXT NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Agent recommendations
CREATE TABLE IF NOT EXISTS recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,
    symbol TEXT,
    strategy TEXT,
    action TEXT,
    llm_reasoning TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

-- Orders sent to Alpaca via MCP
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id INTEGER REFERENCES recommendations(id),
    alpaca_order_id TEXT,
    symbol TEXT,
    side TEXT,
    qty REAL,
    order_type TEXT,
    status TEXT,
    raw_response TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Risk gate trigger events
CREATE TABLE IF NOT EXISTS risk_gate_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id INTEGER,
    gate_name TEXT NOT NULL,
    proposed_action TEXT,
    reason TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Periodic P&L snapshots
CREATE TABLE IF NOT EXISTS pnl_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equity REAL,
    cash REAL,
    buying_power REAL,
    pnl_total REAL,
    pnl_today REAL,
    snapshot_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class Database:
    """Async SQLite database wrapper for SILVERCAWN."""

    def __init__(self, db_path: str = "silvercawn.db"):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self):
        """Open the database connection and create tables if needed."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()
        logger.info("Database connected: %s", self.db_path)

    async def close(self):
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("Database closed.")

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db

    # -------------------------------------------------------------------
    # Aggressiveness Log
    # -------------------------------------------------------------------

    async def log_aggressiveness(self, value: int, zone: str) -> int:
        """Record an aggressiveness change. Returns the new row id."""
        cursor = await self.db.execute(
            "INSERT INTO aggressiveness_log (value, zone) VALUES (?, ?)",
            (value, zone),
        )
        await self.db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def get_current_aggressiveness(self) -> dict | None:
        """Get the most recent aggressiveness setting."""
        cursor = await self.db.execute(
            "SELECT * FROM aggressiveness_log ORDER BY id DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    # -------------------------------------------------------------------
    # Recommendations
    # -------------------------------------------------------------------

    async def create_recommendation(
        self,
        mode: str,
        symbol: str | None,
        strategy: str | None,
        action: str | None,
        llm_reasoning: str | None,
    ) -> int:
        """Insert a new recommendation with status='pending'. Returns row id."""
        cursor = await self.db.execute(
            """INSERT INTO recommendations (mode, symbol, strategy, action, llm_reasoning, status)
               VALUES (?, ?, ?, ?, ?, 'pending')""",
            (mode, symbol, strategy, action, llm_reasoning),
        )
        await self.db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def get_recommendation(self, rec_id: int) -> dict | None:
        """Get a single recommendation by id."""
        cursor = await self.db.execute(
            "SELECT * FROM recommendations WHERE id = ?", (rec_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_recommendations(self, status: str | None = None) -> list[dict]:
        """List recommendations, optionally filtered by status."""
        if status:
            cursor = await self.db.execute(
                "SELECT * FROM recommendations WHERE status = ? ORDER BY id DESC",
                (status,),
            )
        else:
            cursor = await self.db.execute(
                "SELECT * FROM recommendations ORDER BY id DESC"
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def update_recommendation_status(
        self, rec_id: int, status: str
    ) -> None:
        """Update the status of a recommendation."""
        now = datetime.now(timezone.utc).isoformat()
        await self.db.execute(
            "UPDATE recommendations SET status = ?, resolved_at = ? WHERE id = ?",
            (status, now, rec_id),
        )
        await self.db.commit()

    # -------------------------------------------------------------------
    # Orders
    # -------------------------------------------------------------------

    async def create_order(
        self,
        recommendation_id: int | None,
        alpaca_order_id: str | None,
        symbol: str | None,
        side: str | None,
        qty: float | None,
        order_type: str | None,
        status: str,
        raw_response: dict | str | None = None,
    ) -> int:
        """Insert an order record. Returns row id."""
        raw = json.dumps(raw_response) if isinstance(raw_response, dict) else raw_response
        cursor = await self.db.execute(
            """INSERT INTO orders
               (recommendation_id, alpaca_order_id, symbol, side, qty, order_type, status, raw_response)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (recommendation_id, alpaca_order_id, symbol, side, qty, order_type, status, raw),
        )
        await self.db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def list_orders(self, limit: int = 50) -> list[dict]:
        """List recent orders."""
        cursor = await self.db.execute(
            "SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------------------------
    # Risk Gate Events
    # -------------------------------------------------------------------

    async def log_risk_gate_event(
        self,
        recommendation_id: int | None,
        gate_name: str,
        proposed_action: str | None,
        reason: str,
    ) -> int:
        """Log a risk gate activation event."""
        cursor = await self.db.execute(
            """INSERT INTO risk_gate_events
               (recommendation_id, gate_name, proposed_action, reason)
               VALUES (?, ?, ?, ?)""",
            (recommendation_id, gate_name, proposed_action, reason),
        )
        await self.db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def list_risk_gate_events(self, limit: int = 50) -> list[dict]:
        """List recent risk gate events."""
        cursor = await self.db.execute(
            "SELECT * FROM risk_gate_events ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # -------------------------------------------------------------------
    # P&L Snapshots
    # -------------------------------------------------------------------

    async def create_pnl_snapshot(
        self,
        equity: float,
        cash: float,
        buying_power: float,
        pnl_total: float,
        pnl_today: float,
    ) -> int:
        """Record a P&L snapshot."""
        cursor = await self.db.execute(
            """INSERT INTO pnl_snapshots (equity, cash, buying_power, pnl_total, pnl_today)
               VALUES (?, ?, ?, ?, ?)""",
            (equity, cash, buying_power, pnl_total, pnl_today),
        )
        await self.db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def list_pnl_snapshots(self, limit: int = 100) -> list[dict]:
        """List recent P&L snapshots."""
        cursor = await self.db.execute(
            "SELECT * FROM pnl_snapshots ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
