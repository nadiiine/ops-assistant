"""Unit tests for observability summary helpers (no live cluster)."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
AGENT_DIR = BACKEND_DIR.parent / "agent"
for path in (BACKEND_DIR, AGENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from observability import (  # noqa: E402
    _count_ready_nodes,
    _count_unhealthy_pods,
    _status_label,
)


def test_count_ready_nodes() -> None:
    output = """
NAME            STATUS     ROLES           AGE   VERSION
ip-10-0-0-163   Ready      control-plane   10d   v1.31.4
ip-10-0-1-237   Ready      <none>          10d   v1.31.4
ip-10-0-1-173   NotReady   <none>          9d    v1.31.4
"""
    ready, total = _count_ready_nodes(output)
    assert ready == 2
    assert total == 3


def test_count_unhealthy_pods_detects_crashloop() -> None:
    output = """
NAMESPACE            NAME                         READY   STATUS             RESTARTS
ops-assistant        backend-abc                  1/1     Running            0
ops-assistant-demo   crashloop-demo-xyz           0/1     CrashLoopBackOff   6
kube-system          coredns-xyz                  1/1     Running            0
default              job-done                     0/1     Completed          0
"""
    assert _count_unhealthy_pods(output) == 1


def test_count_unhealthy_pods_ignores_healthy_and_succeeded() -> None:
    output = """
NAMESPACE     NAME      READY   STATUS      RESTARTS
default       web       1/1     Running     0
default       batch     0/1     Succeeded   0
"""
    assert _count_unhealthy_pods(output) == 0


def test_status_label_healthy_degraded_critical() -> None:
    assert _status_label(2, 2, 0, 0) == "healthy"
    assert _status_label(1, 2, 1, 0) == "degraded"
    assert _status_label(0, 2, 0, 0) == "critical"
    assert _status_label(2, 2, 3, 0) == "critical"
