"""Phase 1 guardrail policy for Kubernetes MCP tool calls."""

from __future__ import annotations

from typing import Any

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
        "kubectl_apply",
        "kubectl_create",
        "kubectl_patch",
        "kubectl_rollout",
        "port_forward",
        "stop_port_forward",
        "install_helm_chart",
        "upgrade_helm_chart",
        "helm_template_apply",
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
    _ = arguments  # reserved for future argument-level checks

    if tool_name in BLOCKED_TOOLS:
        return False, (
            f"Tool '{tool_name}' is blocked by Phase 1 guardrail policy. "
            "Destructive operations (delete, cleanup, generic kubectl) are not permitted."
        )

    if tool_name not in ALLOWED_TOOLS:
        return False, (
            f"Tool '{tool_name}' is not in the Phase 1 allowlist. "
            "Only approved read and scale operations are permitted."
        )

    return True, "allowed"
