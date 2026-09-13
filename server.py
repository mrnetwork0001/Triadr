"""
Triadr - FastAPI control plane.

Serves the Next.js visualiser: MCP tool catalogue, app connection status, run
launch, and a live Server-Sent Events stream of every gate decision as it
happens. Runs execute on a worker thread so the stream stays responsive while
the saga is mid-flight.

    pip install -r requirements.txt
    uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from env import load_env

load_env()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents import ReliabilityLogger, TriadrOrchestrator
from agents.planner import default_instruction, plan_from_instruction
from mcp_servers import MCPRegistry
from risk_gate import ChaosProfile, FaultType, ReliabilityGate


SCENARIOS: Dict[str, Dict[str, Any]] = {
    "clean": {"label": "Clean run", "description": "All three apps healthy."},
    "chaos": {"label": "Chaos storm", "description": "~75% of calls fail on first attempt; the gate heals them."},
    "rollback": {"label": "Stripe outage", "description": "Stripe is hard-down after the approval card is posted - the saga rolls back."},
    "rejected": {"label": "Reviewer rejects", "description": "The team rejects the payout; no money moves."},
}

app = FastAPI(
    title="Triadr",
    version="1.0.0",
    description="Self-Healing Multi-App Agent & Reliability Engine - GitHub + Telegram + Stripe",
)
# The front end normally proxies /api/* server-side (see next.config.js), so CORS is
# not on the critical path. It is opened anyway for deployments where the browser
# talks to this API directly - set TRIADR_CORS_ORIGINS to a comma-separated list.
_CORS = [o.strip() for o in os.environ.get("TRIADR_CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS or ["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Run manager
# ---------------------------------------------------------------------------


class Run:
    """One workflow execution plus its live event stream."""

    def __init__(self, run_id: str, instruction: str, scenario: str) -> None:
        self.id = run_id
        self.instruction = instruction
        self.scenario = scenario
        self.created_at = time.time()
        self.state = "queued"
        self.events: List[Dict[str, Any]] = []
        self.result: Optional[Dict[str, Any]] = None
        self.attestation: Optional[Dict[str, Any]] = None
        self.entries: List[Dict[str, Any]] = []
        self._subscribers: List[queue.Queue] = []
        self._lock = threading.Lock()

    def publish(self, event: Dict[str, Any]) -> None:
        with self._lock:
            self.events.append(event)
            subscribers = list(self._subscribers)
        for sub in subscribers:
            try:
                sub.put_nowait(event)
            except queue.Full:
                pass

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=2048)
        with self._lock:
            backlog = list(self.events)
            self._subscribers.append(q)
        for event in backlog:  # late subscribers still see the whole run
            q.put_nowait(event)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def summary(self) -> Dict[str, Any]:
        return {
            "run_id": self.id,
            "instruction": self.instruction,
            "scenario": self.scenario,
            "state": self.state,
            "created_at": self.created_at,
            "ok": self.result.get("ok") if self.result else None,
            "summary": self.result.get("summary") if self.result else None,
            "event_count": len(self.events),
        }


class RunManager:
    def __init__(self, max_runs: int = 50) -> None:
        self._runs: Dict[str, Run] = {}
        self._order: List[str] = []
        self._max = max_runs
        self._lock = threading.Lock()

    def create(self, instruction: str, scenario: str) -> Run:
        run = Run(f"run_{uuid.uuid4().hex[:12]}", instruction, scenario)
        with self._lock:
            self._runs[run.id] = run
            self._order.append(run.id)
            while len(self._order) > self._max:
                self._runs.pop(self._order.pop(0), None)
        return run

    def get(self, run_id: str) -> Run:
        run = self._runs.get(run_id)
        if run is None:
            raise HTTPException(404, f"unknown run '{run_id}'")
        return run

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self._runs[rid].summary() for rid in reversed(self._order) if rid in self._runs]


runs = RunManager()


def _build(scenario: str, auto_approve: bool, chaos_seed: Optional[int]) -> tuple:
    config = {
        "clean": (None, True, None),
        "chaos": (ChaosProfile.storm(seed=chaos_seed or 7), True, None),
        "rollback": (None, True, ("stripe.release_escrow", FaultType.SERVER_ERROR)),
        "rejected": (None, False, None),
    }
    if scenario not in config:
        raise HTTPException(400, f"unknown scenario '{scenario}' - expected one of {sorted(config)}")
    chaos, approve, forced = config[scenario]
    registry = MCPRegistry(auto_approve=approve and auto_approve)
    if forced:
        registry.force_fault(*forced)
    return registry, chaos


def _execute(run: Run, auto_approve: bool, chaos_seed: Optional[int], persist: bool) -> None:
    registry, chaos = _build(run.scenario, auto_approve, chaos_seed)
    orchestrator = TriadrOrchestrator(
        registry=registry, chaos=chaos, run_id=run.id, on_event=run.publish
    )
    orchestrator.logger.subscribe(lambda entry: run.publish({
        "event": "audit.entry", "run_id": run.id, "ts": entry.ts,
        "index": entry.index, "kind": entry.kind, "digest": entry.digest[:16],
    }))
    run.state = "running"
    run.publish({"event": "run.queued", "run_id": run.id, "scenario": run.scenario})
    try:
        result = orchestrator.run(run.instruction)
        run.result = result.to_dict()
        run.attestation = result.attestation
        run.entries = [e.to_dict() for e in orchestrator.logger.entries]
        run.state = "completed" if result.ok else "rolled_back"
        if persist:
            orchestrator.persist()
    except Exception as exc:  # never leave a stream hanging
        run.state = "error"
        run.publish({"event": "run.error", "run_id": run.id, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        run.publish({"event": "stream.close", "run_id": run.id, "state": run.state})


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    instruction: str = Field(default_factory=default_instruction, max_length=2000)
    scenario: str = Field(default="clean")
    auto_approve: bool = True
    chaos_seed: Optional[int] = None
    persist: bool = True


class ChaosRequest(BaseModel):
    enabled: bool = True
    seed: int = 1337
    rate_limit: float = Field(default=0.30, ge=0, le=1)
    timeout: float = Field(default=0.15, ge=0, le=1)
    server_error: float = Field(default=0.15, ge=0, le=1)
    network_partition: float = Field(default=0.06, ge=0, le=1)
    schema_drift: float = Field(default=0.05, ge=0, le=1)
    auth_expired: float = Field(default=0.04, ge=0, le=1)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "service": "triadr", "version": "1.0.0", "ts": time.time()}


@app.get("/api/apps")
def apps() -> Dict[str, Any]:
    status = MCPRegistry().status()
    status["scenarios"] = [{"id": k, **v} for k, v in SCENARIOS.items()]
    status["default_instruction"] = default_instruction()
    return status


@app.get("/api/tools")
def tools() -> Dict[str, Any]:
    catalogue = MCPRegistry().list_tools()
    by_app: Dict[str, List[Dict[str, Any]]] = {}
    for tool in catalogue:
        by_app.setdefault(tool["_triadr"]["app"], []).append(tool)
    return {"count": len(catalogue), "tools": catalogue, "by_app": by_app}


@app.post("/api/plan")
def plan(request: RunRequest) -> Dict[str, Any]:
    """Preview the saga without executing it."""
    return plan_from_instruction(request.instruction).to_dict()


@app.post("/api/run")
def start_run(request: RunRequest) -> Dict[str, Any]:
    if request.scenario not in SCENARIOS:
        raise HTTPException(400, f"unknown scenario '{request.scenario}'")
    run = runs.create(request.instruction, request.scenario)
    threading.Thread(
        target=_execute,
        args=(run, request.auto_approve, request.chaos_seed, request.persist),
        daemon=True,
        name=f"triadr-{run.id}",
    ).start()
    return {"run_id": run.id, "stream": f"/api/runs/{run.id}/stream", "scenario": run.scenario}


@app.get("/api/runs")
def list_runs() -> Dict[str, Any]:
    return {"runs": runs.list()}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    run = runs.get(run_id)
    return {**run.summary(), "result": run.result, "attestation": run.attestation}


@app.get("/api/runs/{run_id}/audit")
def get_audit(run_id: str) -> Dict[str, Any]:
    run = runs.get(run_id)
    if not run.entries:
        raise HTTPException(409, "audit chain is not sealed yet - the run is still in flight")
    logger = ReliabilityLogger(run_id)
    from agents.reliability_logger import LogEntry

    logger._entries = [LogEntry(**e) for e in run.entries]
    return {
        "run_id": run_id,
        "verification": logger.verify(),
        "attestation": run.attestation,
        "entries": run.entries,
    }


@app.get("/api/runs/{run_id}/stream")
async def stream(run_id: str) -> StreamingResponse:
    run = runs.get(run_id)
    subscriber = run.subscribe()

    async def generator():
        loop = asyncio.get_running_loop()
        try:
            yield f"event: hello\ndata: {json.dumps(run.summary())}\n\n"
            while True:
                try:
                    event = await loop.run_in_executor(None, subscriber.get, True, 20.0)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield f"event: {event.get('event', 'message')}\ndata: {json.dumps(event, default=str)}\n\n"
                if event.get("event") == "stream.close":
                    break
        finally:
            run.unsubscribe(subscriber)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/benchmark")
def benchmark(iterations: int = 20_000) -> Dict[str, Any]:
    iterations = max(1_000, min(iterations, 200_000))
    return ReliabilityGate().benchmark(iterations)


@app.post("/api/chaos/preview")
def chaos_preview(request: ChaosRequest) -> Dict[str, Any]:
    profile = ChaosProfile(
        enabled=request.enabled, seed=request.seed, rate_limit=request.rate_limit,
        timeout=request.timeout, server_error=request.server_error,
        network_partition=request.network_partition, schema_drift=request.schema_drift,
        auth_expired=request.auth_expired,
    )
    if profile.total_probability > 0.95:
        raise HTTPException(400, "total fault probability must stay below 0.95 or no call can ever succeed")
    return profile.to_dict()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
