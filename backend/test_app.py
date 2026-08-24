"""Backend API tests that do not call Bedrock or Kubernetes."""

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

from agent import AgentResult  # noqa: E402
from main import app  # noqa: E402

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_cluster_status_mocked() -> None:
    fake = {
        "connected": True,
        "ready_nodes": 2,
        "total_nodes": 2,
        "detail": "ip-10-0-0-163 Ready",
    }
    with patch("main.cluster_status", new=AsyncMock(return_value=fake)):
        response = client.get("/cluster/status")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["ready_nodes"] == 2


def test_chat_mocked() -> None:
    result = AgentResult(
        answer="Both nodes are Ready.",
        tools_used=["kubectl_get"],
        blocked_tools=[],
    )
    with patch("main.chat", new=AsyncMock(return_value=result)):
        response = client.post("/chat", json={"message": "Show me the Kubernetes nodes."})
    assert response.status_code == 200
    body = response.json()
    assert "Ready" in body["answer"]
    assert body["tools_used"] == ["kubectl_get"]


def test_observability_summary_mocked() -> None:
    fake = {
        "status": "healthy",
        "nodes_ready": 2,
        "nodes_total": 2,
        "unhealthy_pods": 0,
        "recent_alerts": 0,
    }
    with patch("main.observability_summary", new=AsyncMock(return_value=fake)):
        response = client.get("/observability/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["nodes_ready"] == 2
