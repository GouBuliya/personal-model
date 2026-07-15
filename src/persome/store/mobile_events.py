"""Durable idempotency receipts for paired mobile observations."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

RECEIPT_RETENTION_DAYS = 90
RECEIPT_LIMIT = 100_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS mobile_event_receipts (
    device_id   TEXT NOT NULL,
    event_id    TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    capture_id  TEXT NOT NULL,
    status      TEXT NOT NULL CHECK(status IN ('pending', 'accepted')),
    received_at TEXT NOT NULL,
    accepted_at TEXT,
    PRIMARY KEY(device_id, event_id)
);
CREATE INDEX IF NOT EXISTS ix_mobile_event_receipts_accepted
    ON mobile_event_receipts(status, accepted_at);
"""


@dataclass(frozen=True)
class MobileEventReceipt:
    device_id: str
    event_id: str
    payload_hash: str
    capture_id: str
    status: str
    received_at: str
    accepted_at: str | None


def ensure_schema(conn: sqlite3.Connection) -> None:
    from . import fts

    if fts.is_client_process():
        return
    conn.executescript(SCHEMA)


def get(conn: sqlite3.Connection, *, device_id: str, event_id: str) -> MobileEventReceipt | None:
    ensure_schema(conn)
    row = conn.execute(
        "SELECT device_id, event_id, payload_hash, capture_id, status, received_at, accepted_at "
        "FROM mobile_event_receipts WHERE device_id=? AND event_id=?",
        (device_id, event_id),
    ).fetchone()
    return MobileEventReceipt(*map(str_or_none, row)) if row else None


def claim(
    conn: sqlite3.Connection,
    *,
    device_id: str,
    event_id: str,
    payload_hash: str,
    capture_id: str,
    received_at: str,
) -> MobileEventReceipt:
    """Create a pending identity receipt, or return the existing identity."""
    ensure_schema(conn)
    conn.execute(
        "INSERT INTO mobile_event_receipts"
        " (device_id, event_id, payload_hash, capture_id, status, received_at)"
        " VALUES (?, ?, ?, ?, 'pending', ?)"
        " ON CONFLICT(device_id, event_id) DO NOTHING",
        (device_id, event_id, payload_hash, capture_id, received_at),
    )
    conn.commit()
    receipt = get(conn, device_id=device_id, event_id=event_id)
    if receipt is None:  # pragma: no cover - SQLite just accepted or found the row
        raise RuntimeError("mobile event receipt claim disappeared")
    return receipt


def accept(
    conn: sqlite3.Connection,
    *,
    device_id: str,
    event_id: str,
    payload_hash: str,
    accepted_at: str,
) -> bool:
    ensure_schema(conn)
    cursor = conn.execute(
        "UPDATE mobile_event_receipts SET status='accepted', accepted_at=? "
        "WHERE device_id=? AND event_id=? AND payload_hash=?",
        (accepted_at, device_id, event_id, payload_hash),
    )
    conn.commit()
    return cursor.rowcount == 1


def prune(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
    keep: int = RECEIPT_LIMIT,
) -> int:
    """Bound accepted receipts by both age and count; never drop in-flight rows."""
    ensure_schema(conn)
    cutoff = ((now or datetime.now(UTC)) - timedelta(days=RECEIPT_RETENTION_DAYS)).isoformat()
    cursor = conn.execute(
        "DELETE FROM mobile_event_receipts "
        "WHERE status='accepted' AND (accepted_at < ? OR rowid NOT IN "
        "(SELECT rowid FROM mobile_event_receipts WHERE status='accepted' "
        "ORDER BY accepted_at DESC LIMIT ?))",
        (cutoff, keep),
    )
    conn.commit()
    return cursor.rowcount


def str_or_none(value: object) -> str | None:
    return None if value is None else str(value)
