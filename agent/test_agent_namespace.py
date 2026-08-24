"""Regression tests: agent namespace behavior for kubectl_get calls."""

from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import MAX_TOOL_ROUNDS, SYSTEM_PROMPT


class TestAgentNamespaceBehavior(unittest.TestCase):
    """Verify that general pod queries use allNamespaces=true."""

    def test_general_pod_query_uses_all_namespaces(self):
        """A general 'what about the pods' query must pass allNamespaces=true."""
        self.assertIn("allNamespaces: true", SYSTEM_PROMPT)
        self.assertIn("WITHOUT specifying a namespace", SYSTEM_PROMPT)

    def test_system_prompt_instructs_namespace_preservation(self):
        """Explicitly named namespace must NOT trigger allNamespaces."""
        self.assertIn("explicitly names a namespace", SYSTEM_PROMPT)
        self.assertNotIn("hardcode", SYSTEM_PROMPT.lower())

    def test_empty_result_response_instruction_all_namespaces(self):
        """System prompt must tell the model what to say when allNamespaces returns empty."""
        self.assertIn("no <resource> running in the cluster", SYSTEM_PROMPT)

    def test_empty_result_response_instruction_specific_namespace(self):
        """System prompt must tell the model what to say when a specific namespace returns empty."""
        self.assertIn("no <resource> in the <namespace> namespace", SYSTEM_PROMPT)

    def test_max_tool_rounds_is_five(self):
        self.assertEqual(MAX_TOOL_ROUNDS, 5)


if __name__ == "__main__":
    unittest.main()
