from datetime import date, datetime

import pytest

from space_booking_mcp.errors import BookingError
from space_booking_mcp.models import BookingStatus, Profile, User

from conftest import at


def code(excinfo) -> str:
    return excinfo.value.code


# ---------------------------------------------------------------- availability


def test_today_starts_from_the_next_quarter_hour(corp, dana):
    windows = corp.availability(dana, "room-atlas", date(2026, 11, 23))
    assert len(windows) == 1
    assert (windows[0].start.hour, windows[0].start.minute) == (9, 0)
    assert windows[0].end.hour == 20


def test_future_day_uses_full_opening_hours(corp, dana):
    (window,) = corp.availability(dana, "room-atlas", date(2026, 11, 24))
    assert (window.start.hour, window.end.hour) == (7, 20)


def test_booking_splits_the_free_windows(corp, dana):
    corp.create_booking(dana, "room-atlas", at(24, 10), at(24, 11))
    windows = corp.availability(dana, "room-atlas", date(2026, 11, 24))
    assert [(w.start.hour, w.end.hour) for w in windows] == [(7, 10), (11, 20)]


def test_past_and_too_far_dates_are_rejected(corp, dana):
    with pytest.raises(BookingError) as past:
        corp.availability(dana, "room-atlas", date(2026, 11, 20))
    assert code(past) == "invalid_time"
    with pytest.raises(BookingError) as far:
        corp.availability(dana, "room-atlas", date(2027, 3, 1))
    assert code(far) == "invalid_time"


# ---------------------------------------------------------------- creating bookings


def test_create_booking_succeeds(corp, dana):
    booking = corp.create_booking(dana, "room-atlas", at(24, 10), at(24, 11))
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.space_name == "Atlas meeting room"
    assert corp.list_bookings(dana) == [booking]


def test_overlap_is_a_conflict_but_adjacent_slots_are_fine(corp, dana, eli):
    corp.create_booking(dana, "room-atlas", at(24, 10), at(24, 11))
    with pytest.raises(BookingError) as clash:
        corp.create_booking(eli, "room-atlas", at(24, 10, 30), at(24, 11, 30))
    assert code(clash) == "conflict"
    # Back to back is allowed (half-open intervals).
    corp.create_booking(eli, "room-atlas", at(24, 11), at(24, 12))
    corp.create_booking(eli, "room-atlas", at(24, 9), at(24, 10))


def test_cancelling_frees_the_slot(corp, dana, eli):
    booking = corp.create_booking(dana, "room-atlas", at(24, 10), at(24, 11))
    corp.cancel_booking(dana, booking.id)
    corp.create_booking(eli, "room-atlas", at(24, 10), at(24, 11))


@pytest.mark.parametrize(
    "start,end",
    [
        (at(24, 10, 10), at(24, 11)),  # not on the quarter hour
        (at(24, 10), at(24, 10)),  # zero length
        (at(24, 11), at(24, 10)),  # end before start
        (at(24, 6), at(24, 7)),  # before opening
        (at(24, 19), at(24, 20, 15)),  # after closing
        (at(23, 8), at(23, 9)),  # in the past (clock is 09:00 on the 23rd)
        (at(24, 23), at(25, 1)),  # spans midnight
    ],
)
def test_invalid_times_are_rejected(corp, dana, start, end):
    with pytest.raises(BookingError) as err:
        corp.create_booking(dana, "room-atlas", start, end)
    assert code(err) == "invalid_time"


def test_naive_datetimes_are_rejected(corp, dana):
    with pytest.raises(BookingError) as err:
        corp.create_booking(dana, "room-atlas", datetime(2026, 11, 24, 10), datetime(2026, 11, 24, 11))
    assert code(err) == "invalid_time"
    assert "UTC offset" in err.value.message


def test_booking_too_far_ahead_is_rejected(res, robin):
    with pytest.raises(BookingError) as err:
        res.create_booking(robin, "gym", datetime(2026, 12, 20, 10, tzinfo=at(1, 0).tzinfo), datetime(2026, 12, 20, 11, tzinfo=at(1, 0).tzinfo))
    assert code(err) == "invalid_time"


# ---------------------------------------------------------------- rules differ by backend


def test_corporate_allows_a_long_booking_residential_does_not(corp, res, dana, robin):
    corp.create_booking(dana, "desk-a1", at(24, 8), at(24, 16))  # 8 hours: allowed
    with pytest.raises(BookingError) as err:
        res.create_booking(robin, "gym", at(24, 9), at(24, 12))  # 3 hours: over the 2-hour limit
    assert code(err) == "limit_exceeded"


def test_residential_active_booking_limit(res, robin):
    res.create_booking(robin, "gym", at(24, 9), at(24, 10))
    res.create_booking(robin, "gym", at(25, 9), at(25, 10))
    with pytest.raises(BookingError) as err:
        res.create_booking(robin, "gym", at(26, 9), at(26, 10))
    assert code(err) == "limit_exceeded"


# ---------------------------------------------------------------- cancelling


def test_cannot_cancel_someone_elses_booking(corp, dana, eli):
    booking = corp.create_booking(dana, "room-atlas", at(24, 10), at(24, 11))
    with pytest.raises(BookingError) as err:
        corp.cancel_booking(eli, booking.id)
    assert code(err) == "not_found"  # the same answer as for a booking that does not exist
    assert corp.list_bookings(dana)[0].status == BookingStatus.CONFIRMED


def test_cancel_is_idempotent(corp, dana):
    booking = corp.create_booking(dana, "room-atlas", at(24, 10), at(24, 11))
    first = corp.cancel_booking(dana, booking.id)
    second = corp.cancel_booking(dana, booking.id)
    assert first.status == second.status == BookingStatus.CANCELLED
    assert corp.list_bookings(dana) == []
    assert len(corp.list_bookings(dana, include_cancelled=True)) == 1


def test_cannot_cancel_a_started_booking(corp, dana, clock):
    booking = corp.create_booking(dana, "room-atlas", at(23, 10), at(23, 11))
    clock.advance(hours=1, minutes=30)  # now 10:30
    with pytest.raises(BookingError) as err:
        corp.cancel_booking(dana, booking.id)
    assert code(err) == "not_allowed"


# ---------------------------------------------------------------- tenant isolation


def test_other_tenants_cannot_see_or_book_spaces(corp):
    outsider = User(id="u-x", name="Outsider", profile=Profile.CORPORATE, tenant_id="other-tenant")
    assert corp.list_spaces(outsider) == []
    with pytest.raises(BookingError) as err:
        corp.create_booking(outsider, "room-atlas", at(24, 10), at(24, 11))
    assert code(err) == "not_found"


def test_bookings_are_private_to_their_owner(corp, dana, eli):
    corp.create_booking(dana, "room-atlas", at(24, 10), at(24, 11))
    assert corp.list_bookings(eli) == []


def test_list_spaces_filters_by_kind(corp, dana):
    rooms = corp.list_spaces(dana, "meeting_room")
    assert {s.id for s in rooms} == {"room-atlas", "room-birch"}
