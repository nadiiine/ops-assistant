"""Tests for prometheus_query validation and safe predefined queries."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from guardrails import check_tool_call
from prometheus_tool import PREDEFINED_QUERIES, execute_prometheus_query, validate_prometheus_query_args


def test_prometheus_query_allowlisted() -> None:
    allowed, reason = check_tool_call("prometheus_query", {"query_type": "top_pod_cpu"})
    assert allowed, reason


def test_prometheus_query_rejects_unknown_type() -> None:
    allowed, reason = check_tool_call("prometheus_query", {"query_type": "drop_all_tables"})
    assert not allowed
    assert "Unsupported" in reason or "query_type" in reason


def test_prometheus_query_rejects_freeform_promql() -> None:
    ok, reason = validate_prometheus_query_args(
        {"query_type": "top_pod_cpu", "query": "up{job=\"evil\"}"}
    )
    assert not ok
    assert "Free-form" in reason


def test_predefined_queries_cover_ops_use_cases() -> None:
    required = {
        "top_pod_cpu",
        "top_pod_memory",
        "node_memory_usage",
        "pod_restarts_1h",
        "deployment_unavailable_replicas",
        "pods_crashloop",
    }
    assert required.issubset(PREDEFINED_QUERIES.keys())


def test_execute_prometheus_query_mocked() -> None:
    fake = json.dumps({"status": "success", "data": {"result": [{"metric": {"pod": "a"}, "value": [1, "0.2"]}]}}).encode()

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return fake

    with patch("prometheus_tool.urllib.request.urlopen", return_value=FakeResp()):
        out = json.loads(execute_prometheus_query({"query_type": "top_pod_cpu"}))
    assert out["ok"] is True
    assert out["query_type"] == "top_pod_cpu"
    assert out["result"][0]["metric"]["pod"] == "a"


def test_system_prompt_includes_diagnosis_guidance() -> None:
    from agent import SYSTEM_PROMPT

    assert "Cluster health" in SYSTEM_PROMPT or "diagnosis" in SYSTEM_PROMPT.lower()
    assert "prometheus_query" in SYSTEM_PROMPT
    assert "likely" in SYSTEM_PROMPT.lower()
    assert "Batch independent" in SYSTEM_PROMPT
