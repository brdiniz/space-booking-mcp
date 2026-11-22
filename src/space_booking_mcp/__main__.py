from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from .auth import DEMO_USERS, StaticUserAuth, load_users
from .errors import BookingError
from .server import build_server, default_router


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="space-booking-mcp",
        description="Reference MCP server for booking shared spaces (in-memory demo backends).",
    )
    parser.add_argument(
        "--user-id",
        default=os.environ.get("BOOKING_USER_ID", "u-corp-1"),
        help="Which user this server acts as (default: $BOOKING_USER_ID or u-corp-1)",
    )
    parser.add_argument("--users-file", help="JSON file with users, replacing the built-in demo users")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    users = load_users(args.users_file) if args.users_file else DEMO_USERS
    try:
        auth = StaticUserAuth.from_id(args.user_id, users)
    except BookingError as exc:
        print(exc.message, file=sys.stderr)
        return 2

    server = build_server(default_router(), auth)
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        # Demo only: every HTTP client acts as the same user. Do not expose this to a network.
        server.run(transport="streamable-http", host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
