from __future__ import annotations

import threading
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from ..errors import BookingError
from ..models import Booking, BookingStatus, Profile, Rules, Space, TimeWindow, User
from .base import BookingBackend

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryBackend(BookingBackend):
    """A complete, thread-safe booking backend that keeps everything in memory.

    It exists so the server can be run and tested with no external system. The rules (opening hours,
    maximum duration, active-booking limit) come from ``Rules``, so two instances with different
    rules behave like two different products.
    """

    def __init__(
        self,
        profile: Profile,
        rules: Rules,
        spaces_by_tenant: Dict[str, List[Space]],
        clock: Clock = _utc_now,
    ):
        self.profile = profile
        self.rules = rules
        self._spaces = spaces_by_tenant
        self._clock = clock
        self._tz = ZoneInfo(rules.timezone)
        self._bookings: Dict[str, Booking] = {}
        self._owner: Dict[str, User] = {}  # booking id -> user who made it
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ helpers

    def _now(self) -> datetime:
        return self._clock().astimezone(self._tz)

    def _space(self, user: User, space_id: str) -> Space:
        # Unknown ids and other tenants' ids look identical, so existence never leaks across tenants.
        for space in self._spaces.get(user.tenant_id, []):
            if space.id == space_id:
                return space
        raise BookingError("not_found", f"No space with id '{space_id}'. Use list_spaces to see valid ids.")

    def _confirmed_for_space(self, user: User, space_id: str) -> List[Booking]:
        return [
            b
            for bid, b in self._bookings.items()
            if b.space_id == space_id
            and b.status == BookingStatus.CONFIRMED
            and self._owner[bid].tenant_id == user.tenant_id
        ]

    def _round_up(self, moment: datetime) -> datetime:
        step = self.rules.granularity_minutes
        moment = moment.replace(second=0, microsecond=0)
        remainder = moment.minute % step
        if remainder:
            moment += timedelta(minutes=step - remainder)
        return moment

    # ------------------------------------------------------------------ interface

    def list_spaces(self, user: User, kind: Optional[str] = None) -> List[Space]:
        spaces = self._spaces.get(user.tenant_id, [])
        return [s for s in spaces if kind is None or s.kind == kind]

    def availability(self, user: User, space_id: str, day: date) -> List[TimeWindow]:
        self._space(user, space_id)
        now = self._now()
        if day < now.date():
            raise BookingError("invalid_time", "That date is in the past.")
        if day > now.date() + timedelta(days=self.rules.max_days_ahead):
            raise BookingError(
                "invalid_time", f"Bookings open at most {self.rules.max_days_ahead} days ahead."
            )

        open_dt = datetime.combine(day, time(self.rules.open_hour), tzinfo=self._tz)
        close_dt = datetime.combine(day, time(self.rules.close_hour), tzinfo=self._tz)
        cursor = max(open_dt, self._round_up(now))

        with self._lock:
            busy = sorted(
                (b.start, b.end)
                for b in self._confirmed_for_space(user, space_id)
                if b.end > open_dt and b.start < close_dt
            )

        free: List[TimeWindow] = []
        for busy_start, busy_end in busy:
            if busy_start > cursor:
                free.append(TimeWindow(start=cursor, end=min(busy_start, close_dt)))
            cursor = max(cursor, busy_end)
            if cursor >= close_dt:
                break
        if cursor < close_dt:
            free.append(TimeWindow(start=cursor, end=close_dt))
        return [w for w in free if w.end > w.start]

    def create_booking(self, user: User, space_id: str, start: datetime, end: datetime) -> Booking:
        space = self._space(user, space_id)
        rules = self.rules

        if start.tzinfo is None or end.tzinfo is None:
            raise BookingError(
                "invalid_time",
                "Times must include a UTC offset, for example 2026-11-24T10:00:00+00:00.",
            )
        start, end = start.astimezone(self._tz), end.astimezone(self._tz)
        now = self._now()

        if end <= start:
            raise BookingError("invalid_time", "The end time must be after the start time.")
        for label, moment in (("start", start), ("end", end)):
            if moment.second or moment.microsecond or moment.minute % rules.granularity_minutes:
                raise BookingError(
                    "invalid_time",
                    f"The {label} time must fall on a {rules.granularity_minutes}-minute boundary.",
                )
        if end - start > timedelta(minutes=rules.max_duration_minutes):
            raise BookingError(
                "limit_exceeded",
                f"Bookings can last at most {rules.max_duration_minutes} minutes for this account.",
            )
        if start < now:
            raise BookingError("invalid_time", "That start time is in the past.")
        if start.date() > now.date() + timedelta(days=rules.max_days_ahead):
            raise BookingError("invalid_time", f"Bookings open at most {rules.max_days_ahead} days ahead.")
        if start.date() != end.date():
            raise BookingError("invalid_time", "A booking must start and end on the same day.")
        if start.hour < rules.open_hour or end > datetime.combine(
            start.date(), time(rules.close_hour), tzinfo=self._tz
        ):
            raise BookingError(
                "invalid_time",
                f"Spaces can be booked between {rules.open_hour:02d}:00 and {rules.close_hour:02d}:00 "
                f"({rules.timezone}).",
            )

        with self._lock:
            active = [
                b
                for bid, b in self._bookings.items()
                if self._owner[bid].id == user.id and b.status == BookingStatus.CONFIRMED and b.end > now
            ]
            if len(active) >= rules.max_active_bookings:
                raise BookingError(
                    "limit_exceeded",
                    f"You already have {len(active)} active bookings (the limit is "
                    f"{rules.max_active_bookings}). Cancel one first.",
                )
            for other in self._confirmed_for_space(user, space_id):
                if start < other.end and other.start < end:  # half-open interval overlap
                    raise BookingError(
                        "conflict",
                        f"{space.name} is already booked from {other.start:%H:%M} to {other.end:%H:%M} "
                        "on that day. Use check_availability to find a free slot.",
                    )
            booking = Booking(
                id=uuid.uuid4().hex[:10],
                space_id=space.id,
                space_name=space.name,
                start=start,
                end=end,
                status=BookingStatus.CONFIRMED,
                created_at=now,
            )
            self._bookings[booking.id] = booking
            self._owner[booking.id] = user
            return booking

    def list_bookings(self, user: User, include_cancelled: bool = False) -> List[Booking]:
        with self._lock:
            mine = [
                b
                for bid, b in self._bookings.items()
                if self._owner[bid].id == user.id and (include_cancelled or b.status == BookingStatus.CONFIRMED)
            ]
        return sorted(mine, key=lambda b: b.start)

    def cancel_booking(self, user: User, booking_id: str) -> Booking:
        with self._lock:
            booking = self._bookings.get(booking_id)
            # Someone else's booking and a missing booking produce the same error.
            if booking is None or self._owner[booking_id].id != user.id:
                raise BookingError(
                    "not_found", f"No booking with id '{booking_id}' on your account. Use list_my_bookings."
                )
            if booking.status == BookingStatus.CANCELLED:
                return booking  # idempotent
            if booking.start <= self._now():
                raise BookingError("not_allowed", "A booking that has already started cannot be cancelled.")
            cancelled = booking.model_copy(update={"status": BookingStatus.CANCELLED})
            self._bookings[booking_id] = cancelled
            return cancelled


def corporate_backend(clock: Clock = _utc_now) -> InMemoryBackend:
    """Office-style rules: long bookings, desks and meeting rooms, weekdays-friendly hours."""
    spaces = {
        "acme-corp": [
            Space(id="room-atlas", name="Atlas meeting room", kind="meeting_room", capacity=8),
            Space(id="room-birch", name="Birch meeting room", kind="meeting_room", capacity=4),
            Space(id="desk-a1", name="Desk A1", kind="desk", capacity=1),
            Space(id="desk-a2", name="Desk A2", kind="desk", capacity=1),
        ]
    }
    rules = Rules(
        timezone="Europe/Dublin",
        open_hour=7,
        close_hour=20,
        max_duration_minutes=8 * 60,
        max_active_bookings=10,
    )
    return InMemoryBackend(Profile.CORPORATE, rules, spaces, clock)


def residential_backend(clock: Clock = _utc_now) -> InMemoryBackend:
    """Residential-style rules: shared amenities, short bookings, tight per-resident limit."""
    spaces = {
        "harbour-view": [
            Space(id="gym", name="Residents' gym", kind="gym", capacity=6),
            Space(id="bbq-terrace", name="BBQ terrace", kind="outdoor", capacity=12),
            Space(id="roof-lounge", name="Roof lounge", kind="lounge", capacity=20),
        ]
    }
    rules = Rules(
        timezone="Europe/Dublin",
        open_hour=8,
        close_hour=22,
        max_duration_minutes=2 * 60,
        max_active_bookings=2,
        max_days_ahead=14,
    )
    return InMemoryBackend(Profile.RESIDENTIAL, rules, spaces, clock)
