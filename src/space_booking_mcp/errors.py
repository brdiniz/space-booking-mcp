from __future__ import annotations


class BookingError(Exception):
    """A domain error with a stable machine-readable code.

    The message is written for the model (and the person behind it): it says what went wrong and,
    where possible, what to try instead.
    """

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
