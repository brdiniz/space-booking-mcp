from __future__ import annotations

from typing import Mapping

from .backends.base import BookingBackend
from .errors import BookingError
from .models import Profile, User


class BackendRouter:
    """Chooses the booking system for a user from their profile.

    This is the heart of the "one assistant, several booking systems" pattern: the model sees one
    set of tools, and the router decides where each call really goes.
    """

    def __init__(self, backends: Mapping[Profile, BookingBackend]):
        self._backends = dict(backends)

    def for_user(self, user: User) -> BookingBackend:
        backend = self._backends.get(user.profile)
        if backend is None:
            raise BookingError(
                "not_allowed", f"Bookings are not available for the '{user.profile.value}' account type yet."
            )
        return backend
