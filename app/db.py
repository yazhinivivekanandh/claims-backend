import json
import sqlite3
from datetime import datetime, timezone

from .config import DATABASE_PATH

_conn = None


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    name TEXT,
    admission_id TEXT,
    admission_date TEXT,
    discharge_date TEXT,
    room_category TEXT,
    insurer TEXT,
    policy_number TEXT,
    status TEXT,
    pending_confirmation TEXT
);
CREATE TABLE IF NOT EXISTS policies (
    policy_number TEXT PRIMARY KEY,
    patient_id TEXT,
    insurer TEXT,
    active_from TEXT,
    active_to TEXT,
    approved_limit REAL,
    approved_stay_days INTEGER,
    status TEXT
);
CREATE TABLE IF NOT EXISTS emr_notes (
    note_id TEXT PRIMARY KEY,
    patient_id TEXT,
    note_date TEXT,
    source TEXT,
    section TEXT,
    is_clinical INTEGER,
    text TEXT
);
CREATE TABLE IF NOT EXISTS allergies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT,
    allergen TEXT,
    severity TEXT,
    recorded_date TEXT,
    source_note_id TEXT
);
CREATE TABLE IF NOT EXISTS ledger_entries (
    entry_id TEXT PRIMARY KEY,
    patient_id TEXT,
    entry_date TEXT,
    description TEXT,
    amount REAL,
    is_credit INTEGER,
    status TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    patient_id TEXT,
    order_date TEXT,
    item TEXT,
    charge_entry_id TEXT,
    status TEXT
);
CREATE TABLE IF NOT EXISTS floor_clerk_exceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT,
    order_id TEXT,
    reason TEXT,
    status TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS state_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id TEXT UNIQUE,
    current_state TEXT,
    next_state TEXT,
    blocking INTEGER DEFAULT 0,
    transition_event TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS audit_trails (
    audit_id TEXT PRIMARY KEY,
    patient_id TEXT,
    action TEXT,
    source_ids TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS registry (
    patient_id TEXT PRIMARY KEY,
    datasets TEXT,
    indexed_records TEXT,
    missing_join_keys TEXT,
    registered_at TEXT
);
CREATE TABLE IF NOT EXISTS insurer_checklists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    insurer TEXT,
    checklist_version TEXT,
    code TEXT,
    description TEXT
);
CREATE TABLE IF NOT EXISTS claims (
    claim_id TEXT PRIMARY KEY,
    patient_id TEXT,
    bundle_id TEXT,
    amount REAL,
    status TEXT,
    receipt TEXT,
    payer_response_deadline TEXT,
    submitted_at TEXT
);
CREATE TABLE IF NOT EXISTS nhcx_queries (
    query_id TEXT PRIMARY KEY,
    patient_id TEXT,
    claim_id TEXT,
    text TEXT,
    classification TEXT,
    status TEXT,
    source_ids TEXT,
    response TEXT,
    receipt TEXT,
    received_at TEXT,
    transmitted_at TEXT
);
CREATE TABLE IF NOT EXISTS summaries (
    patient_id TEXT PRIMARY KEY,
    draft_sections TEXT,
    status TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS extensions (
    extension_id TEXT PRIMARY KEY,
    patient_id TEXT,
    evidence TEXT,
    status TEXT,
    created_at TEXT
);
"""


def init_db() -> None:
    get_conn().executescript(SCHEMA)
    get_conn().commit()


def rows(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    cur = get_conn().execute(sql, params)
    return cur.fetchall()


def one(sql: str, params: tuple = ()):
    cur = get_conn().execute(sql, params)
    return cur.fetchone()


def write(sql: str, params: tuple = ()) -> int:
    cur = get_conn().execute(sql, params)
    get_conn().commit()
    return cur.lastrowid


def write_many(sql: str, params_list: list[tuple]) -> None:
    get_conn().executemany(sql, params_list)
    get_conn().commit()


def next_sequence(table: str, column: str, prefix: str) -> int:
    row = one(
        f"SELECT {column} FROM {table} ORDER BY {column} DESC LIMIT 1",
    )
    if row is None:
        return 1
    value = row[0]
    try:
        return int(str(value).replace(prefix, "")) + 1
    except ValueError:
        return 1


def json_dumps(value) -> str:
    return json.dumps(value, default=str)
