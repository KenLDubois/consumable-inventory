"""Stock estimation and list building. Plain code, no AI, so the list stays predictable.

The rules, agreed in the design docs:

- A reading measures stock; it replaces the previous reading at its location, never adds to it.
- Different locations add up.
- Purchases add to stock and usage events subtract from it, from the latest reading onward.
- A reading with no known location is only a lower bound: it can raise the estimate, never lower it.
- Usage rate comes from timestamps, so readings can arrive weekly or several times a day.
- The list never buys past an item's maximum.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime

SECONDS_PER_DAY = 86_400


@dataclass(frozen=True)
class Reading:
    location_id: int | None  # None: location unknown, so the reading is only a lower bound
    quantity: float
    at: datetime


@dataclass(frozen=True)
class Change:
    kind: str  # "purchase" or "use"
    quantity: float
    at: datetime

    @property
    def delta(self) -> float:
        return self.quantity if self.kind == "purchase" else -self.quantity


@dataclass(frozen=True)
class Estimate:
    on_hand: float | None  # None until there is at least one reading
    usage_per_day: float | None  # None until there is enough history to learn it
    locations: dict[int, Reading] = field(default_factory=dict)  # latest reading per location
    last_reading_at: datetime | None = None


@dataclass(frozen=True)
class ListLine:
    quantity: int
    on_hand: float
    expected_at_shop: float
    reason: str


def container_quantity(unopened: int, opened: int) -> float:
    """Count containers from a photo: an opened one counts as half until usage history says more."""
    return unopened + 0.5 * opened


def days_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / SECONDS_PER_DAY


def _snapshots(readings: list[Reading]) -> list[tuple[datetime, float]]:
    """Total stock across known locations after each known-location reading, oldest first."""
    latest: dict[int, float] = {}
    snapshots: list[tuple[datetime, float]] = []
    for r in sorted((r for r in readings if r.location_id is not None), key=lambda r: r.at):
        latest[r.location_id] = r.quantity
        total = sum(latest.values())
        if snapshots and snapshots[-1][0] == r.at:
            snapshots[-1] = (r.at, total)
        else:
            snapshots.append((r.at, total))
    return snapshots


def usage_rate(readings: list[Reading], changes: list[Change]) -> float | None:
    """Average units used per day between readings, counting purchases in between.

    Returns None until two readings at least a few hours apart exist.
    """
    snapshots = _snapshots(readings)
    used = 0.0
    elapsed = 0.0
    for (start, before), (end, after) in zip(snapshots, snapshots[1:], strict=False):
        # Usage events are already reflected in the next reading; only purchases are added back.
        bought = sum(c.quantity for c in changes if c.kind == "purchase" and start < c.at <= end)
        used += max(0.0, before + bought - after)
        elapsed += days_between(start, end)
    if elapsed < 0.125:  # three hours: too short to say anything about a rate
        return None
    return used / elapsed


def estimate(readings: list[Reading], changes: list[Change], now: datetime) -> Estimate:
    readings = [r for r in readings if r.at <= now]
    changes = [c for c in changes if c.at <= now]
    rate = usage_rate(readings, changes)

    latest: dict[int, Reading] = {}
    for r in readings:
        if r.location_id is None:
            continue
        current = latest.get(r.location_id)
        if current is None or r.at >= current.at:
            latest[r.location_id] = r

    on_hand: float | None = None
    last_at: datetime | None = None
    if latest:
        last_at = max(r.at for r in latest.values())
        anchor = sum(r.quantity for r in latest.values())
        anchor += sum(c.delta for c in changes if c.at > last_at)
        on_hand = anchor - (rate or 0.0) * days_between(last_at, now)

    # A reading with no location says "at least this many", decayed by usage since it was taken.
    floors = [r for r in readings if r.location_id is None and (last_at is None or r.at > last_at)]
    for r in floors:
        floor = r.quantity + sum(c.delta for c in changes if c.at > r.at)
        floor -= (rate or 0.0) * days_between(r.at, now)
        on_hand = floor if on_hand is None else max(on_hand, floor)

    return Estimate(
        on_hand=None if on_hand is None else max(0.0, on_hand),
        usage_per_day=rate,
        locations=dict(sorted(latest.items())),
        last_reading_at=last_at,
    )


def list_line(
    est: Estimate,
    min_level: float | None,
    max_level: float | None,
    now: datetime,
    next_shop: datetime,
) -> ListLine | None:
    """What to buy for one item so it lasts until the shop after next_shop. None: don't buy."""
    if min_level is None or est.on_hand is None:
        return None
    expected = max(0.0, est.on_hand - (est.usage_per_day or 0.0) * days_between(now, next_shop))
    if expected >= min_level:
        return None
    target = max_level if max_level is not None else min_level
    quantity = math.floor(target - expected)
    if max_level is None:
        quantity = max(quantity, 1)
    if quantity < 1:
        return None
    shown = round(expected, 2)
    reason = (
        f"expected {shown:g} by the shopping date, below the minimum of {min_level:g}"
        if expected < est.on_hand
        else f"{shown:g} on hand, below the minimum of {min_level:g}"
    )
    return ListLine(
        quantity=quantity, on_hand=est.on_hand, expected_at_shop=expected, reason=reason
    )
