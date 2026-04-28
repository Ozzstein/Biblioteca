# Claude Desktop Reference Config

This example uses Claude Desktop's managed remote MCP server configuration. The
current Claude managed configuration schema represents `managedMcpServers` as a
JSON-encoded string under `enterpriseConfig`.

## Setup

1. Copy `claude_desktop_config.json` into the Claude Desktop configuration
   location for your deployment.
2. Replace `https://<your-gateway-hostname>/mcp` with the Cloudflare-protected
   gateway MCP URL.
3. Provide `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` through your
   managed configuration or secret-injection mechanism.
4. Fully quit and reopen Claude Desktop.
5. Ask:

```text
Draft a 3-page summary of LFP cathode degradation including our internal SOPs and reports.
```

Expected behavior: Claude can use the `battery-research-os` connector, calls the
`query` tool, and receives drafted prose with provenance citations from
literature and lab sources.

## Notes

Claude Desktop's local developer `mcpServers` file is still primarily for local
stdio servers. For remote HTTP MCP in managed deployments, prefer the
`managedMcpServers` shape shown here.
