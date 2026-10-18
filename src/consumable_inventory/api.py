"""The public API: the catalog, observations in, events in, and stock out."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from consumable_inventory import db, estimator
from consumable_inventory.schemas import (
    Event,
    EventIn,
    Item,
    ItemIn,
    ItemUpdate,
    ListLine,
    Location,
    LocationIn,
    LocationReading,
    Observation,
    ObservationIn,
    ShoppingList,
    Stock,
)

router = APIRouter()


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = db.connect(request.app.state.db_path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


Conn = Depends(get_conn)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def iso(value: datetime | None) -> str:
    if value is None:
        return now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def get_item_row(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"item {item_id} not found")
    return row


def resolve_location(conn: sqlite3.Connection, body: BaseModel) -> int | None:
    """Omitted location means the default one; an explicit null means unknown."""
    if "location_id" not in body.model_fields_set:
        row = conn.execute("SELECT id FROM locations WHERE name = ?", (db.DEFAULT_LOCATION,))
        return row.fetchone()["id"]
    location_id = body.location_id
    if location_id is not None:
        exists = conn.execute("SELECT 1 FROM locations WHERE id = ?", (location_id,)).fetchone()
        if exists is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"location {location_id} not found")
    return location_id


def check_levels(min_level: float | None, max_level: float | None) -> None:
    if min_level is not None and max_level is not None and min_level > max_level:
        raise HTTPException(422, "min_level cannot be above max_level")


# Locations


@router.get("/locations", response_model=list[Location])
def list_locations(conn: sqlite3.Connection = Conn):
    return [dict(r) for r in conn.execute("SELECT * FROM locations ORDER BY id")]


@router.post("/locations", response_model=Location, status_code=status.HTTP_201_CREATED)
def create_location(body: LocationIn, conn: sqlite3.Connection = Conn):
    try:
        cur = conn.execute("INSERT INTO locations (name) VALUES (?)", (body.name,))
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, f"location {body.name!r} exists") from None
    return {"id": cur.lastrowid, "name": body.name}


# Items


@router.get("/items", response_model=list[Item])
def list_items(conn: sqlite3.Connection = Conn):
    return [dict(r) for r in conn.execute("SELECT * FROM items ORDER BY name")]


@router.post("/items", response_model=Item, status_code=status.HTTP_201_CREATED)
def create_item(body: ItemIn, conn: sqlite3.Connection = Conn):
    try:
        cur = conn.execute(
            "INSERT INTO items (name, unit, min_level, max_level, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (body.name, body.unit, body.min_level, body.max_level, now()),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, f"item {body.name!r} exists") from None
    return dict(get_item_row(conn, cur.lastrowid))


@router.get("/items/{item_id}", response_model=Item)
def get_item(item_id: int, conn: sqlite3.Connection = Conn):
    return dict(get_item_row(conn, item_id))


@router.patch("/items/{item_id}", response_model=Item)
def update_item(item_id: int, body: ItemUpdate, conn: sqlite3.Connection = Conn):
    current = dict(get_item_row(conn, item_id))
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        raise HTTPException(422, "name cannot be null")
    merged = {**current, **changes}
    check_levels(merged["min_level"], merged["max_level"])
    try:
        conn.execute(
            "UPDATE items SET name = ?, unit = ?, min_level = ?, max_level = ? WHERE id = ?",
            (merged["name"], merged["unit"], merged["min_level"], merged["max_level"], item_id),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, f"item {merged['name']!r} exists") from None
    return dict(get_item_row(conn, item_id))


# Observations: sensor readings that replace the estimate.


@router.post("/observations", response_model=Observation, status_code=status.HTTP_201_CREATED)
def create_observation(body: ObservationIn, conn: sqlite3.Connection = Conn):
    get_item_row(conn, body.item_id)
    location_id = resolve_location(conn, body)
    observed_at = iso(body.observed_at)
    cur = conn.execute(
        "INSERT INTO observations"
        " (item_id, location_id, quantity, confidence, source, observed_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (body.item_id, location_id, body.quantity, body.confidence, body.source, observed_at),
    )
    row = conn.execute("SELECT * FROM observations WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.get("/observations", response_model=list[Observation])
def list_observations(item_id: int | None = None, conn: sqlite3.Connection = Conn):
    if item_id is None:
        rows = conn.execute("SELECT * FROM observations ORDER BY observed_at DESC, id DESC")
    else:
        rows = conn.execute(
            "SELECT * FROM observations WHERE item_id = ? ORDER BY observed_at DESC, id DESC",
            (item_id,),
        )
    return [dict(r) for r in rows]


# Events: purchases and usage that change stock.


@router.post("/events", response_model=Event, status_code=status.HTTP_201_CREATED)
def create_event(body: EventIn, conn: sqlite3.Connection = Conn):
    get_item_row(conn, body.item_id)
    location_id = resolve_location(conn, body)
    cur = conn.execute(
        "INSERT INTO events (item_id, location_id, kind, quantity, source, occurred_at)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (body.item_id, location_id, body.kind, body.quantity, body.source, iso(body.occurred_at)),
    )
    return dict(conn.execute("SELECT * FROM events WHERE id = ?", (cur.lastrowid,)).fetchone())


@router.get("/events", response_model=list[Event])
def list_events(item_id: int | None = None, conn: sqlite3.Connection = Conn):
    if item_id is None:
        rows = conn.execute("SELECT * FROM events ORDER BY occurred_at DESC, id DESC")
    else:
        rows = conn.execute(
            "SELECT * FROM events WHERE item_id = ? ORDER BY occurred_at DESC, id DESC",
            (item_id,),
        )
    return [dict(r) for r in rows]


# Stock and the shopping list


def item_history(
    conn: sqlite3.Connection, item_id: int
) -> tuple[list[estimator.Reading], list[estimator.Change]]:
    readings = [
        estimator.Reading(r["location_id"], r["quantity"], datetime.fromisoformat(r["observed_at"]))
        for r in conn.execute(
            "SELECT location_id, quantity, observed_at FROM observations"
            " WHERE item_id = ? ORDER BY observed_at, id",
            (item_id,),
        )
    ]
    changes = [
        estimator.Change(r["kind"], r["quantity"], datetime.fromisoformat(r["occurred_at"]))
        for r in conn.execute(
            "SELECT kind, quantity, occurred_at FROM events"
            " WHERE item_id = ? ORDER BY occurred_at, id",
            (item_id,),
        )
    ]
    return readings, changes


def as_utc(value: datetime | None) -> datetime:
    return datetime.fromisoformat(iso(value))


@router.get("/items/{item_id}/stock", response_model=Stock)
def get_stock(item_id: int, as_of: datetime | None = None, conn: sqlite3.Connection = Conn):
    get_item_row(conn, item_id)
    now_at = as_utc(as_of)
    est = estimator.estimate(*item_history(conn, item_id), now=now_at)
    return Stock(
        item_id=item_id,
        as_of=now_at,
        on_hand=est.on_hand,
        usage_per_day=est.usage_per_day,
        last_reading_at=est.last_reading_at,
        locations=[
            LocationReading(location_id=loc, quantity=r.quantity, observed_at=r.at)
            for loc, r in est.locations.items()
        ],
    )


@router.get("/list", response_model=ShoppingList)
def get_list(
    next_shop: datetime | None = None,
    as_of: datetime | None = None,
    conn: sqlite3.Connection = Conn,
):
    """What to buy so everything lasts past the next shopping date (default: a week from now)."""
    now_at = as_utc(as_of)
    shop_at = as_utc(next_shop) if next_shop is not None else now_at + timedelta(days=7)
    if shop_at < now_at:
        raise HTTPException(422, "next_shop cannot be before as_of")
    lines = []
    for item in conn.execute("SELECT * FROM items ORDER BY name").fetchall():
        est = estimator.estimate(*item_history(conn, item["id"]), now=now_at)
        line = estimator.list_line(est, item["min_level"], item["max_level"], now_at, shop_at)
        if line is not None:
            lines.append(
                ListLine(
                    item_id=item["id"],
                    name=item["name"],
                    unit=item["unit"],
                    quantity=line.quantity,
                    on_hand=line.on_hand,
                    expected_at_shop=line.expected_at_shop,
                    reason=line.reason,
                )
            )
    return ShoppingList(as_of=now_at, next_shop=shop_at, lines=lines)
