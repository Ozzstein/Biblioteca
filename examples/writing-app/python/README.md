# Python Writing-App Client

This small client uses the official MCP Python SDK to connect to the Biblioteca
gateway over Streamable HTTP and call the `query` tool.

## Run

```bash
cd examples/writing-app/python
uv sync
cp .env.example .env
```

Fill in `.env`, then run:

```bash
uv run python client.py
```

Expected output is a JSON MCP tool result containing drafted prose, provenance
citations, `sources_consulted`, and `sources_unavailable`.

The script exits `0` on success and nonzero on auth, transport, or gateway
errors.
