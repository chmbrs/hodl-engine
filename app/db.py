import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


def _adapt_datetime_iso(value: datetime) -> str:
    return value.isoformat()


def _convert_timestamp(value: bytes) -> datetime:
    return datetime.fromisoformat(value.decode())


sqlite3.register_adapter(datetime, _adapt_datetime_iso)
sqlite3.register_converter("timestamp", _convert_timestamp)

DB_PATH = "../local_db/hodl.db"

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

TRADES_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS trades (
        id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        base_asset TEXT NOT NULL,
        quote_asset TEXT NOT NULL,
        account_type TEXT NOT NULL,
        side TEXT NOT NULL,
        price REAL NOT NULL,
        qty REAL NOT NULL,
        quote_qty REAL NOT NULL,
        quote_qty_usd REAL NOT NULL DEFAULT 0,
        commission REAL NOT NULL,
        commission_asset TEXT NOT NULL,
        trade_time TIMESTAMP NOT NULL,
        synced_at TIMESTAMP NOT NULL
    )
"""

BALANCES_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS balances (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset TEXT NOT NULL,
        account_type TEXT NOT NULL,
        free REAL NOT NULL,
        locked REAL NOT NULL,
        total REAL NOT NULL,
        updated_at TIMESTAMP NOT NULL,
        UNIQUE(asset, account_type)
    )
"""

PRICES_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS prices (
        symbol TEXT PRIMARY KEY,
        price REAL NOT NULL,
        updated_at TIMESTAMP NOT NULL
    )
"""

ASSET_GROUPS_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS asset_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_name TEXT NOT NULL UNIQUE,
        members_json TEXT NOT NULL
    )
"""

SYNC_LOG_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS sync_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sync_type TEXT NOT NULL,
        started_at TIMESTAMP NOT NULL,
        completed_at TIMESTAMP,
        status TEXT NOT NULL,
        details TEXT
    )
"""

CHATS_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        messages_json TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL,
        updated_at TIMESTAMP NOT NULL
    )
"""

COST_BASIS_OVERRIDES_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS cost_basis_overrides (
        asset TEXT PRIMARY KEY,
        avg_price_usd REAL NOT NULL,
        notes TEXT,
        source TEXT DEFAULT 'manual',
        created_at TIMESTAMP NOT NULL
    )
"""

ALLOCATION_TARGETS_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS allocation_targets (
        asset TEXT PRIMARY KEY,
        target_pct REAL NOT NULL,
        updated_at TIMESTAMP NOT NULL
    )
"""

ANALYSIS_SNAPSHOTS_TABLE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS analysis_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL
    )
"""

ALL_SCHEMAS = [
    TRADES_TABLE_SCHEMA,
    BALANCES_TABLE_SCHEMA,
    PRICES_TABLE_SCHEMA,
    ASSET_GROUPS_TABLE_SCHEMA,
    SYNC_LOG_TABLE_SCHEMA,
    CHATS_TABLE_SCHEMA,
    COST_BASIS_OVERRIDES_TABLE_SCHEMA,
    ALLOCATION_TARGETS_TABLE_SCHEMA,
    ANALYSIS_SNAPSHOTS_TABLE_SCHEMA,
]


@contextmanager
def managed_db_session():
    db = sqlite3.connect(
        DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
    )
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def init_db():
    with managed_db_session() as db:
        for schema in ALL_SCHEMAS:
            db.execute(schema)
        # Migrate: add quote_qty_usd if it doesn't exist
        cols = [row[1] for row in db.execute("PRAGMA table_info(trades)").fetchall()]
        if "quote_qty_usd" not in cols:
            db.execute("ALTER TABLE trades ADD COLUMN quote_qty_usd REAL NOT NULL DEFAULT 0")
        db.commit()


def seed_default_asset_groups():
    from config import DEFAULT_ASSET_GROUPS

    with managed_db_session() as db:
        for group_name, members in DEFAULT_ASSET_GROUPS.items():
            existing = db.execute(
                "SELECT id FROM asset_groups WHERE group_name = ?",
                (group_name,),
            ).fetchone()
            if not existing:
                db.execute(
                    "INSERT INTO asset_groups (group_name, members_json) VALUES (?, ?)",
                    (group_name, json.dumps(members)),
                )
        db.commit()
