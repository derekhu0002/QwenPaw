from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .store import SecurityCenterStore


class RecoveryHandshakeRequest(BaseModel):
    client_id: str = Field(..., min_length=1)
    trace_id: str | None = None
    local_hash: str = Field(..., min_length=1)
    checkpoint_hash: str | None = None
    requested_at_ns: int | None = None


class RejectionUplinkRequest(BaseModel):
    client_id: str | None = None
    trace_id: str | None = None
    run_id: str | None = None
    session_id: str | None = None
    user_id: str = Field(..., min_length=1)
    tool_name: str = Field(..., min_length=1)
    prompt_text: str | None = None
    current_hash: str | None = None
    edge_timestamp_ns: int = Field(..., ge=1)
    security_rejection_nonce: str | None = None
    Security_Rejection_Nonce: str | None = None
    security_rejection_nonce_binding_hash: str | None = None


class LockdownUplinkRequest(BaseModel):
    client_id: str | None = None
    trace_id: str | None = None
    run_id: str | None = None
    session_id: str | None = None
    user_id: str = Field(..., min_length=1)
    tool_name: str = Field(..., min_length=1)
    current_hash: str = Field(..., min_length=1)
    prior_hash: str | None = None
    edge_timestamp_ns: int = Field(..., ge=1)


def create_app(store: SecurityCenterStore | None = None) -> FastAPI:
    app = FastAPI(
        title="QwenPaw Security Center API",
        version="0.1.0",
        summary="Independent Security Center backend API for recovery handshakes, vouchers, and realtime alerts.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    service_store = store or SecurityCenterStore.from_default()

    @app.get("/")
    async def root() -> dict[str, Any]:
        return {
            "service": "security_center_backend_api",
            "health": "ok",
            "stream": "/security-center/v1/operator/stream",
            "overview": "/security-center/v1/operator/overview",
        }

    @app.get("/security-center/v1/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "service": "security_center_backend_api"}

    @app.post("/security-center/v1/recovery/handshake")
    async def recovery_handshake(body: RecoveryHandshakeRequest) -> dict[str, Any]:
        return await service_store.recovery_handshake(body.model_dump(mode="json"))

    @app.post("/security-center/v1/uplinks/rejections")
    async def uplink_rejection(body: RejectionUplinkRequest) -> dict[str, Any]:
        return await service_store.record_rejection(body.model_dump(mode="json"))

    @app.post("/security-center/v1/uplinks/lockdowns")
    async def uplink_lockdown(body: LockdownUplinkRequest) -> dict[str, Any]:
        return await service_store.record_lockdown(body.model_dump(mode="json"))

    @app.get("/security-center/v1/operator/overview")
    async def operator_overview() -> dict[str, Any]:
        return await service_store.overview()

    @app.get("/security-center/v1/operator/rejections/{nonce}")
    async def operator_rejection(nonce: str) -> dict[str, Any]:
        record = await service_store.rejection(nonce)
        if record is None:
            raise HTTPException(status_code=404, detail="rejection not found")
        return record

    @app.get("/security-center/v1/operator/vouchers/{nonce}")
    async def operator_voucher(nonce: str) -> dict[str, Any]:
        voucher = await service_store.voucher(nonce)
        if voucher is None:
            raise HTTPException(status_code=404, detail="voucher not found")
        return voucher

    @app.get("/security-center/v1/operator/timelines/{client_id}")
    async def operator_timeline(client_id: str) -> dict[str, Any]:
        timeline = await service_store.timeline(client_id)
        if timeline is None:
            raise HTTPException(status_code=404, detail="timeline not found")
        return timeline

    @app.get("/security-center/v1/operator/stream")
    async def operator_stream() -> StreamingResponse:
        queue = await service_store.subscribe()

        async def event_stream():
            try:
                yield "event: ready\ndata: {\"service\":\"security_center_backend_api\"}\n\n"
                while True:
                    try:
                        alert = await asyncio.wait_for(queue.get(), timeout=15.0)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    yield f"event: security-alert\ndata: {json.dumps(alert, ensure_ascii=False)}\n\n"
            finally:
                await service_store.unsubscribe(queue)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "deploy.api.app:app",
        host=os.environ.get("SECURITY_CENTER_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("SECURITY_CENTER_API_PORT", "8091")),
        reload=False,
    )
