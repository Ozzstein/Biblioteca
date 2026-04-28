# Cursor Reference Config

Cursor reads MCP configuration from `.cursor/mcp.json` in a project, or from
`~/.cursor/mcp.json` for a user-wide setup.

## Setup

1. Copy `.cursor/mcp.json` into the project where you draft reports.
2. Replace `https://<your-gateway-hostname>/mcp` with the Cloudflare-protected
   gateway MCP URL.
3. Set `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` in the environment
   Cursor uses for MCP server connections.
4. Restart Cursor or reload MCP servers.
5. Ask Cursor to draft a summary using the `battery-research-os` MCP tools.

Expected behavior: Cursor connects to the remote MCP gateway, calls `query`, and
returns prose with provenance citations plus source availability metadata.
