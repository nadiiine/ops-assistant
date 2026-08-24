"""SNS Terraform configuration smoke checks (no AWS calls)."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_sns_tf_least_privilege_publish_only() -> None:
    text = (ROOT / "infra" / "sns.tf").read_text(encoding="utf-8")
    assert "sns:Publish" in text
    assert "SNSFullAccess" not in text
    assert "ops-assistant" in text or "project_name" in text
    assert "alert_email" in text
    assert "sns_alert_topic_arn" in text


def test_monitoring_values_include_alert_rules() -> None:
    text = (ROOT / "k8s" / "monitoring" / "values.yaml").read_text(encoding="utf-8")
    for alert in (
        "NodeNotReady",
        "PodCrashLooping",
        "PodHighRestartRate",
        "DeploymentReplicasUnavailable",
        "HighNodeCPU",
        "HighNodeMemory",
    ):
        assert alert in text
    assert "sns_configs" in text
    assert "sigv4" in text


def test_demo_crashloop_manifest_exists() -> None:
    demo = ROOT / "k8s" / "demo" / "crashloop-demo.yaml"
    assert demo.exists()
    text = demo.read_text(encoding="utf-8")
    assert "ops-assistant-demo" in text
    assert "exit 1" in text or "CrashLoop" in text or "crashloop" in text.lower()
    assert "kube-system" not in text.split("---")[-1]
    assert "kind: Namespace" in text
    assert "crashloop-demo" in text


def test_rbac_has_no_delete_permissions() -> None:
    text = (ROOT / "k8s" / "rbac.yaml").read_text(encoding="utf-8")
    assert "verbs: [\"delete\"]" not in text
    assert '"delete"' not in text
    assert "cluster-admin" not in text
    assert "kubectl_delete" not in text
    assert "patch" in text  # scale only
    assert "deployments/scale" in text


def test_prometheus_url_matches_truncated_helm_service() -> None:
    from prometheus_tool import DEFAULT_PROMETHEUS_URL

    assert "ops-monitor-kube-prometheu-prometheus" in DEFAULT_PROMETHEUS_URL
    cfg = (ROOT / "k8s" / "configmap.yaml").read_text(encoding="utf-8")
    assert "ops-monitor-kube-prometheu-prometheus" in cfg
