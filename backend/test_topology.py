"""Unit tests for topology health logic and relationships (no Bedrock / live cluster)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent
AGENT_DIR = BACKEND_DIR.parent / "agent"
for path in (BACKEND_DIR, AGENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from main import app  # noqa: E402
from topology import (  # noqa: E402
    build_workloads,
    compute_cluster_health,
    compute_deployment_health,
    compute_pod_health,
    extract_node,
    extract_pod,
    parse_k8s_json,
)

client = TestClient(app)


def test_pod_health_running() -> None:
    assert (
        compute_pod_health(
            {"phase": "Running", "status": "Running", "ready": "1/1", "restarts": 0}
        )
        == "healthy"
    )


def test_pod_health_crashloop_critical() -> None:
    assert (
        compute_pod_health(
            {
                "phase": "Running",
                "status": "CrashLoopBackOff",
                "crash_loop": True,
                "ready": "0/1",
                "restarts": 6,
            }
        )
        == "critical"
    )


def test_pod_health_pending_degraded() -> None:
    assert compute_pod_health({"phase": "Pending", "status": "Pending", "ready": "0/1"}) == "degraded"


def test_deployment_healthy() -> None:
    assert compute_deployment_health(1, 1, ["healthy"]) == "healthy"


def test_deployment_degraded_unavailable_replicas() -> None:
    assert compute_deployment_health(2, 1, ["healthy"]) == "degraded"


def test_deployment_critical_zero_available() -> None:
    assert compute_deployment_health(1, 0, ["critical"]) == "critical"


def test_cluster_not_ready_node_critical() -> None:
    nodes = [{"status": "Ready"}, {"status": "NotReady"}]
    pods = [{"health": "healthy", "phase": "Running", "status": "Running", "ready": "1/1"}]
    assert compute_cluster_health(nodes, pods, []) == "critical"


def test_cluster_crashloop_critical() -> None:
    nodes = [{"status": "Ready"}]
    pods = [
        {
            "health": "critical",
            "phase": "Running",
            "status": "CrashLoopBackOff",
            "crash_loop": True,
            "ready": "0/1",
        }
    ]
    assert compute_cluster_health(nodes, pods, []) == "critical"


def test_service_deployment_pod_relationship() -> None:
    services = [
        {
            "name": "backend",
            "namespace": "ops-assistant",
            "selector": {"app": "backend"},
            "type": "ClusterIP",
            "ports": [],
            "labels": {},
        }
    ]
    deployments = [
        {
            "name": "backend",
            "namespace": "ops-assistant",
            "desired": 1,
            "available": 1,
            "ready": 1,
            "selector": {"app": "backend"},
            "labels": {"app": "backend"},
        }
    ]
    pods = [
        {
            "name": "backend-abc",
            "namespace": "ops-assistant",
            "phase": "Running",
            "status": "Running",
            "ready": "1/1",
            "restarts": 0,
            "labels": {"app": "backend"},
            "health": "healthy",
            "owner_refs": [],
        }
    ]
    workloads = build_workloads("ops-assistant", services, deployments, [], pods)
    assert len(workloads) == 1
    w = workloads[0]
    assert w["service"]["name"] == "backend"
    assert w["deployment"]["name"] == "backend"
    assert w["pods"][0]["name"] == "backend-abc"
    assert w["health"] == "healthy"


def test_namespace_filter_keeps_ops_assistant_demo_crashloop() -> None:
    services: list = []
    deployments = [
        {
            "name": "crashloop-demo",
            "namespace": "ops-assistant-demo",
            "desired": 1,
            "available": 0,
            "ready": 0,
            "selector": {"app": "crashloop-demo"},
            "labels": {"app": "crashloop-demo"},
        }
    ]
    pods = [
        {
            "name": "crashloop-demo-xyz",
            "namespace": "ops-assistant-demo",
            "phase": "Running",
            "status": "CrashLoopBackOff",
            "crash_loop": True,
            "ready": "0/1",
            "restarts": 8,
            "labels": {"app": "crashloop-demo"},
            "health": "critical",
            "owner_refs": [],
        }
    ]
    workloads = build_workloads("ops-assistant-demo", services, deployments, [], pods)
    assert workloads[0]["health"] == "critical"
    assert workloads[0]["pods"][0]["status"] == "CrashLoopBackOff"


def test_extract_pod_crashloop_from_k8s_json() -> None:
    raw = {
        "metadata": {
            "name": "boom-1",
            "namespace": "ops-assistant-demo",
            "creationTimestamp": "2026-08-24T10:00:00Z",
            "labels": {"app": "crashloop-demo"},
        },
        "spec": {"nodeName": "ip-10-0-1-237", "containers": [{"name": "boom"}]},
        "status": {
            "phase": "Running",
            "containerStatuses": [
                {
                    "name": "boom",
                    "ready": False,
                    "restartCount": 4,
                    "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                    "lastState": {"terminated": {"reason": "Error", "exitCode": 1}},
                }
            ],
        },
    }
    pod = extract_pod(raw)
    assert pod["status"] == "CrashLoopBackOff"
    assert pod["health"] == "critical"
    assert pod["restarts"] == 4
    assert pod["last_termination_reason"] == "Error"


def _ready_status_dict() -> dict:
    return {
        "conditions": [{"type": "Ready", "status": "True"}],
        "addresses": [{"type": "InternalIP", "address": "10.0.0.163"}],
    }


def _not_ready_status_dict() -> dict:
    return {
        "conditions": [{"type": "Ready", "status": "False"}],
        "addresses": [{"type": "InternalIP", "address": "10.0.1.141"}],
    }


def test_extract_node_full_kubernetes_object() -> None:
    node = extract_node(
        {
            "metadata": {
                "name": "ip-10-0-0-163",
                "labels": {"node-role.kubernetes.io/control-plane": ""},
            },
            "status": _ready_status_dict(),
            "spec": {"unschedulable": False},
        }
    )
    assert node["name"] == "ip-10-0-0-163"
    assert node["status"] == "Ready"
    assert node["health"] == "healthy"
    assert node["internal_ip"] == "10.0.0.163"
    assert node["role"] == "control-plane"


def test_extract_node_full_kubernetes_not_ready() -> None:
    node = extract_node(
        {
            "metadata": {"name": "ip-10-0-1-141", "labels": {}},
            "status": _not_ready_status_dict(),
        }
    )
    assert node["status"] == "NotReady"
    assert node["health"] == "critical"
    assert node["internal_ip"] == "10.0.1.141"


def test_extract_node_mcp_simplified_ready() -> None:
    """Confirmed live MCP shape: top-level name + status string Ready."""
    node = extract_node(
        {
            "name": "ip-10-0-0-163",
            "namespace": "",
            "kind": "Node",
            "status": "Ready",
            "createdAt": "2026-08-18T08:47:40Z",
        }
    )
    assert node["name"] == "ip-10-0-0-163"
    assert node["status"] == "Ready"
    assert node["health"] == "healthy"
    assert node["internal_ip"] is None
    assert node["cpu_percent"] is None
    assert node["memory_percent"] is None


def test_extract_node_mcp_simplified_not_ready() -> None:
    node = extract_node(
        {
            "name": "ip-10-0-0-44",
            "namespace": "",
            "kind": "Node",
            "status": "NotReady",
            "createdAt": "2026-08-24T13:06:36Z",
        }
    )
    assert node["name"] == "ip-10-0-0-44"
    assert node["status"] == "NotReady"
    assert node["health"] == "critical"
    assert node["internal_ip"] is None


def test_extract_node_status_as_json_string() -> None:
    import json

    node = extract_node(
        {
            "metadata": {"name": "ip-10-0-1-237", "labels": {}},
            "status": json.dumps(_ready_status_dict()),
        }
    )
    assert node["name"] == "ip-10-0-1-237"
    assert node["status"] == "Ready"
    assert node["health"] == "healthy"
    assert node["internal_ip"] == "10.0.0.163"


def test_extract_node_status_malformed_string() -> None:
    node = extract_node(
        {
            "name": "ip-10-0-0-99",
            "kind": "Node",
            "status": "bogus-not-a-condition",
        }
    )
    assert node["name"] == "ip-10-0-0-99"
    assert node["status"] == "Unknown"
    assert node["health"] == "unknown"
    assert node["internal_ip"] is None


def test_extract_node_status_missing() -> None:
    node = extract_node({"metadata": {"name": "orphan-node"}})
    assert node["name"] == "orphan-node"
    assert node["status"] == "Unknown"
    assert node["health"] == "unknown"
    assert node["internal_ip"] is None


def test_extract_node_status_null() -> None:
    node = extract_node({"name": "null-status-node", "status": None})
    assert node["name"] == "null-status-node"
    assert node["status"] == "Unknown"
    assert node["health"] == "unknown"


def test_parse_k8s_json_list() -> None:
    payload = parse_k8s_json('{"kind":"List","items":[{"metadata":{"name":"a"}}]}')
    assert payload["items"][0]["metadata"]["name"] == "a"


def test_topology_endpoint_mocked_no_bedrock() -> None:
    fake = {
        "cluster": {
            "status": "healthy",
            "nodes_ready": 2,
            "nodes_total": 2,
            "pods_running": 2,
            "pods_total": 2,
            "unhealthy_pods": 0,
            "alerts": 0,
            "namespace": "ops-assistant",
        },
        "nodes": [],
        "workloads": [],
        "events": [],
        "relationships": [],
        "bedrock_used": False,
        "updated_at": "2026-08-24T12:00:00+00:00",
    }
    with patch("main.observability_topology", new=AsyncMock(return_value=fake)) as mock_topo:
        response = client.get("/observability/topology?namespace=ops-assistant")
    assert response.status_code == 200
    body = response.json()
    assert body["bedrock_used"] is False
    assert body["cluster"]["status"] == "healthy"
    mock_topo.assert_awaited_once()


def test_topology_rejects_unknown_namespace() -> None:
    response = client.get("/observability/topology?namespace=evil-ns")
    assert response.status_code == 400


def test_rbac_still_read_only_for_dashboard() -> None:
    text = (BACKEND_DIR.parent / "k8s" / "rbac.yaml").read_text(encoding="utf-8")
    assert '"delete"' not in text
    assert "cluster-admin" not in text
    # scale patch remains; no create for pods/deployments
    assert "pods" in text
    assert 'verbs: ["get", "list", "watch"]' in text
