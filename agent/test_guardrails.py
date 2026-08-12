"""Unit tests for Phase 1 guardrail policy (7 cases)."""

import unittest

from guardrails import check_tool_call


class TestGuardrails(unittest.TestCase):
    def test_allows_kubectl_get(self):
        allowed, reason = check_tool_call("kubectl_get", {"resourceType": "pods"})
        self.assertTrue(allowed, reason)

    def test_allows_kubectl_describe(self):
        allowed, reason = check_tool_call(
            "kubectl_describe", {"resourceType": "deployment", "name": "nginx"}
        )
        self.assertTrue(allowed, reason)

    def test_allows_kubectl_logs(self):
        allowed, reason = check_tool_call("kubectl_logs", {"name": "nginx-abc", "namespace": "default"})
        self.assertTrue(allowed, reason)

    def test_allows_kubectl_scale(self):
        allowed, reason = check_tool_call(
            "kubectl_scale",
            {"name": "nginx", "namespace": "default", "replicas": 3},
        )
        self.assertTrue(allowed, reason)

    def test_blocks_kubectl_delete(self):
        allowed, reason = check_tool_call(
            "kubectl_delete",
            {"resourceType": "deployment", "name": "crashy", "namespace": "default"},
        )
        self.assertFalse(allowed)
        self.assertIn("blocked", reason.lower())

    def test_blocks_cleanup_pods(self):
        allowed, reason = check_tool_call("cleanup_pods", {"namespace": "default"})
        self.assertFalse(allowed)
        self.assertIn("blocked", reason.lower())

    def test_blocks_kubectl_generic(self):
        allowed, reason = check_tool_call("kubectl_generic", {"command": "delete deployment crashy"})
        self.assertFalse(allowed)
        self.assertIn("blocked", reason.lower())


if __name__ == "__main__":
    unittest.main()
