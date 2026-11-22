# Connecting and inspecting

## Local clients (stdio)

Most desktop MCP clients start a local server from a command. Add an entry like this to the client's MCP server configuration (the file location depends on the client, so check its documentation):

```json
{
  "mcpServers": {
    "space-booking": {
      "command": "python",
      "args": ["-m", "space_booking_mcp"],
      "env": { "BOOKING_USER_ID": "u-corp-1" }
    }
  }
}
```

Use the Python from the environment where you installed the package (for example a virtual environment's `python`). Switch `BOOKING_USER_ID` to `u-res-1` to act as the residential user. The built-in demo users are:

| User id | Account type | Tenant |
|---|---|---|
| `u-corp-1`, `u-corp-2` | corporate | acme-corp |
| `u-res-1` | residential | harbour-view |

To use your own users, pass `--users-file users.json`, a list of objects with `id`, `name`, `profile` and `tenant_id`.

## MCP Inspector

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) lets you list and call tools by hand:

```bash
npx @modelcontextprotocol/inspector python -m space_booking_mcp
```

## Quick programmatic check

```python
import anyio, sys
from mcp import Client
from mcp.client.stdio import StdioServerParameters

async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "space_booking_mcp"])
    async with Client(params) as client:
        print([t.name for t in (await client.list_tools()).tools])
        print((await client.call_tool("whoami", {})).structured_content)

anyio.run(main)
```

## Remote use (HTTP)

```bash
python -m space_booking_mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

This mode is for local experiments only: every client acts as the same demo user and there is no authentication. Assistants that connect to remote servers generally need a public HTTPS endpoint with authentication, and requirements differ between products and change over time, so check the current documentation of the client you target. Before exposing any server, follow [security.md](security.md).
