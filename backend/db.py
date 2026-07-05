from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import get_settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS app_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    tenant_id TEXT
);

CREATE TABLE IF NOT EXISTS xero_contacts (
    contact_id TEXT PRIMARY KEY,
    tenant_id TEXT,
    payload TEXT NOT NULL,
    synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS xero_invoices (
    invoice_id TEXT PRIMARY KEY,
    tenant_id TEXT,
    contact_id TEXT,
    status TEXT,
    invoice_number TEXT,
    payload TEXT NOT NULL,
    synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS xero_payments (
    payment_id TEXT PRIMARY KEY,
    tenant_id TEXT,
    invoice_id TEXT,
    payload TEXT NOT NULL,
    synced_at TEXT NOT NULL
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    settings = get_settings()
    db_path = path or settings.database_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate_xero_tenant_columns(conn)
    conn.commit()
    return conn


def _migrate_xero_tenant_columns(conn: sqlite3.Connection) -> None:
    for table in ("xero_contacts", "xero_invoices", "xero_payments"):
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "tenant_id" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN tenant_id TEXT")


def get_json(conn: sqlite3.Connection, key: str, default: Any) -> Any:
    row = conn.execute("SELECT value FROM app_state WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    return json.loads(row["value"])


def set_json(conn: sqlite3.Connection, key: str, value: Any) -> None:
    conn.execute(
        "INSERT INTO app_state(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )
    conn.commit()


def upsert_payload(conn: sqlite3.Connection, table: str, key_column: str, key: str, payload: dict, extra: dict[str, Any] | None = None) -> None:
    if table not in {"xero_contacts", "xero_invoices", "xero_payments"}:
        raise ValueError(f"unsupported table: {table}")

    extra = extra or {}
    synced_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    if table == "xero_contacts":
        conn.execute(
            "INSERT INTO xero_contacts(contact_id, tenant_id, payload, synced_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(contact_id) DO UPDATE SET tenant_id = excluded.tenant_id, "
            "payload = excluded.payload, synced_at = excluded.synced_at",
            (key, extra.get("tenant_id"), json.dumps(payload), synced_at),
        )
    elif table == "xero_invoices":
        conn.execute(
            "INSERT INTO xero_invoices(invoice_id, tenant_id, contact_id, status, invoice_number, payload, synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(invoice_id) DO UPDATE SET tenant_id = excluded.tenant_id, "
            "contact_id = excluded.contact_id, status = excluded.status, "
            "invoice_number = excluded.invoice_number, payload = excluded.payload, synced_at = excluded.synced_at",
            (
                key,
                extra.get("tenant_id"),
                extra.get("contact_id"),
                extra.get("status"),
                extra.get("invoice_number"),
                json.dumps(payload),
                synced_at,
            ),
        )
    else:
        conn.execute(
            "INSERT INTO xero_payments(payment_id, tenant_id, invoice_id, payload, synced_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(payment_id) DO UPDATE SET tenant_id = excluded.tenant_id, invoice_id = excluded.invoice_id, "
            "payload = excluded.payload, synced_at = excluded.synced_at",
            (key, extra.get("tenant_id"), extra.get("invoice_id"), json.dumps(payload), synced_at),
        )


def clear_xero_raw_snapshot(conn: sqlite3.Connection) -> None:
    for table in ("xero_contacts", "xero_invoices", "xero_payments"):
        conn.execute(f"DELETE FROM {table}")


def count_rows(conn: sqlite3.Connection, table: str, tenant_id: str | None = None) -> int:
    if table not in {"xero_contacts", "xero_invoices", "xero_payments"}:
        raise ValueError(f"unsupported table: {table}")
    if tenant_id is not None:
        return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table} WHERE tenant_id = ?", (tenant_id,)).fetchone()["count"])
    return int(conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"])
