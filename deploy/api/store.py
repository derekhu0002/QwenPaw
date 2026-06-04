from __future__ import annotations

import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def derive_shadow_hash(client_id: str, *parts: Any) -> str:
    payload = {
        "client_id": client_id,
        "parts": [str(part) for part in parts],
        "protocol": "security-center-v1",
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def derive_lockdown_shadow_hash(
    client_id: str,
    *,
    previous_shadow_hash: str,
    trace_id: str,
    edge_timestamp_ns: int,
    tool_name: str,
) -> str:
    return derive_shadow_hash(
        client_id,
        "lockdown-shadow",
        previous_shadow_hash,
        trace_id,
        edge_timestamp_ns,
        tool_name,
    )


def require_edge_timestamp_ns(payload: dict[str, Any]) -> int:
    raw_value = payload.get("edge_timestamp_ns")
    if raw_value is None:
        raise ValueError("edge_timestamp_ns is required for anti-cheat alert timing")
    edge_timestamp_ns = int(raw_value)
    if edge_timestamp_ns <= 0:
        raise ValueError("edge_timestamp_ns must be a positive integer")
    return edge_timestamp_ns


class SecurityCenterStore:
    def __init__(self, store_path: Path) -> None:
        self._path = store_path
        self._lock = asyncio.Lock()
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    @classmethod
    def from_default(cls) -> "SecurityCenterStore":
        base = Path(__file__).resolve().parent / "data" / "security-center-store.json"
        return cls(base)

    def _bootstrap_state(self) -> dict[str, Any]:
        return {
            "version": 1,
            "clients": {},
            "rejections": {},
            "lockdowns": {},
            "alerts": [],
        }

    def _read_locked(self) -> dict[str, Any]:
        if not self._path.exists():
            return self._bootstrap_state()
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return self._bootstrap_state()
        for key in ("clients", "rejections", "lockdowns", "alerts"):
            payload.setdefault(key, {} if key != "alerts" else [])
        return payload

    def _write_locked(self, state: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp.replace(self._path)

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    async def _broadcast(self, alert: dict[str, Any]) -> None:
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            queue.put_nowait(alert)

    async def recovery_handshake(self, payload: dict[str, Any]) -> dict[str, Any]:
        client_id = str(payload.get("client_id") or payload.get("session_id") or "unknown-client")
        local_hash = str(payload.get("local_hash") or payload.get("checkpoint_hash") or "")
        trace_id = str(payload.get("trace_id") or "")
        requested_at_ns = int(payload.get("requested_at_ns") or time.time_ns())
        async with self._lock:
            state = self._read_locked()
            client_state = state["clients"].setdefault(
                client_id,
                {
                    "shadow_hash": derive_shadow_hash(client_id, "bootstrap"),
                    "trust_state": "UNKNOWN",
                    "last_trace_id": None,
                    "updated_at_ns": requested_at_ns,
                },
            )
            shadow_hash = str(client_state.get("shadow_hash") or derive_shadow_hash(client_id, "bootstrap"))
            trust_state = "ALIGNED" if local_hash and local_hash == shadow_hash else "DIVERGED"
            client_state.update(
                {
                    "trust_state": trust_state,
                    "last_handshake_trace_id": trace_id or client_state.get("last_handshake_trace_id"),
                    "updated_at_ns": requested_at_ns,
                },
            )
            state["clients"][client_id] = client_state
            self._write_locked(state)
        return {
            "client_id": client_id,
            "shadow_hash": shadow_hash,
            "trust_state": trust_state,
            "recovery_required": trust_state != "ALIGNED",
            "requested_at_ns": requested_at_ns,
            "last_trace_id": client_state.get("last_trace_id"),
            "handshake_status": "ready",
        }

    async def record_rejection(self, payload: dict[str, Any]) -> dict[str, Any]:
        client_id = str(payload.get("client_id") or payload.get("session_id") or payload.get("user_id") or "unknown-client")
        nonce = str(
            payload.get("security_rejection_nonce")
            or payload.get("Security_Rejection_Nonce")
            or derive_shadow_hash(client_id, payload.get("trace_id"), payload.get("tool_name"))[:32]
        )
        trace_id = str(payload.get("trace_id") or payload.get("run_id") or nonce)
        edge_timestamp_ns = require_edge_timestamp_ns(payload)
        binding_hash = str(
            payload.get("security_rejection_nonce_binding_hash")
            or derive_shadow_hash(client_id, trace_id, nonce, payload.get("current_hash") or "")
        )
        received_at_ns = time.time_ns()
        record = {
            "client_id": client_id,
            "trace_id": trace_id,
            "nonce": nonce,
            "binding_hash": binding_hash,
            "tool_name": str(payload.get("tool_name") or payload.get("high_risk_tool_name") or "unknown-tool"),
            "prompt_text": str(payload.get("prompt_text") or ""),
            "user_id": str(payload.get("user_id") or payload.get("request_user_id") or "unknown-user"),
            "edge_timestamp_ns": edge_timestamp_ns,
            "received_at_ns": received_at_ns,
            "voucher": f"Voucher:{nonce}",
            "severity": "critical",
            "status": "rejected",
        }
        alert = {
            "type": "SECURITY_REJECTION",
            "client_id": client_id,
            "trace_id": trace_id,
            "nonce": nonce,
            "edge_timestamp_ns": edge_timestamp_ns,
            "received_at_ns": received_at_ns,
            "alert_latency_ms": max(0, int((received_at_ns - edge_timestamp_ns) / 1_000_000)),
            "severity": "critical",
            "message": f"Security_Rejection_Nonce {nonce} received for {record['tool_name']}",
        }
        async with self._lock:
            state = self._read_locked()
            state["rejections"][nonce] = record
            client_state = state["clients"].setdefault(client_id, {})
            client_state.update(
                {
                    "last_rejection_nonce": nonce,
                    "trust_state": "REJECTED",
                    "updated_at_ns": record["received_at_ns"],
                    "last_trace_id": trace_id,
                },
            )
            state["clients"][client_id] = client_state
            state["alerts"].append(alert)
            state["alerts"] = state["alerts"][-250:]
            self._write_locked(state)
        await self._broadcast(alert)
        return {
            "ack_status": "received",
            "client_id": client_id,
            "trace_id": trace_id,
            "nonce": nonce,
            "voucher": record["voucher"],
            "voucher_url": f"/security-center/v1/operator/vouchers/{nonce}",
            "rejection_url": f"/security-center/v1/operator/rejections/{nonce}",
            "stream_url": "/security-center/v1/operator/stream",
            "alert_latency_ms": alert["alert_latency_ms"],
        }

    async def record_lockdown(self, payload: dict[str, Any]) -> dict[str, Any]:
        client_id = str(payload.get("client_id") or payload.get("session_id") or payload.get("user_id") or "unknown-client")
        trace_id = str(payload.get("trace_id") or payload.get("run_id") or derive_shadow_hash(client_id, "lockdown")[:12])
        local_hash = str(payload.get("current_hash") or payload.get("local_hash") or derive_shadow_hash(client_id, "local"))
        prior_hash = str(payload.get("prior_hash") or derive_shadow_hash(client_id, "prior"))
        edge_timestamp_ns = require_edge_timestamp_ns(payload)
        received_at_ns = time.time_ns()
        async with self._lock:
            state = self._read_locked()
            client_state = state["clients"].setdefault(client_id, {})
            previous_shadow_hash = str(client_state.get("shadow_hash") or derive_shadow_hash(client_id, "shadow-head"))
            fork_point_event_id = str(
                client_state.get("last_trace_id")
                or client_state.get("last_handshake_trace_id")
                or f"shadow-anchor::{client_id}"
            )
            cloud_shadow_hash = derive_lockdown_shadow_hash(
                client_id,
                previous_shadow_hash=previous_shadow_hash,
                trace_id=trace_id,
                edge_timestamp_ns=edge_timestamp_ns,
                tool_name=str(payload.get("tool_name") or payload.get("high_risk_tool_name") or "unknown-tool"),
            )
            timeline = {
                "client_id": client_id,
                "local_hash_curve": [
                    {"sequence": 0, "label": "anchor", "hash": prior_hash},
                    {"sequence": 1, "label": "tampered-head", "hash": local_hash},
                ],
                "cloud_shadow_curve": [
                    {"sequence": 0, "label": "shadow-anchor", "hash": previous_shadow_hash},
                    {"sequence": 1, "label": "shadow-head", "hash": cloud_shadow_hash},
                ],
                "fork_point": {
                    "event_id": fork_point_event_id,
                    "sequence": 0,
                    "local_hash": local_hash,
                    "cloud_shadow_hash": cloud_shadow_hash,
                },
            }
            record = {
                "client_id": client_id,
                "trace_id": trace_id,
                "tool_name": str(payload.get("tool_name") or payload.get("high_risk_tool_name") or "unknown-tool"),
                "user_id": str(payload.get("user_id") or payload.get("request_user_id") or "unknown-user"),
                "edge_timestamp_ns": edge_timestamp_ns,
                "received_at_ns": received_at_ns,
                "local_hash": local_hash,
                "cloud_shadow_hash": cloud_shadow_hash,
                "prior_hash": prior_hash,
                "timeline": timeline,
                "trust_state": "UNTRUSTED",
                "recovery_required": True,
                "handshake_status": "required",
            }
            client_state.update(
                {
                    "shadow_hash": cloud_shadow_hash,
                    "trust_state": "UNTRUSTED",
                    "updated_at_ns": record["received_at_ns"],
                    "last_trace_id": trace_id,
                    "last_fork_point_event_id": fork_point_event_id,
                },
            )
            state["clients"][client_id] = client_state
            state["lockdowns"][trace_id] = record
            alert = {
                "type": "AUDIT_LOCKDOWN",
                "client_id": client_id,
                "trace_id": trace_id,
                "edge_timestamp_ns": edge_timestamp_ns,
                "received_at_ns": received_at_ns,
                "alert_latency_ms": max(0, int((received_at_ns - edge_timestamp_ns) / 1_000_000)),
                "severity": "critical",
                "message": f"UNTRUSTED recovery required for {client_id}",
                "fork_point_event_id": fork_point_event_id,
            }
            state["alerts"].append(alert)
            state["alerts"] = state["alerts"][-250:]
            self._write_locked(state)
        await self._broadcast(alert)
        return {
            "ack_status": "received",
            "client_id": client_id,
            "trace_id": trace_id,
            "shadow_hash": cloud_shadow_hash,
            "timeline_url": f"/security-center/v1/operator/timelines/{client_id}",
            "trust_state": "UNTRUSTED",
            "alert_latency_ms": alert["alert_latency_ms"],
        }

    async def overview(self) -> dict[str, Any]:
        async with self._lock:
            state = self._read_locked()
        rejections = list(state["rejections"].values())[-8:]
        lockdowns = list(state["lockdowns"].values())[-8:]
        clients = [
            {"client_id": client_id, **client_state}
            for client_id, client_state in state["clients"].items()
        ]
        return {
            "service": "security_center_backend_api",
            "client_count": len(clients),
            "rejection_count": len(state["rejections"]),
            "lockdown_count": len(state["lockdowns"]),
            "clients": clients,
            "rejections": rejections,
            "lockdowns": lockdowns,
            "alerts": state["alerts"][-12:],
        }

    async def voucher(self, nonce: str) -> dict[str, Any] | None:
        async with self._lock:
            state = self._read_locked()
            record = state["rejections"].get(nonce)
        if record is None:
            return None
        return {
            "nonce": nonce,
            "voucher": record["voucher"],
            "binding_hash": record["binding_hash"],
            "tool_name": record["tool_name"],
            "trace_id": record["trace_id"],
            "client_id": record["client_id"],
        }

    async def rejection(self, nonce: str) -> dict[str, Any] | None:
        async with self._lock:
            state = self._read_locked()
            return state["rejections"].get(nonce)

    async def timeline(self, client_id: str) -> dict[str, Any] | None:
        async with self._lock:
            state = self._read_locked()
            lockdowns = [
                record
                for record in state["lockdowns"].values()
                if record.get("client_id") == client_id
            ]
            client_state = state["clients"].get(client_id)
        if lockdowns:
            latest = lockdowns[-1]
            return {
                "client_id": client_id,
                "trust_state": latest["trust_state"],
                "recovery_required": latest["recovery_required"],
                **latest["timeline"],
            }
        if client_state is None:
            return None
        shadow_hash = str(client_state.get("shadow_hash") or derive_shadow_hash(client_id, "shadow-head"))
        return {
            "client_id": client_id,
            "trust_state": client_state.get("trust_state", "UNKNOWN"),
            "recovery_required": client_state.get("trust_state") == "UNTRUSTED",
            "local_hash_curve": [{"sequence": 0, "label": "anchor", "hash": shadow_hash}],
            "cloud_shadow_curve": [{"sequence": 0, "label": "shadow-head", "hash": shadow_hash}],
            "fork_point": None,
        }
