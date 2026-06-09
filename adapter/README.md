# Learner / data-platform MCP adapter

Exposes the existing REST API (`$MCP_BASE_URL/api/mcp/tools/<name>`, `X-API-Key`)
as an MCP server so its tools load as native `mcp__steventa-data-platform__*`
tools inside Claude clients — including Cowork, whose sandbox egress proxy blocks
direct `curl` to the endpoint. Connector traffic does not traverse that sandbox,
so this is the supported way to use the platform from Cowork with no allowlist
change and no Team/Enterprise plan.

One file, two transports. Pick the one that matches how you registered
`obsidian-bridge`.

## Install

```bash
cd adapter
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

## Option A — local stdio (simplest; mirrors a typical obsidian-bridge setup)

Runs on your machine, uses your real network to reach the endpoint. No public
hosting, no TLS, nothing exposed to the internet. Add it to your Claude MCP
config the same way obsidian-bridge is configured, e.g.:

```json
{
  "mcpServers": {
    "steventa-data-platform": {
      "command": "/abs/path/adapter/.venv/bin/python",
      "args": ["/abs/path/adapter/learner_mcp_adapter.py"],
      "env": {
        "MCP_BASE_URL": "https://a8f2e1.steventa.me",
        "MCP_API_KEY": "<key>",
        "ADAPTER_TRANSPORT": "stdio"
      }
    }
  }
}
```

The key stays in your local config and is sent to your endpoint only — never to
Claude.

## Option B — remote streamable-HTTP (register by URL)

Run it as a public HTTPS service and register the URL in
Settings → Connectors → Add custom connector.

```bash
export MCP_BASE_URL="https://a8f2e1.steventa.me"
export MCP_API_KEY="<key>"
export ADAPTER_TRANSPORT="streamable-http"
uvicorn learner_mcp_adapter:app --host 127.0.0.1 --port 8787
# then front :8787/mcp with your TLS reverse proxy, e.g. https://mcp.steventa.me/mcp
```

Connector URL = `https://<host>/mcp`.

### Remote security (read before exposing)

This adapter holds your API key and exposes write tools (`update_profile`,
`save_memory`, …). At the MCP layer it is **authless**, so lock it down at the
network layer:

- Restrict inbound to Anthropic's published IP ranges (see
  docs.claude.com / support.claude.com for current ranges), and/or
- put it on an unguessable path, and/or
- add OAuth (Claude supports authless or OAuth remote servers).

Local stdio (Option A) avoids all of this because nothing is exposed.

## Tools exposed

Read: `compute_daily_insights`, `query_calendar`, `query_health`,
`query_raw_sql`, `recall_memory`.
Write: `save_memory`, `update_memory`, `expire_memory`, `write_llm_run`,
`write_agent_run`, `update_profile`.

(The `write_test_*` tools are intentionally omitted; add them if a test flow
needs them.)

## Verify

After registering, the tools appear as `mcp__steventa-data-platform__…`. A
read-only call such as `query_raw_sql {"database":"llm_db","sql":"SELECT 1"}`
confirms it reaches the endpoint.
