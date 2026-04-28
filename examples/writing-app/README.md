# Writing-App Reference Integrations

These examples show how writing tools connect to the Biblioteca gateway through
Cloudflare Access and call the federated `query` tool.

- `claude_desktop/`: Claude Desktop managed remote MCP configuration.
- `cursor/`: project-level Cursor MCP configuration.
- `python/`: small Python smoke client using the official MCP Python SDK.

All examples assume the gateway is reachable at `https://<gateway-hostname>/mcp`
and Cloudflare Access service-token credentials are available as:

- `CF_ACCESS_CLIENT_ID`
- `CF_ACCESS_CLIENT_SECRET`

The demo prompt is:

```text
Draft a summary of LFP cathode degradation including our internal SOPs and reports.
```

The expected result is drafted prose with provenance citations and a list of
consulted or unavailable sources.
