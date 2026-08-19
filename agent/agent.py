#!/usr/bin/env python3
"""Phase 1 ops assistant: OpenAI agent with Kubernetes MCP tools and guardrails."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from guardrails import check_tool_call
from mcp_client import KubernetesMCPClient

AGENT_DIR = Path(__file__).resolve().parent
SYSTEM_PROMPT = """You are a Kubernetes operations assistant.

Use the available MCP Kubernetes tools to inspect and manage the cluster.
For read-only questions, prefer kubectl_get, kubectl_describe, and kubectl_logs.
For scaling deployments, use kubectl_scale with the deployment name, namespace, and replica count.

Namespace rules for kubectl_get:
- When the user asks about pods (or any resource) WITHOUT specifying a namespace, always pass
  allNamespaces: true so that resources across ALL namespaces are returned.
- When the user explicitly names a namespace (e.g. "in kube-system"), pass that namespace and
  do NOT set allNamespaces.
- Never assume the default namespace for a general resource query.

If a kubectl_get call returns an empty list and allNamespaces was true, say
"There are no <resource> running in the cluster."
If the call targeted a specific namespace and returned empty, say
"There are no <resource> in the <namespace> namespace."

If the user asks for a destructive action such as delete, still request the matching MCP tool
so the guardrail policy can refuse it. Explain the policy refusal clearly afterward.
When diagnosing failing workloads, inspect pod status/events and report concrete error reasons
such as ImagePullBackOff, ErrImagePull, or CrashLoopBackOff.
Be concise and factual."""


@dataclass
class AgentResult:
    answer: str
    tools_used: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)


def _load_env() -> None:
    load_dotenv(AGENT_DIR / ".env")


def _openai_tools(mcp_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description") or tool["name"],
                "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
            },
        }
        for tool in mcp_tools
    ]


def _resolve_kubeconfig() -> str:
    kubeconfig = os.environ.get("KUBECONFIG", "")
    if kubeconfig:
        return kubeconfig
    kind_path = AGENT_DIR / "kind-kubeconfig"
    return str(kind_path) if kind_path.exists() else ""


async def run_agent(prompt: str) -> AgentResult:
    _load_env()
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    kubeconfig = _resolve_kubeconfig()
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)
    tools_used: list[str] = []
    blocked_tools: list[str] = []

    async with KubernetesMCPClient(kubeconfig=kubeconfig) as mcp:
        tools = await mcp.list_tools()
        openai_tools = _openai_tools(tools)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        for _ in range(12):
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=openai_tools,
                tool_choice="auto",
            )
            message = response.choices[0].message
            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": message.content or "",
            }
            if message.tool_calls:
                assistant_message["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]
            messages.append(assistant_message)

            if not message.tool_calls:
                return AgentResult(
                    answer=(message.content or "").strip(),
                    tools_used=tools_used,
                    blocked_tools=blocked_tools,
                )

            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tools_used.append(tool_name)
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}

                allowed, reason = check_tool_call(tool_name, arguments)
                if not allowed:
                    blocked_tools.append(tool_name)
                    tool_result = reason
                else:
                    tool_result = await mcp.call_tool(tool_name, arguments)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    }
                )

        return AgentResult(
            answer="Agent stopped after maximum tool iterations.",
            tools_used=tools_used,
            blocked_tools=blocked_tools,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Kubernetes ops assistant (Phase 1)")
    parser.add_argument("prompt", help="Natural language request for the cluster")
    args = parser.parse_args()

    try:
        output = asyncio.run(run_agent(args.prompt))
        print(output.answer)
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
