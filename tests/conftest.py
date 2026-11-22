from datetime import datetime, timedelta, timezone

import pytest

from space_booking_mcp.auth import DEMO_USERS, StaticUserAuth
from space_booking_mcp.backends.in_memory import corporate_backend, residential_backend
from space_booking_mcp.server import build_server, default_router

# Monday 23 Nov 2026, 09:00 in Dublin (GMT in November, so the same as UTC).
START_OF_TEST_TIME = datetime(2026, 11, 23, 9, 0, tzinfo=timezone.utc)


class MutableClock:
    def __init__(self, now: datetime = START_OF_TEST_TIME):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock():
    return MutableClock()


@pytest.fixture
def corp(clock):
    return corporate_backend(clock)


@pytest.fixture
def res(clock):
    return residential_backend(clock)


@pytest.fixture
def dana():
    return DEMO_USERS["u-corp-1"]


@pytest.fixture
def eli():
    return DEMO_USERS["u-corp-2"]


@pytest.fixture
def robin():
    return DEMO_USERS["u-res-1"]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def make_server(clock):
    def _make(user_id: str):
        return build_server(default_router(clock), StaticUserAuth.from_id(user_id))

    return _make


def at(day: int, hour: int, minute: int = 0) -> datetime:
    """A time in November 2026 (UTC offset +00:00, same as Dublin in winter)."""
    return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc)
