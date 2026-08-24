"""Deterministic Kubernetes topology + health for the Cluster Health dashboard.

Read-only: uses MCP kubectl_get (JSON) and Prometheus HTTP queries.
Does not call Bedrock.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from agent import _load_env, _resolve_kubeconfig
from mcp_client import KubernetesMCPClient
from prometheus_tool import default_prometheus_url

ALLOWED_NAMESPACES = frozenset(
    {
        "all",
        "ops-assistant",
        "ops-assistant-demo",
        "monitoring",
        "kube-system",
    }
)

# Namespaces that get compact grouping (DaemonSets / many system pods).
COMPACT_NAMESPACES = frozenset({"kube-system", "monitoring"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_k8s_json(raw: str) -> Any:
    """Parse MCP kubectl JSON output; tolerate leading/trailing noise."""
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return {}


def _as_dict(value: Any) -> dict[str, Any]:
    """Normalize metadata/status/spec fields that may arrive as dict, JSON text, or junk."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        # Ready / NotReady / phase-like plain strings are not object status blobs.
        if not (text.startswith("{") or text.startswith("[")):
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return []
            return parsed if isinstance(parsed, list) else []
        return []
    return []


def _items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [i for i in payload["items"] if isinstance(i, dict)]
    if isinstance(payload, list):
        return [i for i in payload if isinstance(i, dict)]
    if isinstance(payload, dict) and payload.get("kind") and payload.get("metadata"):
        return [payload]
    return []


def _labels_match(selector: dict[str, str] | None, labels: dict[str, str] | None) -> bool:
    if not selector:
        return False
    labels = labels or {}
    if not isinstance(labels, dict):
        labels = _as_dict(labels)
    if not isinstance(selector, dict):
        selector = _as_dict(selector)
    return all(labels.get(k) == v for k, v in selector.items())


def _age_from_timestamp(ts: str | None) -> str:
    if not ts:
        return "unknown"
    try:
        created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    delta = datetime.now(timezone.utc) - created.astimezone(timezone.utc)
    secs = int(delta.total_seconds())
    if secs < 0:
        secs = 0
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


def _node_role(labels: dict[str, str] | None) -> str:
    labels = _as_dict(labels) if not isinstance(labels, dict) else (labels or {})
    if (
        "node-role.kubernetes.io/control-plane" in labels
        or "node-role.kubernetes.io/master" in labels
    ):
        return "control-plane"
    return "worker"


def _node_ready(conditions: Any) -> str:
    for cond in _as_list(conditions):
        if not isinstance(cond, dict):
            cond = _as_dict(cond)
            if not cond:
                continue
        if cond.get("type") == "Ready":
            return "Ready" if cond.get("status") == "True" else "NotReady"
    return "Unknown"


def _internal_ip(addresses: Any) -> str | None:
    for addr in _as_list(addresses):
        if not isinstance(addr, dict):
            addr = _as_dict(addr)
            if not addr:
                continue
        if addr.get("type") == "InternalIP":
            return addr.get("address")
    return None


def compute_pod_health(pod: dict[str, Any]) -> str:
    """Return healthy | degraded | critical | unknown for a structured pod dict."""
    status = (pod.get("status") or "").strip()
    phase = (pod.get("phase") or status or "").strip()
    waiting = (pod.get("waiting_reason") or "").strip()
    last_term = (pod.get("last_termination_reason") or "").strip()
    crash = bool(pod.get("crash_loop")) or waiting == "CrashLoopBackOff" or status == "CrashLoopBackOff"
    oom = bool(pod.get("oom_killed")) or last_term == "OOMKilled" or waiting == "OOMKilled"

    if crash or oom or phase == "Failed" or status in {"Failed", "Error"}:
        return "critical"
    if phase == "Pending" or status in {
        "Pending",
        "ImagePullBackOff",
        "ErrImagePull",
        "ContainerCreating",
    }:
        return "degraded"
    if status in {"Terminating", "Unknown"} or phase in {"Unknown", "Terminating"}:
        return "unknown"
    ready = pod.get("ready") or "0/0"
    if phase == "Running" and "/" in str(ready):
        have, want = str(ready).split("/", 1)
        try:
            if int(have) < int(want):
                return "degraded"
        except ValueError:
            pass
    if phase in {"Succeeded", "Completed"}:
        return "healthy"
    if phase == "Running":
        restarts = int(pod.get("restarts") or 0)
        if restarts >= 5:
            return "degraded"
        return "healthy"
    return "degraded"


def compute_deployment_health(
    desired: int,
    available: int,
    pod_healths: list[str],
) -> str:
    if desired > 0 and available == 0:
        return "critical"
    if any(h == "critical" for h in pod_healths):
        return "critical"
    if available < desired:
        return "degraded"
    if any(h in {"degraded", "unknown"} for h in pod_healths):
        return "degraded"
    return "healthy"


def compute_cluster_health(
    nodes: list[dict[str, Any]],
    pods: list[dict[str, Any]],
    deployments: list[dict[str, Any]] | None = None,
) -> str:
    """Cluster-level health from nodes + pods (+ optional deployment replica state)."""
    if not nodes:
        return "critical"
    if any((n.get("status") or "") != "Ready" for n in nodes):
        return "critical"

    pod_healths = [p.get("health") or compute_pod_health(p) for p in pods]
    if any(h == "critical" for h in pod_healths):
        return "critical"

    for dep in deployments or []:
        desired = int(dep.get("desired") or 0)
        available = int(dep.get("available") or 0)
        if desired > 0 and available == 0:
            return "critical"

    if any(h == "degraded" for h in pod_healths):
        return "degraded"
    for dep in deployments or []:
        desired = int(dep.get("desired") or 0)
        available = int(dep.get("available") or 0)
        if available < desired:
            return "degraded"
    return "healthy"


def _prom_instant(query: str, timeout: float = 5.0) -> list[dict[str, Any]]:
    base = default_prometheus_url().rstrip("/")
    url = f"{base}/api/v1/query?{urllib.parse.urlencode({'query': query})}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        return payload.get("data", {}).get("result") or []
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError, OSError):
        return []


def _prom_value_map(results: list[dict[str, Any]], key_fields: tuple[str, ...]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in results:
        metric = row.get("metric") or {}
        key = "|".join(str(metric.get(f) or "") for f in key_fields)
        try:
            out[key] = float(row.get("value", [None, "0"])[1])
        except (TypeError, ValueError, IndexError):
            continue
    return out


def fetch_metrics() -> dict[str, Any]:
    """CPU/memory maps from Prometheus (best-effort; empty if unreachable)."""
    node_cpu = _prom_value_map(
        _prom_instant(
            '100 * (1 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])))'
        ),
        ("instance",),
    )
    node_mem = _prom_value_map(
        _prom_instant(
            "100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))"
        ),
        ("instance",),
    )
    pod_cpu = _prom_value_map(
        _prom_instant(
            'sum by (namespace, pod) (rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m]))'
        ),
        ("namespace", "pod"),
    )
    pod_mem = _prom_value_map(
        _prom_instant(
            'sum by (namespace, pod) (container_memory_working_set_bytes{container!="",pod!=""})'
        ),
        ("namespace", "pod"),
    )
    alerts = 0
    alert_rows = _prom_instant(
        'count(ALERTS{alertstate="firing"} unless ALERTS{alertname="Watchdog"}) or vector(0)'
    )
    if alert_rows:
        try:
            alerts = int(float(alert_rows[0].get("value", [None, "0"])[1]))
        except (TypeError, ValueError, IndexError):
            alerts = 0
    return {
        "node_cpu": node_cpu,
        "node_mem": node_mem,
        "pod_cpu": pod_cpu,
        "pod_mem": pod_mem,
        "alerts": alerts,
    }


def _match_node_metric(ip: str | None, name: str, metric_map: dict[str, float]) -> float | None:
    if not metric_map:
        return None
    candidates = []
    if ip:
        candidates.append(ip)
        candidates.append(f"{ip}:9100")
    candidates.append(name)
    for key, value in metric_map.items():
        for cand in candidates:
            if cand and cand in key:
                return round(value, 1)
    return None


def extract_pod(raw: dict[str, Any], metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else _as_dict(raw)
    meta = _as_dict(raw.get("metadata"))
    status = _as_dict(raw.get("status"))
    spec = _as_dict(raw.get("spec"))
    # MCP summary: top-level name/namespace/status/createdAt (no metadata/status objects).
    ns = str(meta.get("namespace") or raw.get("namespace") or "default")
    name = str(meta.get("name") or raw.get("name") or "")
    plain_status = raw.get("status") if isinstance(raw.get("status"), str) else None
    container_statuses = [
        c if isinstance(c, dict) else _as_dict(c)
        for c in _as_list(status.get("containerStatuses"))
    ]
    container_statuses = [c for c in container_statuses if c]
    init_statuses = [
        c if isinstance(c, dict) else _as_dict(c)
        for c in _as_list(status.get("initContainerStatuses"))
    ]
    init_statuses = [c for c in init_statuses if c]

    ready_have = sum(1 for c in container_statuses if c.get("ready"))
    ready_want = len(container_statuses) or len(_as_list(spec.get("containers")))
    restarts = sum(int(c.get("restartCount") or 0) for c in container_statuses)

    waiting_reason = None
    last_termination_reason = None
    oom_killed = False
    crash_loop = False
    containers: list[dict[str, Any]] = []

    for c in container_statuses:
        state = _as_dict(c.get("state"))
        last_state = _as_dict(c.get("lastState"))
        waiting = _as_dict(state.get("waiting")).get("reason")
        terminated = _as_dict(state.get("terminated")).get("reason")
        last_term = _as_dict(last_state.get("terminated")).get("reason")
        if waiting:
            waiting_reason = waiting_reason or waiting
            if waiting == "CrashLoopBackOff":
                crash_loop = True
            if waiting == "OOMKilled":
                oom_killed = True
        if last_term:
            last_termination_reason = last_termination_reason or last_term
            if last_term == "OOMKilled":
                oom_killed = True
        if terminated == "OOMKilled":
            oom_killed = True
        containers.append(
            {
                "name": c.get("name"),
                "ready": bool(c.get("ready")),
                "restarts": int(c.get("restartCount") or 0),
                "state": (
                    "waiting"
                    if waiting
                    else "terminated"
                    if terminated
                    else "running"
                    if state.get("running")
                    else "unknown"
                ),
                "reason": waiting or terminated or last_term,
            }
        )

    phase = status.get("phase") or "Unknown"
    if plain_status and plain_status.strip():
        # MCP summary uses status as phase / waiting reason text.
        token = plain_status.strip()
        if token in {
            "Running",
            "Pending",
            "Succeeded",
            "Failed",
            "Unknown",
            "CrashLoopBackOff",
            "ImagePullBackOff",
            "ErrImagePull",
            "ContainerCreating",
            "Terminating",
            "Completed",
            "Error",
            "OOMKilled",
        }:
            phase = token
            if token == "CrashLoopBackOff":
                crash_loop = True
                waiting_reason = waiting_reason or token
    display_status = waiting_reason or phase
    if crash_loop:
        display_status = "CrashLoopBackOff"
    # MCP summary has no ready counts; assume 1/1 when Running, else 0/1.
    if ready_want == 0 and plain_status:
        if phase == "Running" and not crash_loop:
            ready_have, ready_want = 1, 1
        else:
            ready_have, ready_want = 0, 1

    age_ts = meta.get("creationTimestamp") or raw.get("createdAt")
    pod: dict[str, Any] = {
        "name": name,
        "namespace": ns,
        "phase": phase,
        "status": display_status,
        "ready": f"{ready_have}/{ready_want}" if ready_want else "0/0",
        "restarts": restarts,
        "node": spec.get("nodeName") or "",
        "age": _age_from_timestamp(age_ts if isinstance(age_ts, str) else None),
        "labels": _as_dict(meta.get("labels")),
        "owner_refs": [
            r if isinstance(r, dict) else _as_dict(r)
            for r in _as_list(meta.get("ownerReferences"))
        ],
        "waiting_reason": waiting_reason,
        "last_termination_reason": last_termination_reason,
        "oom_killed": oom_killed,
        "crash_loop": crash_loop,
        "containers": containers,
        "init_containers": [
            {"name": c.get("name"), "ready": bool(c.get("ready"))} for c in init_statuses
        ],
        "cpu_cores": None,
        "memory_bytes": None,
        "cpu": None,
        "memory": None,
    }
    metrics = metrics or {}
    key = f"{ns}|{name}"
    cpu = (metrics.get("pod_cpu") or {}).get(key)
    mem = (metrics.get("pod_mem") or {}).get(key)
    if cpu is not None:
        pod["cpu_cores"] = round(cpu, 4)
        pod["cpu"] = f"{cpu * 1000:.0f}m" if cpu < 1 else f"{cpu:.2f}"
    if mem is not None:
        pod["memory_bytes"] = int(mem)
        if mem >= 1024**3:
            pod["memory"] = f"{mem / 1024**3:.1f}Gi"
        else:
            pod["memory"] = f"{mem / 1024**2:.0f}Mi"
    pod["health"] = compute_pod_health(pod)
    return pod


def extract_node(raw: dict[str, Any], metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse a Node from full Kubernetes API JSON or simplified MCP summary JSON.

    Full Kubernetes node::

        {"metadata": {"name": "...", "labels": {...}},
         "status": {"conditions": [...], "addresses": [...]}, "spec": {...}}

    Simplified MCP node (confirmed live)::

        {"name": "...", "namespace": "", "kind": "Node",
         "status": "Ready"|"NotReady", "createdAt": "..."}

    Never treat a simplified MCP ``status="Ready"`` as Unknown just because
    ``status`` is not a dict.
    """
    raw = raw if isinstance(raw, dict) else _as_dict(raw)
    metrics = metrics or {}
    meta = _as_dict(raw.get("metadata"))
    status_field = raw.get("status")

    # --- Path A: simplified MCP node (status is a readiness string) ---
    if isinstance(status_field, str):
        token = status_field.strip()
        # JSON-string status blob → treat as full status object below
        if token.startswith("{") or token.startswith("["):
            status = _as_dict(token)
            name = str(meta.get("name") or raw.get("name") or "")
            ip = _internal_ip(status.get("addresses"))
            ready = _node_ready(status.get("conditions"))
        elif token in {"Ready", "NotReady", "Unknown"}:
            # Explicit MCP summary handling — do NOT collapse via _as_dict({}) → Unknown
            name = str(raw.get("name") or meta.get("name") or "")
            ready = token
            ip = None
        else:
            # Malformed plain string (e.g. "bogus") — keep a node row, mark Unknown
            name = str(raw.get("name") or meta.get("name") or "")
            ready = "Unknown"
            ip = None
        cpu = _match_node_metric(ip, name, metrics.get("node_cpu") or {})
        mem = _match_node_metric(ip, name, metrics.get("node_mem") or {})
        health = (
            "healthy"
            if ready == "Ready"
            else "critical"
            if ready == "NotReady"
            else "unknown"
        )
        return {
            "name": name,
            "role": _node_role(meta.get("labels")),
            "status": ready,
            "health": health,
            "internal_ip": ip,
            "cpu_percent": cpu,
            "memory_percent": mem,
            "pod_count": 0,
        }

    # --- Path B: full Kubernetes node object (status dict / missing / null) ---
    status = _as_dict(status_field)
    name = str(meta.get("name") or raw.get("name") or "")
    ip = _internal_ip(status.get("addresses"))
    ready = _node_ready(status.get("conditions"))
    cpu = _match_node_metric(ip, name, metrics.get("node_cpu") or {})
    mem = _match_node_metric(ip, name, metrics.get("node_mem") or {})
    health = (
        "healthy"
        if ready == "Ready"
        else "critical"
        if ready == "NotReady"
        else "unknown"
    )
    return {
        "name": name,
        "role": _node_role(meta.get("labels")),
        "status": ready,
        "health": health,
        "internal_ip": ip,
        "cpu_percent": cpu,
        "memory_percent": mem,
        "pod_count": 0,
    }


def _parse_ready_fraction(text: str | None) -> tuple[int | None, int | None]:
    if not text or not isinstance(text, str):
        return None, None
    m = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*(?:ready)?\s*$", text.strip(), re.IGNORECASE)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def extract_deployment(raw: dict[str, Any]) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else _as_dict(raw)
    meta = _as_dict(raw.get("metadata"))
    spec = _as_dict(raw.get("spec"))
    status = _as_dict(raw.get("status"))
    name = str(meta.get("name") or raw.get("name") or "")
    namespace = str(meta.get("namespace") or raw.get("namespace") or "")
    selector = _as_dict(_as_dict(spec.get("selector")).get("matchLabels"))
    desired = int(
        status.get("replicas") if status.get("replicas") is not None else (spec.get("replicas") or 0)
    )
    available = int(status.get("availableReplicas") or 0)
    ready = int(status.get("readyReplicas") or 0)
    # MCP summary: status is like "1/1 ready"
    plain = raw.get("status") if isinstance(raw.get("status"), str) else None
    ready_n, desired_n = _parse_ready_fraction(plain)
    if ready_n is not None and desired_n is not None:
        ready = ready_n
        available = ready_n
        desired = desired_n
    return {
        "name": name,
        "namespace": namespace,
        "desired": desired,
        "available": available,
        "ready": ready,
        "selector": selector,
        "labels": _as_dict(meta.get("labels")),
    }


def extract_service(raw: dict[str, Any]) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else _as_dict(raw)
    meta = _as_dict(raw.get("metadata"))
    spec = _as_dict(raw.get("spec"))
    name = str(meta.get("name") or raw.get("name") or "")
    namespace = str(meta.get("namespace") or raw.get("namespace") or "")
    ports = []
    for p in _as_list(spec.get("ports")):
        p = p if isinstance(p, dict) else _as_dict(p)
        if not p:
            continue
        ports.append(
            {
                "port": p.get("port"),
                "target_port": p.get("targetPort"),
                "protocol": p.get("protocol"),
            }
        )
    svc_type = spec.get("type") or "ClusterIP"
    # MCP summary stores Service type in the status string field.
    plain = raw.get("status") if isinstance(raw.get("status"), str) else None
    if plain and plain.strip() in {"ClusterIP", "NodePort", "LoadBalancer", "ExternalName"}:
        svc_type = plain.strip()
    return {
        "name": name,
        "namespace": namespace,
        "type": svc_type,
        "selector": _as_dict(spec.get("selector")),
        "ports": ports,
        "labels": _as_dict(meta.get("labels")),
    }


def extract_daemonset(raw: dict[str, Any]) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else _as_dict(raw)
    meta = _as_dict(raw.get("metadata"))
    spec = _as_dict(raw.get("spec"))
    status = _as_dict(raw.get("status"))
    name = str(meta.get("name") or raw.get("name") or "")
    namespace = str(meta.get("namespace") or raw.get("namespace") or "")
    selector = _as_dict(_as_dict(spec.get("selector")).get("matchLabels"))
    desired = int(status.get("desiredNumberScheduled") or 0)
    ready = int(status.get("numberReady") or 0)
    plain = raw.get("status") if isinstance(raw.get("status"), str) else None
    ready_n, desired_n = _parse_ready_fraction(plain)
    if ready_n is not None and desired_n is not None:
        ready = ready_n
        desired = desired_n
    return {
        "name": name,
        "namespace": namespace,
        "kind": "DaemonSet",
        "desired": desired,
        "available": ready,
        "ready": ready,
        "selector": selector,
        "labels": _as_dict(meta.get("labels")),
    }


def extract_event(raw: dict[str, Any]) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else _as_dict(raw)
    meta = _as_dict(raw.get("metadata"))
    involved = _as_dict(raw.get("involvedObject"))
    return {
        "namespace": meta.get("namespace") or "",
        "type": raw.get("type") or "",
        "reason": raw.get("reason") or "",
        "message": (raw.get("message") or "")[:300],
        "count": int(raw.get("count") or 1),
        "object_kind": involved.get("kind") or "",
        "object_name": involved.get("name") or "",
        "last_timestamp": raw.get("lastTimestamp") or meta.get("creationTimestamp"),
    }


def _owner_name(pod: dict[str, Any], kind: str) -> str | None:
    for ref in pod.get("owner_refs") or []:
        if not isinstance(ref, dict):
            ref = _as_dict(ref)
        if ref.get("kind") == kind:
            return ref.get("name")
    for ref in pod.get("owner_refs") or []:
        if not isinstance(ref, dict):
            ref = _as_dict(ref)
        if ref.get("kind") == "ReplicaSet" and kind == "Deployment":
            name = ref.get("name") or ""
            m = re.match(r"^(.*)-[a-z0-9]{5,10}$", name)
            return m.group(1) if m else name
    return None


def _pods_named_like(controller_name: str, ns: str, pods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fallback when MCP summary omits selectors/labels: match pod name prefix."""
    if not controller_name:
        return []
    prefix = f"{controller_name}-"
    return [
        p
        for p in pods
        if p.get("namespace") == ns
        and (p.get("name") == controller_name or str(p.get("name") or "").startswith(prefix))
    ]


def build_workloads(
    namespace: str,
    services: list[dict[str, Any]],
    deployments: list[dict[str, Any]],
    daemonsets: list[dict[str, Any]],
    pods: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build Service→Deployment→Pod (or DaemonSet→Pod) chains."""
    workloads: list[dict[str, Any]] = []
    used_pods: set[tuple[str, str]] = set()
    compact = namespace in COMPACT_NAMESPACES or namespace == "all"

    deps_by_ns: dict[str, list[dict[str, Any]]] = {}
    for d in deployments:
        deps_by_ns.setdefault(d["namespace"], []).append(d)

    for svc in services:
        ns = svc["namespace"]
        if compact and svc["name"] in {"kubernetes"}:
            continue
        matching_pods = [
            p
            for p in pods
            if p["namespace"] == ns and _labels_match(svc.get("selector"), p.get("labels"))
        ]
        matching_deps = [
            d
            for d in deps_by_ns.get(ns, [])
            if _labels_match(svc.get("selector"), d.get("selector"))
            or _labels_match(svc.get("selector"), d.get("labels"))
            or (
                matching_pods
                and any(_labels_match(d.get("selector"), p.get("labels")) for p in matching_pods)
            )
        ]
        # MCP summary objects have empty selectors — fall back to same-name linking.
        if not matching_deps:
            matching_deps = [d for d in deps_by_ns.get(ns, []) if d.get("name") == svc.get("name")]
        if not matching_pods:
            matching_pods = _pods_named_like(svc.get("name") or "", ns, pods)

        dep = matching_deps[0] if matching_deps else None
        chain_pods = matching_pods
        if dep:
            dep_pods = [
                p
                for p in pods
                if p["namespace"] == ns and _labels_match(dep.get("selector"), p.get("labels"))
            ]
            if not dep_pods:
                dep_pods = _pods_named_like(dep.get("name") or "", ns, pods)
            if dep_pods:
                chain_pods = dep_pods

        pod_healths = [p["health"] for p in chain_pods]
        if dep:
            dep_health = compute_deployment_health(dep["desired"], dep["available"], pod_healths)
            deployment_payload = {**dep, "health": dep_health}
        else:
            deployment_payload = None
            dep_health = (
                "critical"
                if any(h == "critical" for h in pod_healths)
                else "degraded"
                if any(h == "degraded" for h in pod_healths)
                else "healthy"
                if chain_pods
                else "unknown"
            )

        for p in chain_pods:
            used_pods.add((p["namespace"], p["name"]))

        workloads.append(
            {
                "id": f"svc/{ns}/{svc['name']}",
                "kind": "Service",
                "name": svc["name"],
                "namespace": ns,
                "health": dep_health
                if deployment_payload
                else (
                    "critical"
                    if any(h == "critical" for h in pod_healths)
                    else "degraded"
                    if pod_healths and any(h != "healthy" for h in pod_healths)
                    else "healthy"
                    if chain_pods
                    else "unknown"
                ),
                "service": svc,
                "deployment": deployment_payload,
                "controller": deployment_payload,
                "pods": chain_pods if not compact else chain_pods[:8],
                "pod_count": len(chain_pods),
                "compact": compact,
            }
        )

    covered_deps = {
        (w["deployment"]["namespace"], w["deployment"]["name"])
        for w in workloads
        if w.get("deployment")
    }
    for dep in deployments:
        key = (dep["namespace"], dep["name"])
        if key in covered_deps:
            continue
        chain_pods = [
            p
            for p in pods
            if p["namespace"] == dep["namespace"]
            and _labels_match(dep.get("selector"), p.get("labels"))
        ]
        if not chain_pods:
            chain_pods = _pods_named_like(dep.get("name") or "", dep["namespace"], pods)
        for p in chain_pods:
            used_pods.add((p["namespace"], p["name"]))
        pod_healths = [p["health"] for p in chain_pods]
        dep_health = compute_deployment_health(dep["desired"], dep["available"], pod_healths)
        workloads.append(
            {
                "id": f"deploy/{dep['namespace']}/{dep['name']}",
                "kind": "Deployment",
                "name": dep["name"],
                "namespace": dep["namespace"],
                "health": dep_health,
                "service": None,
                "deployment": {**dep, "health": dep_health},
                "controller": {**dep, "health": dep_health, "kind": "Deployment"},
                "pods": chain_pods if not compact else chain_pods[:8],
                "pod_count": len(chain_pods),
                "compact": compact,
            }
        )

    for ds in daemonsets:
        chain_pods = [
            p
            for p in pods
            if p["namespace"] == ds["namespace"]
            and (
                _labels_match(ds.get("selector"), p.get("labels"))
                or _owner_name(p, "DaemonSet") == ds["name"]
            )
        ]
        for p in chain_pods:
            used_pods.add((p["namespace"], p["name"]))
        pod_healths = [p["health"] for p in chain_pods]
        ds_health = compute_deployment_health(ds["desired"], ds["available"], pod_healths)
        workloads.append(
            {
                "id": f"ds/{ds['namespace']}/{ds['name']}",
                "kind": "DaemonSet",
                "name": ds["name"],
                "namespace": ds["namespace"],
                "health": ds_health,
                "service": None,
                "deployment": None,
                "controller": {**ds, "health": ds_health},
                "pods": chain_pods if not compact else chain_pods[:6],
                "pod_count": len(chain_pods),
                "compact": True,
            }
        )

    orphans = [p for p in pods if (p["namespace"], p["name"]) not in used_pods]
    if orphans:
        pod_healths = [p["health"] for p in orphans]
        health = (
            "critical"
            if any(h == "critical" for h in pod_healths)
            else "degraded"
            if any(h == "degraded" for h in pod_healths)
            else "healthy"
        )
        workloads.append(
            {
                "id": f"orphan/{namespace}",
                "kind": "Pods",
                "name": "Other pods",
                "namespace": namespace if namespace != "all" else "multi",
                "health": health,
                "service": None,
                "deployment": None,
                "controller": None,
                "pods": orphans if not compact else orphans[:12],
                "pod_count": len(orphans),
                "compact": compact,
            }
        )

    order = {"critical": 0, "degraded": 1, "unknown": 2, "healthy": 3}
    workloads.sort(key=lambda w: (order.get(w["health"], 9), w["namespace"], w["name"]))
    return workloads


async def _kubectl_json(
    mcp: KubernetesMCPClient,
    resource_type: str,
    *,
    namespace: str | None = None,
    all_namespaces: bool = False,
) -> list[dict[str, Any]]:
    args: dict[str, Any] = {"resourceType": resource_type, "output": "json"}
    if all_namespaces:
        args["allNamespaces"] = True
    elif namespace:
        args["namespace"] = namespace
    raw = await mcp.call_tool("kubectl_get", args)
    return _items(parse_k8s_json(raw))


async def observability_topology(namespace: str = "ops-assistant") -> dict[str, Any]:
    """Build topology JSON for the Cluster Health dashboard (no Bedrock)."""
    ns = (namespace or "ops-assistant").strip() or "ops-assistant"
    if ns not in ALLOWED_NAMESPACES:
        ns = "ops-assistant"

    _load_env()
    kubeconfig = _resolve_kubeconfig()
    metrics = fetch_metrics()

    try:
        async with KubernetesMCPClient(kubeconfig=kubeconfig) as mcp:
            nodes_raw = await _kubectl_json(mcp, "nodes")
            all_ns = ns == "all"
            target_ns = None if all_ns else ns

            pods_raw = await _kubectl_json(
                mcp, "pods", namespace=target_ns, all_namespaces=all_ns
            )
            services_raw = await _kubectl_json(
                mcp, "services", namespace=target_ns, all_namespaces=all_ns
            )
            deployments_raw = await _kubectl_json(
                mcp, "deployments", namespace=target_ns, all_namespaces=all_ns
            )
            daemonsets_raw: list[dict[str, Any]] = []
            if all_ns or ns in COMPACT_NAMESPACES:
                daemonsets_raw = await _kubectl_json(
                    mcp, "daemonsets", namespace=target_ns, all_namespaces=all_ns
                )
            events_raw = await _kubectl_json(
                mcp, "events", namespace=target_ns, all_namespaces=all_ns
            )
    except Exception as exc:  # noqa: BLE001
        return {
            "cluster": {
                "status": "critical",
                "nodes_ready": 0,
                "nodes_total": 0,
                "pods_running": 0,
                "pods_total": 0,
                "unhealthy_pods": 0,
                "alerts": 0,
                "namespace": ns,
                "detail": str(exc),
            },
            "nodes": [],
            "workloads": [],
            "events": [],
            "relationships": [],
            "updated_at": _now_iso(),
            "bedrock_used": False,
        }

    nodes = [extract_node(n, metrics) for n in nodes_raw]
    pods = [extract_pod(p, metrics) for p in pods_raw]
    services = [extract_service(s) for s in services_raw]
    if all_ns:
        services = [
            s for s in services if not (s["namespace"] == "default" and s["name"] == "kubernetes")
        ]
    deployments = [extract_deployment(d) for d in deployments_raw]
    daemonsets = [extract_daemonset(d) for d in daemonsets_raw]

    counts: dict[str, int] = {}
    for p in pods:
        if p.get("node"):
            counts[p["node"]] = counts.get(p["node"], 0) + 1
    for n in nodes:
        n["pod_count"] = counts.get(n["name"], 0)

    for d in deployments:
        owned = [
            p
            for p in pods
            if p["namespace"] == d["namespace"] and _labels_match(d.get("selector"), p.get("labels"))
        ]
        d["health"] = compute_deployment_health(
            d["desired"], d["available"], [p["health"] for p in owned]
        )

    workloads = build_workloads(ns, services, deployments, daemonsets, pods)

    relationships = []
    for w in workloads:
        if w.get("service") and w.get("deployment"):
            relationships.append(
                {
                    "from": f"service/{w['namespace']}/{w['service']['name']}",
                    "to": f"deployment/{w['namespace']}/{w['deployment']['name']}",
                    "type": "selects",
                }
            )
        ctrl = w.get("deployment") or w.get("controller")
        if ctrl:
            kind = (ctrl.get("kind") or "Deployment").lower()
            for p in w.get("pods") or []:
                relationships.append(
                    {
                        "from": f"{kind}/{w['namespace']}/{ctrl['name']}",
                        "to": f"pod/{p['namespace']}/{p['name']}",
                        "type": "owns",
                    }
                )

    events = [extract_event(e) for e in events_raw]
    events.sort(key=lambda e: e.get("last_timestamp") or "", reverse=True)
    events = events[:40]

    pods_running = sum(1 for p in pods if p.get("phase") == "Running")
    pods_total = len(pods)
    unhealthy = sum(1 for p in pods if p.get("health") in {"critical", "degraded"})
    nodes_ready = sum(1 for n in nodes if n.get("status") == "Ready")
    cluster_status = compute_cluster_health(nodes, pods, deployments)
    alerts = int(metrics.get("alerts") or 0)

    return {
        "cluster": {
            "status": cluster_status,
            "nodes_ready": nodes_ready,
            "nodes_total": len(nodes),
            "pods_running": pods_running,
            "pods_total": pods_total,
            "unhealthy_pods": unhealthy,
            "alerts": alerts,
            "namespace": ns,
        },
        "nodes": nodes,
        "workloads": workloads,
        "services": services,
        "deployments": deployments,
        "pods": pods,
        "events": events,
        "relationships": relationships,
        "updated_at": _now_iso(),
        "bedrock_used": False,
    }
