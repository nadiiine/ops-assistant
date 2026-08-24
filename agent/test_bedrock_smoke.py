"""Live Bedrock smoke test. Skips when AWS credentials are unavailable."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import DEFAULT_MODEL, DEFAULT_REGION  # noqa: E402

load_dotenv(Path(__file__).resolve().parent / ".env")


def test_bedrock_text_smoke() -> None:
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
    except ImportError:
        pytest.skip("boto3 is not installed")

    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or DEFAULT_REGION
    model = os.environ.get("BEDROCK_MODEL", DEFAULT_MODEL)
    candidates = [model]
    if model == "amazon.nova-2-lite-v1:0":
        candidates.append("us.amazon.nova-2-lite-v1:0")

    try:
        client = boto3.client("bedrock-runtime", region_name=region)
        sts = boto3.client("sts", region_name=region)
        sts.get_caller_identity()
    except (NoCredentialsError, ClientError, BotoCoreError) as exc:
        pytest.skip(f"AWS credentials/Bedrock unavailable: {exc}")

    last_error: Exception | None = None
    response = None
    used_model = model
    for candidate in candidates:
        try:
            response = client.converse(
                modelId=candidate,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": "Reply with exactly the word ok and nothing else."}],
                    }
                ],
                inferenceConfig={"temperature": 0.0, "maxTokens": 32},
            )
            used_model = candidate
            break
        except ClientError as exc:
            last_error = exc
            code = exc.response.get("Error", {}).get("Code", "")
            message = str(exc).lower()
            if code == "AccessDeniedException":
                pytest.skip(f"Bedrock InvokeModel denied for this identity: {exc}")
            if "inference profile" in message or code == "ValidationException":
                continue
            raise

    if response is None:
        raise AssertionError(f"Bedrock smoke failed for {candidates}: {last_error}")

    text_blocks = [
        block.get("text", "")
        for block in response.get("output", {}).get("message", {}).get("content", [])
        if isinstance(block, dict)
    ]
    text = "\n".join(text_blocks).strip().lower()
    assert text, f"empty Bedrock response from {used_model}"
    assert "ok" in text, f"unexpected Bedrock text from {used_model}: {text!r}"
