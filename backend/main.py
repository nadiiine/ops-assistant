"""FastAPI backend for the Kubernetes Ops Assistant."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from service import chat, cluster_status

app = FastAPI(title="Kubernetes Ops Assistant", version="1.0.0")

_cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _cors_origins.split(",") if origin.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    answer: str
    tools_used: list[str]
    blocked_tools: list[str] = []


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/cluster/status")
async def get_cluster_status() -> dict[str, Any]:
    return await cluster_status()


@app.post("/chat", response_model=ChatResponse)
async def post_chat(body: ChatRequest) -> ChatResponse:
    try:
        result = await chat(body.message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(
        answer=result.answer,
        tools_used=result.tools_used,
        blocked_tools=result.blocked_tools,
    )
