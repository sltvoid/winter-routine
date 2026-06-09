#!/usr/bin/env python3
"""
Learner / data-platform MCP adapter.

Wraps the existing REST API at $MCP_BASE_URL/api/mcp/tools/<name> (X-API-Key
auth) as a Model Context Protocol server, so its tools become native MCP tools
inside Claude clients (Cowork, Claude Code, desktop).

Why this exists: Cowork runs bash in a sandbox whose egress proxy blocks the
data-platform host, so the curl-based scripts/mcp.sh cannot reach it from there.
MCP connector traffic does NOT go through that sandbox -- Claude talks to this
adapter directly (remote mode) or via a local process (stdio mode), and the
adapter is the thing that calls the REST API. That sidesteps the egress block
with no allowlist change.

Transports (set ADAPTER_TRANSPORT):
  stdio            (default) Run as a LOCAL MCP server on your machine, exactly
                   like obsidian-bridge. No hosting, no TLS; uses your machine's
                   real network to reach the endpoint.
  streamable-http  Run as a REMOTE MCP server (public HTTPS URL). Use this if you
                   register the connector by URL. See README for hardening.

Env:
  MCP_BASE_URL       required   e.g. https://a8f2e1.steventa.me
  MCP_API_KEY        required   backend API key (kept server-side, never sent to Claude)
  ADAPTER_TRANSPORT  stdio | streamable-http   (default: stdio)
  ADAPTER_HOST       default 127.0.0.1   (streamable-http only)
  ADAPTER_PORT       default 8787        (streamable-http only)
  ADAPTER_PATH       default /mcp        (streamable-http only)
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.environ.get("MCP_BASE_URL", "").rstrip("/")
API_KEY = os.environ.get("MCP_API_KEY", "")
if not BASE_URL or not API_KEY:
    raise SystemExit("MCP_BASE_URL and MCP_API_KEY must both be set")

HOST = os.environ.get("ADAPTER_HOST", "127.0.0.1")
PORT = int(os.environ.get("ADAPTER_PORT", "8787"))
PATH = os.environ.get("ADAPTER_PATH", "/mcp")
TRANSPORT = os.environ.get("ADAPTER_TRANSPORT", "stdio")

mcp = FastMCP("steventa-data-platform", host=HOST, port=PORT, streamable_http_path=PATH)
_client = httpx.AsyncClient(timeout=30.0)


async def _call(tool: str, args: dict[str, Any]) -> str:
    """POST args to the backend REST tool; return its JSON envelope as text."""
    body = {k: v for k, v in args.items() if v is not None}
    resp = await _client.post(
        f"{BASE_URL}/api/mcp/tools/{tool}",
        headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
        json=body,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and data.get("status") == "error":
        raise RuntimeError(f"{tool} error: {data.get('error')}")
    return json.dumps(data, default=str)


# ----------------------------- read tools -----------------------------
@mcp.tool()
async def compute_daily_insights(date: str) -> str:
    """Pre-computed Phase-1 daily insights (anomalies/parity/career). date=YYYY-MM-DD (ET)."""
    return await _call("compute_daily_insights", {"date": date})


@mcp.tool()
async def query_calendar() -> str:
    """Latest daily_briefing.schedule_blocks (prior briefing context, NOT Google Calendar). No args."""
    return await _call("query_calendar", {})


@mcp.tool()
async def query_health(date: Optional[str] = None, mode: Optional[str] = None) -> str:
    """Health metrics. mode='daily' (default) or 'workouts'; date=YYYY-MM-DD (ET, default today)."""
    return await _call("query_health", {"date": date, "mode": mode})


@mcp.tool()
async def query_raw_sql(database: str, sql: str) -> str:
    """Run one SELECT. database in: llm_db, email_db, rescuetime_db, health_db, news_db, spotify_data, job_tracker, context_db."""
    return await _call("query_raw_sql", {"database": database, "sql": sql})


@mcp.tool()
async def recall_memory(query: str, category: Optional[str] = None, limit: Optional[int] = None) -> str:
    """Fuzzy search agent_memory. category in preference|pattern|fact|goal|external; limit default 10."""
    return await _call("recall_memory", {"query": query, "category": category, "limit": limit})


# ----------------------------- write tools -----------------------------
@mcp.tool()
async def save_memory(content: str, category: str, key: Optional[str] = None,
                      confidence: Optional[float] = None, source: Optional[str] = None,
                      expires_at: Optional[str] = None) -> str:
    """Insert a memory row. category in preference|pattern|fact|goal|external; pass key for idempotency."""
    return await _call("save_memory", {"content": content, "category": category, "key": key,
                                        "confidence": confidence, "source": source, "expires_at": expires_at})


@mcp.tool()
async def update_memory(memory_id: int, content: str, category: Optional[str] = None,
                        confidence: Optional[float] = None, expires_at: Optional[str] = None,
                        clear_expires_at: Optional[bool] = None, expected_source: Optional[str] = None) -> str:
    """Update one memory by integer ID. Use expected_source='learning_agent' for learner upserts."""
    return await _call("update_memory", {"memory_id": memory_id, "content": content, "category": category,
                                          "confidence": confidence, "expires_at": expires_at,
                                          "clear_expires_at": clear_expires_at, "expected_source": expected_source})


@mcp.tool()
async def expire_memory(memory_id: Optional[int] = None, key: Optional[str] = None,
                        source: Optional[str] = None, expected_source: Optional[str] = None) -> str:
    """Soft-expire a memory by memory_id, or by key+source. Provide either memory_id or both key and source."""
    return await _call("expire_memory", {"memory_id": memory_id, "key": key,
                                          "source": source, "expected_source": expected_source})


@mcp.tool()
async def write_llm_run(run_type: str, model: str, output_response: str,
                        input_payload: Optional[str] = None, pipeline_id: Optional[str] = None,
                        step_label: Optional[str] = None) -> str:
    """Persist an llm_runs row. output_response/input_payload are JSON strings."""
    return await _call("write_llm_run", {"run_type": run_type, "model": model,
                                          "output_response": output_response, "input_payload": input_payload,
                                          "pipeline_id": pipeline_id, "step_label": step_label})


@mcp.tool()
async def write_agent_run(goal: str, final_response: str, model: Optional[str] = None,
                          tool_calls: Optional[str] = None, iterations: Optional[int] = None,
                          pipeline_id: Optional[str] = None) -> str:
    """Persist an agent_runs row. tool_calls is a JSON string array."""
    return await _call("write_agent_run", {"goal": goal, "final_response": final_response, "model": model,
                                            "tool_calls": tool_calls, "iterations": iterations,
                                            "pipeline_id": pipeline_id})


@mcp.tool()
async def update_profile(sections: str, change_summary: str, source_profile_ids: Optional[str] = None) -> str:
    """Insert a new user_profile version. sections is a JSON string of the full profile sections."""
    return await _call("update_profile", {"sections": sections, "change_summary": change_summary,
                                           "source_profile_ids": source_profile_ids})


# ASGI app for remote (streamable-http) hosting:  uvicorn learner_mcp_adapter:app --host 127.0.0.1 --port 8787
app = mcp.streamable_http_app()

if __name__ == "__main__":
    mcp.run(transport=TRANSPORT)
