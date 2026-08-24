#!/usr/bin/env python3
"""Ops assistant: Amazon Bedrock agent with Kubernetes MCP tools and guardrails."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

from guardrails import check_tool_call
from mcp_client import KubernetesMCPClient
from prometheus_tool import execute_prometheus_query, prometheus_tool_definition

AGENT_DIR = Path(__file__).resolve().parent
MAX_TOOL_ROUNDS = 5
MAX_TOOL_OUTPUT_CHARS = 12_000
DEFAULT_PROVIDER = "bedrock"
DEFAULT_REGION = "us-east-1"
DEFAULT_MODEL = "us.amazon.nova-2-lite-v1:0"
_TRANSIENT_ERROR_CODES = frozenset(
    {
        "ThrottlingException",
        "ServiceUnavailableException",
        "ModelTimeoutException",
        "InternalServerException",
        "RequestTimeout",
        "TooManyRequestsException",
    }
)

logger = logging.getLogger("ops_assistant.agent")

SYSTEM_PROMPT = """You are a Kubernetes operations and observability assistant.

Use the available MCP Kubernetes tools to inspect and manage the cluster.
For read-only questions, prefer kubectl_get, kubectl_describe, and kubectl_logs.
For scaling deployments, use kubectl_scale with the deployment name, namespace, and replica count.
For metrics questions (CPU, memory, restarts, unavailable replicas), use prometheus_query
with a predefined query_type only. Never invent free-form PromQL.

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

Cluster health / diagnosis prompts ("analyze health", "why unhealthy", "diagnose workloads"):
Batch independent reads in the same round when possible:
1. kubectl_get nodes
2. kubectl_get pods with allNamespaces: true
3. kubectl_get events (prefer allNamespaces when useful)
4. prometheus_query for node_cpu_usage, node_memory_usage, pod_restarts_1h,
   pods_crashloop, deployment_unavailable_replicas as needed
5. kubectl_logs only for suspicious/unhealthy pods already identified
6. Check deployment replica state when relevant

Summarize with:
- overall cluster health (Healthy / Degraded / Critical)
- unhealthy nodes/pods
- likely root cause (use "likely", "possible", or "evidence suggests" unless definitive)
- evidence used
- severity
- recommended next action

If the user asks for a destructive action such as delete, still request the matching MCP tool
so the guardrail policy can refuse it. Explain the policy refusal clearly afterward.
When diagnosing failing workloads, inspect pod status/events and report concrete error reasons
such as ImagePullBackOff, ErrImagePull, CrashLoopBackOff, or OOMKilled.
Be concise and factual."""


@dataclass
class AgentResult:
    answer: str
    tools_used: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)


def _load_env() -> None:
    load_dotenv(AGENT_DIR / ".env")


def _sanitize_schema(schema: Any) -> dict[str, Any]:
    """Keep JSON Schema fields Bedrock toolSpec accepts (object top-level)."""
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}

    allowed = {"type", "properties", "required", "description", "enum", "items"}
    cleaned: dict[str, Any] = {}
    for key, value in schema.items():
        if key not in allowed:
            continue
        if key == "type" and isinstance(value, list):
            non_null = [item for item in value if item != "null"]
            cleaned[key] = non_null[0] if non_null else "string"
        elif key == "properties" and isinstance(value, dict):
            cleaned[key] = {name: _sanitize_schema(prop) for name, prop in value.items()}
        elif key == "items":
            cleaned[key] = _sanitize_schema(value)
        else:
            cleaned[key] = value
    if "type" not in cleaned:
        cleaned["type"] = "object"
    if cleaned["type"] == "object":
        cleaned.setdefault("properties", {})
    return cleaned


def _bedrock_tool_config(mcp_tools: list[dict[str, Any]]) -> dict[str, Any]:
    tools = []
    for tool in mcp_tools:
        tools.append(
            {
                "toolSpec": {
                    "name": tool["name"],
                    "description": (tool.get("description") or tool["name"])[:1024],
                    "inputSchema": {
                        "json": _sanitize_schema(
                            tool.get("inputSchema") or {"type": "object", "properties": {}}
                        )
                    },
                }
            }
        )
    return {"tools": tools, "toolChoice": {"auto": {}}}


def _truncate_tool_output(text: str) -> str:
    if len(text) <= MAX_TOOL_OUTPUT_CHARS:
        return text
    omitted = len(text) - MAX_TOOL_OUTPUT_CHARS
    return f"{text[:MAX_TOOL_OUTPUT_CHARS]}\n...[truncated {omitted} characters]"


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        if code in _TRANSIENT_ERROR_CODES:
            return True
    message = str(exc).lower()
    return any(
        token in message
        for token in ("timeout", "throttl", "temporarily", "unavailable", "429", "503")
    )


def _converse(client: Any, **kwargs: Any) -> dict[str, Any]:
    """One Bedrock Converse call with a single retry for transient API failures."""
    try:
        return client.converse(**kwargs)
    except (ClientError, BotoCoreError) as exc:
        if not _is_transient_error(exc):
            raise
        logger.warning("transient Bedrock API error; retrying once")
        time.sleep(0.5)
        return client.converse(**kwargs)


def _tool_use_input(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return dict(raw)


def _extract_tool_uses(message: dict[str, Any]) -> list[dict[str, Any]]:
    tool_uses: list[dict[str, Any]] = []
    for block in message.get("content") or []:
        if isinstance(block, dict) and "toolUse" in block:
            tool_uses.append(block["toolUse"])
    return tool_uses


def _response_text(message: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in message.get("content") or []:
        if isinstance(block, dict) and "text" in block and block["text"]:
            parts.append(str(block["text"]))
    return "\n".join(parts).strip()


def _resolve_kubeconfig() -> str:
    kubeconfig = os.environ.get("KUBECONFIG", "")
    if kubeconfig:
        return kubeconfig
    kind_path = AGENT_DIR / "kind-kubeconfig"
    return str(kind_path) if kind_path.exists() else ""


def _bedrock_client() -> Any:
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or DEFAULT_REGION
    return boto3.client("bedrock-runtime", region_name=region)


async def run_agent(prompt: str) -> AgentResult:
    _load_env()
    provider = (os.environ.get("LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    if provider != "bedrock":
        raise RuntimeError(f"Unsupported LLM_PROVIDER={provider!r}; expected 'bedrock'")

    kubeconfig = _resolve_kubeconfig()
    model = os.environ.get("BEDROCK_MODEL", DEFAULT_MODEL)
    client = _bedrock_client()
    tools_used: list[str] = []
    blocked_tools: list[str] = []
    model_calls = 0

    async with KubernetesMCPClient(kubeconfig=kubeconfig) as mcp:
        tools = await mcp.list_tools()
        tools.append(prometheus_tool_definition())
        tool_config = _bedrock_tool_config(tools)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": [{"text": prompt}]},
        ]
        system = [{"text": SYSTEM_PROMPT}]
        inference_config = {"temperature": 0.2, "maxTokens": 4096}

        for _ in range(MAX_TOOL_ROUNDS):
            model_calls += 1
            logger.info("bedrock model call %s/%s", model_calls, MAX_TOOL_ROUNDS)
            response = _converse(
                client,
                modelId=model,
                messages=messages,
                system=system,
                toolConfig=tool_config,
                inferenceConfig=inference_config,
            )

            output_message = response.get("output", {}).get("message") or {
                "role": "assistant",
                "content": [],
            }
            messages.append(output_message)
            tool_uses = _extract_tool_uses(output_message)
            if not tool_uses:
                answer = _response_text(output_message)
                if not answer:
                    answer = "The model returned no text for this request."
                return AgentResult(
                    answer=answer,
                    tools_used=tools_used,
                    blocked_tools=blocked_tools,
                )

            tool_result_blocks: list[dict[str, Any]] = []
            for tool_use in tool_uses:
                tool_name = tool_use.get("name") or ""
                tool_use_id = tool_use.get("toolUseId") or ""
                tools_used.append(tool_name)
                arguments = _tool_use_input(tool_use.get("input"))

                allowed, reason = check_tool_call(tool_name, arguments)
                if not allowed:
                    blocked_tools.append(tool_name)
                    tool_result = reason
                    status = "error"
                elif tool_name == "prometheus_query":
                    tool_result = execute_prometheus_query(arguments)
                    status = "success"
                else:
                    tool_result = await mcp.call_tool(tool_name, arguments)
                    status = "success"

                tool_result_blocks.append(
                    {
                        "toolResult": {
                            "toolUseId": tool_use_id,
                            "content": [
                                {
                                    "json": {
                                        "result": _truncate_tool_output(tool_result),
                                    }
                                }
                            ],
                            "status": status,
                        }
                    }
                )

            messages.append({"role": "user", "content": tool_result_blocks})

        return AgentResult(
            answer="Agent stopped after maximum tool iterations.",
            tools_used=tools_used,
            blocked_tools=blocked_tools,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Kubernetes ops assistant")
    parser.add_argument("prompt", help="Natural language request for the cluster")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    try:
        output = asyncio.run(run_agent(args.prompt))
        print(output.answer)
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
