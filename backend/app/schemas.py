from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ItemType = Literal["flight", "hotel", "reservation", "activity", "transit", "note"]


class TripIn(BaseModel):
    name: str = Field(min_length=1)
    destinations: list[str] = Field(min_length=1)
    start_date: date
    end_date: date
    timezone: str = "UTC"

    @model_validator(mode="after")
    def _dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class ItemIn(BaseModel):
    type: ItemType
    title: str = Field(min_length=1)
    start_at: datetime
    end_at: datetime | None = None
    location: str | None = None
    notes: str | None = None
    document_id: str | None = None
    source: Literal["user", "agent"] = "user"

    @model_validator(mode="after")
    def _order(self):
        if self.end_at and self.end_at < self.start_at:
            raise ValueError("end_at must not be before start_at")
        return self


class ItemPatch(BaseModel):
    type: ItemType | None = None
    title: str | None = Field(default=None, min_length=1)
    start_at: datetime | None = None
    end_at: datetime | None = None
    location: str | None = None
    notes: str | None = None
