from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Protocol

from .errors import BookingError
from .models import Profile, User

DEMO_USERS: Dict[str, User] = {
    "u-corp-1": User(id="u-corp-1", name="Dana Corporate", profile=Profile.CORPORATE, tenant_id="acme-corp"),
    "u-corp-2": User(id="u-corp-2", name="Eli Corporate", profile=Profile.CORPORATE, tenant_id="acme-corp"),
    "u-res-1": User(id="u-res-1", name="Robin Resident", profile=Profile.RESIDENTIAL, tenant_id="harbour-view"),
}


class AuthProvider(Protocol):
    """Tells the server who is making the current request."""

    def current_user(self) -> User: ...


class StaticUserAuth:
    """Demo identity: one fixed user per server process, chosen at start-up.

    This fits the stdio transport, where the client launches one server process per person.
    A shared remote (HTTP) deployment needs per-request identity instead. Implement ``AuthProvider``
    so that ``current_user`` reads the user from a verified OAuth access token, and never from tool
    arguments. See docs/security.md.
    """

    def __init__(self, user: User):
        self._user = user

    def current_user(self) -> User:
        return self._user

    @classmethod
    def from_id(cls, user_id: str, users: Optional[Dict[str, User]] = None) -> "StaticUserAuth":
        directory = users if users is not None else DEMO_USERS
        if user_id not in directory:
            raise BookingError("not_found", f"Unknown user '{user_id}'. Known users: {', '.join(directory)}")
        return cls(directory[user_id])


def load_users(path: str) -> Dict[str, User]:
    """Load users from a JSON file: a list of objects with id, name, profile and tenant_id."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    users = [User(**item) for item in raw]
    return {u.id: u for u in users}
