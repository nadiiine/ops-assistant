"""Phase 1 guardrail policy for Kubernetes MCP and observability tools."""

from __future__ import annotations

from typing import Any

from prometheus_tool import validate_prometheus_query_args

# Read-only and safe mutation tools allowed in Phase 1.
ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "ping",
        "kubectl_get",
        "kubectl_describe",
        "kubectl_logs",
        "explain_resource",
        "list_api_resources",
        "kubectl_context",
        "kubectl_scale",
        "prometheus_query",
    }
)

# Destructive tools blocked by policy (Phase 1 deny-by-default for deletes).
BLOCKED_TOOLS: frozenset[str] = frozenset(
    {
        "kubectl_delete",
        "uninstall_helm_chart",
        "cleanup",
        "cleanup_pods",
        "node_management",
        "kubectl_generic",
        "helm_template_uninstall",
    }
)


def check_tool_call(tool_name: str, arguments: dict[str, Any] | None = None) -> tuple[bool, str]:
    """Return (allowed, reason). Blocks destructive MCP tools in Phase 1."""
    if tool_name in BLOCKED_TOOLS:
        return False, (
            f"Tool '{tool_name}' is blocked by Phase 1 guardrail policy. "
            "Destructive operations (delete, cleanup, generic kubectl) are not permitted."
        )

    if tool_name not in ALLOWED_TOOLS:
        return False, (
            f"Tool '{tool_name}' is not in the Phase 1 allowlist. "
            "Only approved read, scale, and prometheus_query operations are permitted."
        )

    if tool_name == "prometheus_query":
        return validate_prometheus_query_args(arguments)

    return True, "allowed"
