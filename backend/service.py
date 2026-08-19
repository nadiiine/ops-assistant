"""Thin wrappers around the existing agent and MCP client."""

from __future__ import annotations

import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from agent import AgentResult, _load_env, _resolve_kubeconfig, run_agent  # noqa: E402
from mcp_client import KubernetesMCPClient  # noqa: E402


async def chat(message: str) -> AgentResult:
    return await run_agent(message)


async def cluster_status() -> dict:
    _load_env()
    kubeconfig = _resolve_kubeconfig()
    try:
        async with KubernetesMCPClient(kubeconfig=kubeconfig) as mcp:
            output = await mcp.call_tool(
                "kubectl_get",
                {"resourceType": "nodes", "output": "wide"},
            )
        ready = output.count(" Ready")
        # Header line plus node lines; count lines that look like node rows.
        node_lines = [
            line
            for line in output.splitlines()
            if line.strip() and not line.startswith("NAME") and "STATUS" not in line
        ]
        total = len(node_lines)
        return {
            "connected": True,
            "ready_nodes": ready,
            "total_nodes": total,
            "detail": output,
        }
    except Exception as exc:
        return {
            "connected": False,
            "ready_nodes": 0,
            "total_nodes": 0,
            "detail": str(exc),
        }
