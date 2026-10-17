"""Request and response shapes for the API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class LocationIn(BaseModel):
    name: str = Field(min_length=1)


class Location(LocationIn):
    id: int


class ItemIn(BaseModel):
    name: str = Field(min_length=1)
    unit: str = "each"
    min_level: float | None = Field(default=None, ge=0)
    max_level: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_levels(self):
        if self.min_level is not None and self.max_level is not None:
            if self.min_level > self.max_level:
                raise ValueError("min_level cannot be above max_level")
        return self


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    unit: str | None = None
    min_level: float | None = Field(default=None, ge=0)
    max_level: float | None = Field(default=None, ge=0)


class Item(ItemIn):
    id: int
    created_at: datetime


class ObservationIn(BaseModel):
    item_id: int
    # Omitted means the default location; an explicit null means the location is unknown.
    location_id: int | None = None
    quantity: float = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source: str = "manual"
    observed_at: datetime | None = None


class Observation(BaseModel):
    id: int
    item_id: int
    location_id: int | None
    quantity: float
    confidence: float | None
    source: str
    observed_at: datetime


class EventIn(BaseModel):
    item_id: int
    location_id: int | None = None
    kind: Literal["purchase", "use"]
    quantity: float = Field(gt=0)
    source: str = "manual"
    occurred_at: datetime | None = None


class Event(BaseModel):
    id: int
    item_id: int
    location_id: int | None
    kind: Literal["purchase", "use"]
    quantity: float
    source: str
    occurred_at: datetime


class LocationReading(BaseModel):
    location_id: int
    quantity: float
    observed_at: datetime


class StockReadings(BaseModel):
    """Latest reading per known location. Step 3 replaces this with the full estimate."""

    item_id: int
    locations: list[LocationReading]
    total: float
