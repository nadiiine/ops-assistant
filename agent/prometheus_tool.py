"""Safe Prometheus query helper for the Ops Assistant agent."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# Helm truncates this service name (kube-prometheus-stack + release ops-monitor).
DEFAULT_PROMETHEUS_URL = (
    "http://ops-monitor-kube-prometheu-prometheus.monitoring.svc.cluster.local:9090"
)

# Predefined operational queries only — no free-form PromQL from the model.
PREDEFINED_QUERIES: dict[str, str] = {
    "top_pod_cpu": (
        "topk(5, sum by (namespace, pod) "
        "(rate(container_cpu_usage_seconds_total{container!=\"\",pod!=\"\"}[5m])))"
    ),
    "top_pod_memory": (
        "topk(5, sum by (namespace, pod) "
        "(container_memory_working_set_bytes{container!=\"\",pod!=\"\"}))"
    ),
    "node_cpu_usage": (
        "1 - avg by (instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m]))"
    ),
    "node_memory_usage": (
        "1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)"
    ),
    "pod_restarts_1h": "topk(10, increase(kube_pod_container_status_restarts_total[1h]))",
    "pods_crashloop": (
        "kube_pod_container_status_waiting_reason{reason=\"CrashLoopBackOff\"} == 1"
    ),
    "deployment_unavailable_replicas": (
        "(kube_deployment_spec_replicas - kube_deployment_status_replicas_available) > 0"
    ),
    "node_not_ready": 'kube_node_status_condition{condition="Ready",status="true"} == 0',
    "pod_phase_not_running": (
        'count by (namespace, phase) (kube_pod_status_phase{phase!="Running",phase!="Succeeded"} == 1)'
    ),
    "cluster_cpu_summary": "avg(1 - avg by (instance) (rate(node_cpu_seconds_total{mode=\"idle\"}[5m])))",
    "cluster_memory_summary": (
        "avg(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))"
    ),
}

PROMETHEUS_QUERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query_type": {
            "type": "string",
            "description": (
                "Predefined PromQL query type. One of: "
                + ", ".join(sorted(PREDEFINED_QUERIES))
            ),
            "enum": sorted(PREDEFINED_QUERIES.keys()),
        },
        "time": {
            "type": "string",
            "description": "Optional RFC3339 evaluation time. Omit for now.",
        },
    },
    "required": ["query_type"],
}


def default_prometheus_url() -> str:
    return os.environ.get("PROMETHEUS_URL", DEFAULT_PROMETHEUS_URL)


def validate_prometheus_query_args(arguments: dict[str, Any] | None) -> tuple[bool, str]:
    args = arguments or {}
    query_type = args.get("query_type")
    if not isinstance(query_type, str) or not query_type.strip():
        return False, "prometheus_query requires query_type"
    if query_type not in PREDEFINED_QUERIES:
        return False, (
            f"Unsupported query_type '{query_type}'. "
            f"Allowed: {', '.join(sorted(PREDEFINED_QUERIES))}"
        )
    if "query" in args and args["query"] not in (None, ""):
        return False, "Free-form PromQL is not allowed; use query_type only"
    return True, "allowed"


def execute_prometheus_query(arguments: dict[str, Any] | None) -> str:
    allowed, reason = validate_prometheus_query_args(arguments)
    if not allowed:
        return json.dumps({"ok": False, "error": reason})

    args = arguments or {}
    query_type = args["query_type"]
    promql = PREDEFINED_QUERIES[query_type]
    base = default_prometheus_url().rstrip("/")
    params = {"query": promql}
    if args.get("time"):
        params["time"] = str(args["time"])
    url = f"{base}/api/v1/query?{urllib.parse.urlencode(params)}"

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(body)
    except urllib.error.HTTPError as exc:
        return json.dumps({"ok": False, "error": f"HTTP {exc.code}: {exc.reason}"})
    except Exception as exc:  # noqa: BLE001 — surface to model as tool result
        return json.dumps({"ok": False, "error": str(exc)})

    return json.dumps(
        {
            "ok": True,
            "query_type": query_type,
            "promql": promql,
            "result": payload.get("data", {}).get("result", []),
            "status": payload.get("status"),
        },
        indent=2,
    )


def prometheus_tool_definition() -> dict[str, Any]:
    return {
        "name": "prometheus_query",
        "description": (
            "Query Prometheus using a predefined operational query_type "
            "(CPU, memory, restarts, CrashLoop, unavailable replicas, node readiness). "
            "Free-form PromQL is not accepted."
        ),
        "inputSchema": PROMETHEUS_QUERY_SCHEMA,
    }
