"""SQLite storage. One file in the data directory, schema created on startup."""

import sqlite3
from pathlib import Path

DEFAULT_LOCATION = "home"

SCHEMA = """
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    unit TEXT NOT NULL DEFAULT 'each',
    min_level REAL,
    max_level REAL,
    created_at TEXT NOT NULL
);

-- A sensor reading: a fresh look at stock that replaces the estimate, never adds to it.
-- location_id NULL means the reading's location is unknown, so it is only a lower bound.
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    location_id INTEGER REFERENCES locations(id),
    quantity REAL NOT NULL,
    confidence REAL,
    source TEXT NOT NULL,
    observed_at TEXT NOT NULL
);

-- Something that changes stock: buying adds to it, using subtracts.
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    location_id INTEGER REFERENCES locations(id),
    kind TEXT NOT NULL CHECK (kind IN ('purchase', 'use')),
    quantity REAL NOT NULL,
    source TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS observations_item ON observations(item_id, observed_at);
CREATE INDEX IF NOT EXISTS events_item ON events(item_id, occurred_at);
"""


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init(path: Path) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        conn.execute("INSERT OR IGNORE INTO locations (name) VALUES (?)", (DEFAULT_LOCATION,))
    conn.close()
