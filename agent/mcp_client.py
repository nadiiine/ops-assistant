"""MCP client wrapper for the Kubernetes MCP server."""

from __future__ import annotations

import json
import os
import shutil
import sys
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class KubernetesMCPClient:
    """Connect to mcp-server-kubernetes over stdio."""

    def __init__(self, kubeconfig: str | None = None) -> None:
        self.kubeconfig = kubeconfig or os.environ.get("KUBECONFIG", "")
        self._stack: AsyncExitStack | None = None
        self.session: ClientSession | None = None

    async def __aenter__(self) -> "KubernetesMCPClient":
        env = os.environ.copy()
        if self.kubeconfig:
            env["KUBECONFIG"] = self.kubeconfig

        npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"
        if sys.platform == "win32" and shutil.which(npx_cmd) is None:
            npx_cmd = "npx"

        server_params = StdioServerParameters(
            command=npx_cmd,
            args=["-y", "mcp-server-kubernetes"],
            env=env,
        )

        self._stack = AsyncExitStack()
        read, write = await self._stack.enter_async_context(stdio_client(server_params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self.session = None
        self._stack = None

    async def list_tools(self) -> list[dict[str, Any]]:
        assert self.session is not None
        result = await self.session.list_tools()
        tools: list[dict[str, Any]] = []
        for tool in result.tools:
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": tool.inputSchema,
                }
            )
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        assert self.session is not None
        result = await self.session.call_tool(name, arguments or {})
        parts: list[str] = []
        for block in result.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
            else:
                parts.append(str(block))
        return "\n".join(parts) if parts else json.dumps({"isError": result.isError})
