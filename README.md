# space-booking-mcp

A reference [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that lets an AI assistant such as Claude or ChatGPT book shared spaces (meeting rooms, desks, amenities) on behalf of a signed-in user.

Its main idea is **profile-based routing**: the assistant sees one small set of tools, and the server sends each call to the right booking system for that user, with that system's own rules. A corporate user and a residential user can ask the same question and get answers from different back ends.

It is a runnable example, not a product. The booking systems are in-memory so you can try everything without any external service, and the adapter interface shows where your real APIs plug in.

## What it demonstrates

- Six well-described tools: `whoami`, `list_spaces`, `check_availability`, `book_space`, `list_my_bookings`, `cancel_booking`
- **Profile routing** from the user's account type to a backend adapter ([architecture](docs/architecture.md))
- **Different rules per backend** (opening hours, maximum duration, active-booking limits), reported to the model through `whoami` so it can plan within them
- **Errors written for the model**: a clash says what is taken and which tool to call next
- **Safety basics**: tenant isolation, ownership checks, strict input validation, and tool annotations that mark read-only and destructive tools ([security notes](docs/security.md))
- Built on the official MCP Python SDK, with tests that talk to the server through a real MCP client

## Quick start

```bash
git clone https://github.com/brdiniz/space-booking-mcp.git
cd space-booking-mcp
pip install -e ".[dev]"
pytest
```

Run it as a local (stdio) server, acting as one of the demo users:

```bash
BOOKING_USER_ID=u-corp-1 python -m space_booking_mcp     # corporate user
BOOKING_USER_ID=u-res-1  python -m space_booking_mcp     # residential user
```

To connect it to an assistant or inspect it, see [docs/connecting.md](docs/connecting.md).

## Example conversation (illustrative)

> **You:** Book the Atlas room tomorrow at 10 for an hour.
>
> The assistant calls `whoami` (a corporate account, up to 8 hours per booking), `check_availability` for `room-atlas`, confirms the details with you, then calls `book_space`.
>
> **You:** Actually, cancel it.
>
> The assistant calls `list_my_bookings`, finds the booking, and calls `cancel_booking`.

A residential user asking for "the gym for three hours" gets a clear refusal from the server (the limit for that account type is two hours), and the assistant can offer a two-hour slot instead.

## Project layout

```text
src/space_booking_mcp/
  server.py          Tool definitions (the MCP surface)
  router.py          Chooses a backend from the user's profile
  auth.py            Who is calling (demo: fixed user per process)
  backends/base.py   The adapter interface your real systems implement
  backends/in_memory.py  Thread-safe demo backends with different rules
  models.py          Typed inputs and outputs
tests/               Backend rules, isolation, and end-to-end tool calls
docs/                Architecture, connecting clients, security
```

## Plugging in a real booking system

1. Implement `BookingBackend` (five methods) for your API.
2. Register it in the router under a `Profile`.
3. Keep tenant isolation and ownership checks inside the adapter or the API behind it.
4. Replace `StaticUserAuth` with identity taken from a verified access token (see [security](docs/security.md)).

## Limitations

- Data lives in memory and is lost on restart.
- The demo identity is one fixed user per server process. A shared remote deployment needs per-request authentication before it is safe to expose.
- Prices, payments, notifications and recurring bookings are out of scope.

## Need an MCP server for your product?

I help teams design and ship MCP servers and AI assistants that act safely on real systems: tool design, authentication, evaluation and rollout. Contact: brdiniz@icloud.com

## License

MIT. See [LICENSE](LICENSE).
