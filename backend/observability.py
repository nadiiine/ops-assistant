"""Observability summary helpers for the FastAPI backend."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from agent import _load_env, _resolve_kubeconfig
from mcp_client import KubernetesMCPClient
from prometheus_tool import default_prometheus_url


def _prometheus_url() -> str:
    return default_prometheus_url()


def _count_ready_nodes(output: str) -> tuple[int, int]:
    ready = 0
    total = 0
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("NAME") or "STATUS" in stripped and "NAME" in stripped:
            continue
        # kubectl get nodes lines typically: NAME STATUS ROLES ...
        parts = stripped.split()
        if len(parts) < 2:
            continue
        total += 1
        if parts[1] == "Ready":
            ready += 1
    return ready, total


def _count_unhealthy_pods(output: str) -> int:
    unhealthy = 0
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("NAMESPACE") or stripped.startswith("NAME"):
            continue
        # wide/name tables vary; look for common bad phases
        if any(
            token in stripped
            for token in (
                "CrashLoopBackOff",
                "ImagePullBackOff",
                "ErrImagePull",
                "Error",
                "OOMKilled",
                "Pending",
                "Unknown",
            )
        ):
            unhealthy += 1
            continue
        parts = stripped.split()
        # NAMESPACE NAME READY STATUS ...
        if len(parts) >= 4 and parts[3] not in {"Running", "Succeeded", "Completed"}:
            unhealthy += 1
    return unhealthy


def _recent_firing_alerts() -> int:
    base = _prometheus_url().rstrip("/")
    # Alertmanager-compatible path via Prometheus ALERTS metric when available.
    query = 'count(ALERTS{alertstate="firing"} unless ALERTS{alertname="Watchdog"}) or vector(0)'
    url = f"{base}/api/v1/query?{urllib.parse.urlencode({'query': query})}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        result = payload.get("data", {}).get("result") or []
        if not result:
            return 0
        value = result[0].get("value", [None, "0"])[1]
        return int(float(value))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError):
        return 0


def _status_label(nodes_ready: int, nodes_total: int, unhealthy_pods: int, recent_alerts: int) -> str:
    if nodes_total == 0:
        return "critical"
    if nodes_ready < nodes_total or unhealthy_pods > 0 or recent_alerts > 0:
        if nodes_ready == 0 or unhealthy_pods >= 3 or recent_alerts >= 3:
            return "critical"
        return "degraded"
    return "healthy"


async def observability_summary() -> dict[str, Any]:
    _load_env()
    kubeconfig = _resolve_kubeconfig()
    try:
        async with KubernetesMCPClient(kubeconfig=kubeconfig) as mcp:
            nodes_out = await mcp.call_tool("kubectl_get", {"resourceType": "nodes", "output": "wide"})
            pods_out = await mcp.call_tool(
                "kubectl_get",
                {"resourceType": "pods", "allNamespaces": True, "output": "wide"},
            )
        nodes_ready, nodes_total = _count_ready_nodes(nodes_out)
        unhealthy_pods = _count_unhealthy_pods(pods_out)
        recent_alerts = _recent_firing_alerts()
        status = _status_label(nodes_ready, nodes_total, unhealthy_pods, recent_alerts)
        return {
            "status": status,
            "nodes_ready": nodes_ready,
            "nodes_total": nodes_total,
            "unhealthy_pods": unhealthy_pods,
            "recent_alerts": recent_alerts,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "critical",
            "nodes_ready": 0,
            "nodes_total": 0,
            "unhealthy_pods": 0,
            "recent_alerts": 0,
            "detail": str(exc),
        }
