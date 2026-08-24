"""Unit tests for Bedrock agent loop limits, truncation, and retries."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import (  # noqa: E402
    MAX_TOOL_ROUNDS,
    _bedrock_tool_config,
    _converse,
    _is_transient_error,
    _sanitize_schema,
    _truncate_tool_output,
    run_agent,
)


def test_truncate_tool_output_keeps_short_text() -> None:
    assert _truncate_tool_output("ok") == "ok"


def test_truncate_tool_output_caps_huge_payload() -> None:
    huge = "x" * 20_000
    truncated = _truncate_tool_output(huge)
    assert len(truncated) < len(huge)
    assert truncated.endswith("characters]")
    assert truncated.startswith("x")


def test_sanitize_schema_drops_unsupported_fields() -> None:
    cleaned = _sanitize_schema(
        {
            "type": "object",
            "properties": {"resourceType": {"type": "string"}},
            "additionalProperties": False,
            "$schema": "http://json-schema.org/draft-07/schema#",
        }
    )
    assert "additionalProperties" not in cleaned
    assert "$schema" not in cleaned
    assert cleaned["properties"]["resourceType"]["type"] == "string"


def test_bedrock_tool_config_maps_mcp_schema() -> None:
    config = _bedrock_tool_config(
        [
            {
                "name": "kubectl_get",
                "description": "Get resources",
                "inputSchema": {
                    "type": "object",
                    "properties": {"resourceType": {"type": "string"}},
                    "required": ["resourceType"],
                },
            }
        ]
    )
    tool = config["tools"][0]["toolSpec"]
    assert tool["name"] == "kubectl_get"
    assert tool["inputSchema"]["json"]["type"] == "object"
    assert config["toolChoice"] == {"auto": {}}


def test_transient_error_detection() -> None:
    throttled = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
        "Converse",
    )
    assert _is_transient_error(throttled)
    assert not _is_transient_error(RuntimeError("AccessDeniedException"))


def test_converse_retries_once() -> None:
    client = MagicMock()
    client.converse.side_effect = [
        ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "slow down"}},
            "Converse",
        ),
        {"output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}}},
    ]
    with patch("agent.time.sleep"):
        response = _converse(client, modelId="amazon.nova-2-lite-v1:0", messages=[])
    assert response["output"]["message"]["content"][0]["text"] == "ok"
    assert client.converse.call_count == 2


def test_converse_does_not_retry_permanent_errors() -> None:
    client = MagicMock()
    client.converse.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "Converse",
    )
    with pytest.raises(ClientError):
        _converse(client, modelId="amazon.nova-2-lite-v1:0", messages=[])
    assert client.converse.call_count == 1


def test_run_agent_stops_after_max_tool_rounds() -> None:
    tool_response = {
        "stopReason": "tool_use",
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tooluse_1",
                            "name": "kubectl_get",
                            "input": {"resourceType": "pods", "allNamespaces": True},
                        }
                    }
                ],
            }
        },
    }

    mock_mcp = AsyncMock()
    mock_mcp.__aenter__.return_value = mock_mcp
    mock_mcp.__aexit__.return_value = False
    mock_mcp.list_tools = AsyncMock(
        return_value=[
            {
                "name": "kubectl_get",
                "description": "Get resources",
                "inputSchema": {"type": "object", "properties": {"resourceType": {"type": "string"}}},
            }
        ]
    )
    mock_mcp.call_tool = AsyncMock(return_value='{"items":[]}')

    mock_client = MagicMock()
    mock_client.converse.return_value = tool_response

    with (
        patch("agent.KubernetesMCPClient", return_value=mock_mcp),
        patch("agent._bedrock_client", return_value=mock_client),
        patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "bedrock",
                "AWS_REGION": "us-east-1",
                "BEDROCK_MODEL": "amazon.nova-2-lite-v1:0",
                "KUBECONFIG": "",
            },
            clear=False,
        ),
    ):
        result = asyncio.run(run_agent("what about the pods"))

    assert result.answer == "Agent stopped after maximum tool iterations."
    assert mock_client.converse.call_count == MAX_TOOL_ROUNDS
    assert mock_mcp.call_tool.await_count == MAX_TOOL_ROUNDS
    assert result.tools_used == ["kubectl_get"] * MAX_TOOL_ROUNDS


def test_run_agent_appends_tool_result_as_user_message() -> None:
    first_response = {
        "stopReason": "tool_use",
        "output": {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "tooluse_42",
                            "name": "kubectl_get",
                            "input": {"resourceType": "nodes"},
                        }
                    }
                ],
            }
        },
    }
    second_response = {
        "stopReason": "end_turn",
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "Both nodes are Ready."}],
            }
        },
    }

    mock_mcp = AsyncMock()
    mock_mcp.__aenter__.return_value = mock_mcp
    mock_mcp.__aexit__.return_value = False
    mock_mcp.list_tools = AsyncMock(
        return_value=[
            {
                "name": "kubectl_get",
                "description": "Get resources",
                "inputSchema": {"type": "object", "properties": {"resourceType": {"type": "string"}}},
            }
        ]
    )
    mock_mcp.call_tool = AsyncMock(return_value="node-a Ready")

    mock_client = MagicMock()
    mock_client.converse.side_effect = [first_response, second_response]

    with (
        patch("agent.KubernetesMCPClient", return_value=mock_mcp),
        patch("agent._bedrock_client", return_value=mock_client),
        patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "bedrock",
                "AWS_REGION": "us-east-1",
                "BEDROCK_MODEL": "amazon.nova-2-lite-v1:0",
                "KUBECONFIG": "",
            },
            clear=False,
        ),
    ):
        result = asyncio.run(run_agent("Show me the Kubernetes nodes."))

    second_call_messages = mock_client.converse.call_args_list[1].kwargs["messages"]
    tool_result_message = next(
        message
        for message in second_call_messages
        if message.get("role") == "user"
        and message.get("content")
        and "toolResult" in message["content"][0]
    )
    tool_result = tool_result_message["content"][0]["toolResult"]
    assert tool_result["toolUseId"] == "tooluse_42"
    assert tool_result["content"][0]["json"]["result"] == "node-a Ready"
    assert result.answer == "Both nodes are Ready."
    assert result.tools_used == ["kubectl_get"]
