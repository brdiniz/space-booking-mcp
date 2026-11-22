from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class Profile(str, Enum):
    """Which kind of booking system a user belongs to."""

    CORPORATE = "corporate"
    RESIDENTIAL = "residential"


class BookingStatus(str, Enum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class User(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    profile: Profile
    tenant_id: str


class Space(BaseModel):
    id: str
    name: str
    kind: str
    capacity: int


class Booking(BaseModel):
    id: str
    space_id: str
    space_name: str
    start: datetime
    end: datetime
    status: BookingStatus
    created_at: datetime


class TimeWindow(BaseModel):
    start: datetime
    end: datetime


class Rules(BaseModel):
    """Booking rules that differ between backends."""

    timezone: str
    open_hour: int
    close_hour: int
    max_duration_minutes: int
    max_active_bookings: int
    granularity_minutes: int = 15
    max_days_ahead: int = 30


class WhoAmI(BaseModel):
    user_id: str
    name: str
    profile: Profile
    rules: Rules
