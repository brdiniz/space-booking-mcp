from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import List, Optional

from ..models import Booking, Profile, Rules, Space, TimeWindow, User


class BookingBackend(ABC):
    """The contract every booking system adapter implements.

    A real adapter would call your booking API here. The MCP layer depends only on this
    interface, so adding a new system means adding a class, not touching the tools.

    Every method receives the acting user. Implementations must enforce tenant isolation and
    ownership themselves; the MCP layer is not a security boundary.
    """

    profile: Profile
    rules: Rules

    @abstractmethod
    def list_spaces(self, user: User, kind: Optional[str] = None) -> List[Space]: ...

    @abstractmethod
    def availability(self, user: User, space_id: str, day: date) -> List[TimeWindow]: ...

    @abstractmethod
    def create_booking(self, user: User, space_id: str, start: datetime, end: datetime) -> Booking: ...

    @abstractmethod
    def list_bookings(self, user: User, include_cancelled: bool = False) -> List[Booking]: ...

    @abstractmethod
    def cancel_booking(self, user: User, booking_id: str) -> Booking: ...
