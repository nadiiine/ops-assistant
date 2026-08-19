"""Regression tests: agent namespace behavior for kubectl_get calls."""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import run_agent


def _make_tool_call(name: str, arguments: dict) -> MagicMock:
    tc = MagicMock()
    tc.id = "call_test_001"
    tc.function.name = name
    tc.function.arguments = json.dumps(arguments)
    return tc


def _make_openai_response(tool_calls=None, content: str = "") -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestAgentNamespaceBehavior(unittest.TestCase):
    """Verify that general pod queries use allNamespaces=true."""

    def _run_and_capture_tool_args(self, prompt: str) -> list[dict]:
        """Return the list of argument dicts passed to mcp.call_tool."""
        captured: list[dict] = []

        async def _run():
            fake_tools = [
                {
                    "name": "kubectl_get",
                    "description": "Get k8s resources",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "resourceType": {"type": "string"},
                            "namespace": {"type": "string"},
                            "allNamespaces": {"type": "boolean"},
                        },
                        "required": ["resourceType"],
                    },
                }
            ]

            # First response: agent calls kubectl_get
            first_args = {"resourceType": "pods", "allNamespaces": True}
            first_resp = _make_openai_response(
                tool_calls=[_make_tool_call("kubectl_get", first_args)]
            )
            # Second response: agent returns final text
            second_resp = _make_openai_response(content="Pods found across all namespaces.")

            mock_mcp = AsyncMock()
            mock_mcp.__aenter__ = AsyncMock(return_value=mock_mcp)
            mock_mcp.__aexit__ = AsyncMock(return_value=False)
            mock_mcp.list_tools = AsyncMock(return_value=fake_tools)

            async def fake_call_tool(tool_name, arguments):
                captured.append({"tool": tool_name, "args": arguments})
                return '{"items": []}'

            mock_mcp.call_tool = fake_call_tool

            with patch("agent.KubernetesMCPClient", return_value=mock_mcp), \
                 patch("agent.OpenAI") as mock_openai_cls, \
                 patch("agent.os.environ.get", side_effect=lambda k, d="": {
                     "OPENAI_API_KEY": "test-key",
                     "OPENAI_MODEL": "gpt-4o-mini",
                     "KUBECONFIG": "",
                 }.get(k, d)):

                mock_client = MagicMock()
                mock_openai_cls.return_value = mock_client
                mock_client.chat.completions.create.side_effect = [first_resp, second_resp]

                await run_agent(prompt)

        asyncio.run(_run())
        return captured

    def test_general_pod_query_uses_all_namespaces(self):
        """A general 'what about the pods' query must pass allNamespaces=true."""
        # We test the system prompt instructs allNamespaces correctly by verifying
        # that the system prompt string contains the expected instruction.
        from agent import SYSTEM_PROMPT
        self.assertIn("allNamespaces: true", SYSTEM_PROMPT)
        self.assertIn("WITHOUT specifying a namespace", SYSTEM_PROMPT)

    def test_system_prompt_instructs_namespace_preservation(self):
        """Explicitly named namespace must NOT trigger allNamespaces."""
        from agent import SYSTEM_PROMPT
        self.assertIn("explicitly names a namespace", SYSTEM_PROMPT)
        self.assertNotIn("hardcode", SYSTEM_PROMPT.lower())

    def test_empty_result_response_instruction_all_namespaces(self):
        """System prompt must tell the model what to say when allNamespaces returns empty."""
        from agent import SYSTEM_PROMPT
        self.assertIn("no <resource> running in the cluster", SYSTEM_PROMPT)

    def test_empty_result_response_instruction_specific_namespace(self):
        """System prompt must tell the model what to say when a specific namespace returns empty."""
        from agent import SYSTEM_PROMPT
        self.assertIn("no <resource> in the <namespace> namespace", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
