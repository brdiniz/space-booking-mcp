from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from typing import Iterator, List, Optional

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__
from .auth import AuthProvider
from .backends.in_memory import Clock, corporate_backend, residential_backend
from .errors import BookingError
from .models import Booking, Profile, Space, TimeWindow, WhoAmI
from .router import BackendRouter

INSTRUCTIONS = (
    "Book shared spaces (rooms, desks, amenities) for the signed-in user. "
    "Call whoami first to learn the booking rules that apply to this account. "
    "Use list_spaces to find a space id, check_availability to find free windows, then book_space. "
    "Times must be ISO 8601 with a UTC offset. Always confirm the space, date and time with the "
    "user before calling book_space or cancel_booking."
)


@contextmanager
def _domain_errors() -> Iterator[None]:
    """Turn domain errors into tool errors the model can read and act on."""
    try:
        yield
    except BookingError as exc:
        raise ToolError(str(exc)) from exc


def default_router(clock: Optional[Clock] = None) -> BackendRouter:
    kwargs = {"clock": clock} if clock else {}
    return BackendRouter(
        {
            Profile.CORPORATE: corporate_backend(**kwargs),
            Profile.RESIDENTIAL: residential_backend(**kwargs),
        }
    )


def build_server(router: BackendRouter, auth: AuthProvider) -> MCPServer:
    server = MCPServer("space-booking", version=__version__, instructions=INSTRUCTIONS)

    def ctx():
        user = auth.current_user()
        return user, router.for_user(user)

    @server.tool(
        title="Who am I",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def whoami() -> WhoAmI:
        """Return the signed-in user, their account type, and the booking rules that apply to them."""
        with _domain_errors():
            user, backend = ctx()
            return WhoAmI(user_id=user.id, name=user.name, profile=user.profile, rules=backend.rules)

    @server.tool(
        title="List spaces",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def list_spaces(kind: Optional[str] = None) -> List[Space]:
        """List the spaces the user can book. Optionally filter by kind, for example 'meeting_room' or 'gym'."""
        with _domain_errors():
            user, backend = ctx()
            return backend.list_spaces(user, kind)

    @server.tool(
        title="Check availability",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def check_availability(space_id: str, day: date) -> List[TimeWindow]:
        """List the free time windows for one space on one day (YYYY-MM-DD, in the space's local time)."""
        with _domain_errors():
            user, backend = ctx()
            return backend.availability(user, space_id, day)

    @server.tool(
        title="Book a space",
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
        ),
    )
    def book_space(space_id: str, start: datetime, end: datetime) -> Booking:
        """Book a space for the signed-in user. Times are ISO 8601 with a UTC offset, on the quarter hour.

        Confirm the details with the user first. Fails with a clear message if the slot is taken,
        outside opening hours, or over the account's limits.
        """
        with _domain_errors():
            user, backend = ctx()
            return backend.create_booking(user, space_id, start, end)

    @server.tool(
        title="List my bookings",
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
    )
    def list_my_bookings(include_cancelled: bool = False) -> List[Booking]:
        """List the signed-in user's bookings in time order. Cancelled bookings are hidden by default."""
        with _domain_errors():
            user, backend = ctx()
            return backend.list_bookings(user, include_cancelled)

    @server.tool(
        title="Cancel a booking",
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False
        ),
    )
    def cancel_booking(booking_id: str) -> Booking:
        """Cancel one of the signed-in user's own bookings. Confirm with the user first."""
        with _domain_errors():
            user, backend = ctx()
            return backend.cancel_booking(user, booking_id)

    return server
