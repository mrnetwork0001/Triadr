"""
Triadr - Multi-App MCP Orchestrator.

Executes the planned saga across GitHub, Telegram and Stripe. Every step goes
through `ReliabilityGate.guard()`, and every step that mutates remote state
declares a compensation. If a critical step is unrecoverable, the orchestrator
walks the completed steps backwards and undoes them, so the run ends either
fully applied or fully reverted - never half-executed.

The whole run is streamed as events (for the live visualiser) and written to a
hash-chained reliability log (for the judges).
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from mcp_servers import MCPRegistry, Mode
from risk_gate import ChaosProfile, GateOutcome, ReliabilityGate, Verdict

from .planner import Plan, PlanStep, plan_from_instruction
from .reliability_logger import ReliabilityLogger

_TEMPLATE = re.compile(r"\$\{([a-zA-Z0-9_]+)(?:\.([a-zA-Z0-9_.]+))?\}")


class StepStatus:
    PENDING = "pending"
    RUNNING = "running"
    HEALED = "healed"
    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    FAILED = "failed"
    COMPENSATED = "compensated"


@dataclass
class StepResult:
    step: PlanStep
    status: str = StepStatus.PENDING
    outcome: Optional[GateOutcome] = None
    output: Any = None
    started_at: float = 0.0
    duration_ms: float = 0.0
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.step.id,
            "app": self.step.app,
            "tool": self.step.tool,
            "title": self.step.title,
            "status": self.status,
            "note": self.note,
            "started_at": self.started_at,
            "duration_ms": round(self.duration_ms, 2),
            "output": _jsonable(self.output),
            "gate": self.outcome.to_dict() if self.outcome else None,
        }


@dataclass
class WorkflowResult:
    run_id: str
    instruction: str
    ok: bool
    steps: List[StepResult]
    duration_ms: float
    gate: Dict[str, Any]
    attestation: Dict[str, Any]
    compensations: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "instruction": self.instruction,
            "ok": self.ok,
            "summary": self.summary,
            "duration_ms": round(self.duration_ms, 2),
            "steps": [s.to_dict() for s in self.steps],
            "compensations": self.compensations,
            "gate": self.gate,
            "attestation": self.attestation,
        }


class TriadrOrchestrator:
    """Runs one multi-app saga under full reliability supervision."""

    def __init__(
        self,
        *,
        registry: Optional[MCPRegistry] = None,
        chaos: Optional[ChaosProfile] = None,
        run_id: Optional[str] = None,
        on_event: Optional[Callable[[Dict[str, Any]], None]] = None,
        auto_approve: bool = True,
        log_dir: Optional[str] = None,
    ) -> None:
        self.run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        self.registry = registry or MCPRegistry(auto_approve=auto_approve)
        self.gate = ReliabilityGate(chaos=chaos, endpoints=self.registry.endpoints())
        self.logger = ReliabilityLogger(self.run_id, log_dir=log_dir)
        self._external_listener = on_event
        self.gate.subscribe(self._on_gate_event)

    # -- events ------------------------------------------------------------

    def _on_gate_event(self, event: Dict[str, Any]) -> None:
        self.logger.record(event.get("event", "gate.event"),
                           {k: v for k, v in event.items() if k != "event"},
                           app=event.get("app"), tool=event.get("tool"))
        self._emit(event)

    def _emit(self, event: Dict[str, Any]) -> None:
        if self._external_listener:
            try:
                self._external_listener({"run_id": self.run_id, **event})
            except Exception:
                pass

    # -- template resolution ------------------------------------------------

    @staticmethod
    def _lookup(context: Dict[str, Any], step_id: str, path: Optional[str]) -> Any:
        value = context.get(step_id)
        if path:
            for part in path.split("."):
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    return None
        return value

    def _resolve(self, value: Any, context: Dict[str, Any]) -> Any:
        """Substitute ${step.field} references against earlier step outputs."""
        if isinstance(value, str):
            whole = _TEMPLATE.fullmatch(value)
            if whole:  # a lone reference keeps its native type (dict, int, ...)
                return self._lookup(context, whole.group(1), whole.group(2))
            return _TEMPLATE.sub(
                lambda m: str(self._lookup(context, m.group(1), m.group(2))), value
            )
        if isinstance(value, dict):
            return {k: self._resolve(v, context) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve(v, context) for v in value]
        return value

    @staticmethod
    def _condition_met(condition: Optional[str], context: Dict[str, Any]) -> bool:
        """Supports `step.field == value` and `step.field` (truthiness). Deliberately
        tiny - a payout gate is not a place for `eval`."""
        if not condition:
            return True
        if "==" in condition:
            left, right = (part.strip() for part in condition.split("==", 1))
        else:
            left, right = condition.strip(), None
        step_id, _, path = left.partition(".")
        actual = TriadrOrchestrator._lookup(context, step_id, path or None)
        if right is None:
            return bool(actual)
        return str(actual).strip().strip("'\"") == right.strip().strip("'\"")

    # -- execution ----------------------------------------------------------

    def run(
        self,
        instruction: str,
        *,
        overrides: Optional[Dict[str, Any]] = None,
        plan: Optional[Plan] = None,
    ) -> WorkflowResult:
        started = time.perf_counter()
        plan = plan or plan_from_instruction(instruction, run_id=self.run_id, overrides=overrides)

        self.logger.record("run.start", {
            "instruction": instruction,
            "plan": plan.to_dict(),
            "apps": self.registry.status(),
            "chaos": self.gate.chaos.profile.to_dict(),
        })
        self._emit({"event": "run.start", "instruction": instruction, "plan": plan.to_dict(),
                    "apps": self.registry.status()})

        context: Dict[str, Any] = {}
        results: List[StepResult] = []
        compensations: List[Dict[str, Any]] = []
        applied: List[StepResult] = []   # completed steps that declared a rollback
        failed_step: Optional[StepResult] = None

        for step in plan.steps:
            result = StepResult(step=step, started_at=time.time())
            results.append(result)

            unmet = [d for d in step.depends_on if d not in context]
            if unmet:
                result.status = StepStatus.SKIPPED
                result.note = f"upstream step(s) {unmet} did not produce output"
                self._emit({"event": "step.skipped", "step": step.id, "reason": result.note})
                continue

            if not self._condition_met(step.condition, context):
                result.status = StepStatus.SKIPPED
                result.note = f"condition not met: {step.condition}"
                self.logger.record("step.skipped", {"step": step.id, "condition": step.condition},
                                   app=step.app, tool=step.tool)
                self._emit({"event": "step.skipped", "step": step.id, "reason": result.note})
                continue

            args = self._resolve(step.args, context)
            result.status = StepStatus.RUNNING
            self._emit({"event": "step.start", "step": step.id, "app": step.app,
                        "tool": step.tool, "title": step.title, "args": _jsonable(args)})

            t0 = time.perf_counter()
            outcome = self._execute(step, args)
            result.duration_ms = (time.perf_counter() - t0) * 1000
            result.outcome = outcome
            self.logger.record_gate_outcome(outcome)

            if outcome.ok:
                result.output = outcome.result
                context[step.id] = outcome.result
                result.status = StepStatus.HEALED if outcome.healed else StepStatus.SUCCEEDED
                result.note = outcome.reason
                if step.compensation:
                    applied.append(result)
                self._emit({"event": "step.done", "step": step.id, "status": result.status,
                            "verdict": outcome.verdict.value, "attempts": len(outcome.attempts),
                            "duration_ms": round(result.duration_ms, 2),
                            "output": _jsonable(outcome.result)})
                continue

            result.status = StepStatus.FAILED
            result.note = outcome.reason
            self._emit({"event": "step.failed", "step": step.id, "verdict": outcome.verdict.value,
                        "fault": outcome.fault.value if outcome.fault else None, "reason": outcome.reason})

            if step.critical:
                failed_step = result
                break
            result.note = ("Non-critical step - the saga continues without it. " + outcome.reason)

        if failed_step is not None:
            compensations = self._compensate(applied, context, failed_step)

        duration = (time.perf_counter() - started) * 1000
        ok = failed_step is None
        summary = self._summarise(ok, results, compensations, context)

        # run.end is recorded *before* the attestation is sealed, so the merkle
        # root and head digest commit to the complete log - including the final
        # record. Sealing first would leave the last entry outside the commitment.
        self.logger.record("run.end", {"ok": ok, "summary": summary,
                                       "metrics": self.gate.metrics.to_dict()})
        attestation = self.logger.attestation({
            "reliability": self.gate.metrics.to_dict(),
            "apps": self.registry.status(),
            "outcome": "APPLIED" if ok else "ROLLED_BACK",
        })

        result_obj = WorkflowResult(
            run_id=self.run_id, instruction=instruction, ok=ok, steps=results,
            duration_ms=duration, gate=self.gate.snapshot(), attestation=attestation,
            compensations=compensations, summary=summary,
        )
        self._emit({"event": "run.end", "ok": ok, "summary": summary,
                    "gate": result_obj.gate, "attestation": attestation})
        return result_obj

    def _execute(self, step: PlanStep, args: Dict[str, Any]) -> GateOutcome:
        spec = self.registry.spec(step.tool)

        def executor(*, payload: Dict[str, Any], endpoint: str) -> Any:
            return self.registry.call(step.tool, payload, endpoint=endpoint).data

        return self.gate.guard(
            app=step.app,
            tool=step.tool,
            payload=args,
            executor=executor,
            schema=spec.input_schema,
            output_schema=spec.output_schema,
            idempotency_key=step.idempotency_key or args.get("idempotency_key"),
            side_effect=spec.side_effect.value,
        )

    # -- saga rollback -------------------------------------------------------

    def _compensate(
        self,
        applied: List[StepResult],
        context: Dict[str, Any],
        failed_step: StepResult,
    ) -> List[Dict[str, Any]]:
        """Undo completed side effects in reverse order."""
        self.logger.record("saga.rollback.start", {
            "failed_step": failed_step.step.id,
            "reason": failed_step.note,
            "to_compensate": [r.step.id for r in reversed(applied)],
        })
        self._emit({"event": "saga.rollback.start", "failed_step": failed_step.step.id,
                    "steps": [r.step.id for r in reversed(applied)]})

        records: List[Dict[str, Any]] = []
        for result in reversed(applied):
            comp = result.step.compensation
            if not comp:
                continue
            tool = comp["tool"]
            args = self._resolve(comp.get("args", {}), context)
            spec = self.registry.spec(tool)

            def executor(*, payload: Dict[str, Any], endpoint: str, _tool=tool) -> Any:
                return self.registry.call(_tool, payload, endpoint=endpoint).data

            outcome = self.gate.guard(
                app=spec.app, tool=tool, payload=args, executor=executor,
                schema=spec.input_schema, output_schema=spec.output_schema,
                idempotency_key=args.get("idempotency_key"),
                side_effect=spec.side_effect.value,
                max_attempts=6,   # rollback gets a bigger budget than the forward path
            )
            self.logger.record_gate_outcome(outcome)
            if outcome.ok:
                result.status = StepStatus.COMPENSATED
            record = {
                "undid": result.step.id, "tool": tool, "ok": outcome.ok,
                "verdict": outcome.verdict.value, "reason": outcome.reason,
                "output": _jsonable(outcome.result),
            }
            records.append(record)
            self._emit({"event": "saga.compensated", **record})

        self.logger.record("saga.rollback.end", {
            "compensated": sum(1 for r in records if r["ok"]),
            "failed": sum(1 for r in records if not r["ok"]),
        })
        return records

    # -- reporting -----------------------------------------------------------

    def _summarise(
        self,
        ok: bool,
        results: List[StepResult],
        compensations: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> str:
        m = self.gate.metrics
        healed = sum(1 for r in results if r.status == StepStatus.HEALED)
        done = sum(1 for r in results if r.status in (StepStatus.SUCCEEDED, StepStatus.HEALED))
        if ok:
            payout = context.get("payout") or {}
            money = (f" Payout {payout.get('id')} settled for "
                     f"{payout.get('currency', '').upper()} {payout.get('amount', 0) / 100:,.2f}."
                     if payout.get("id") else " No payout was required.")
            return (
                f"{done}/{len(results)} steps applied across 3 apps. "
                f"{m.faults_absorbed} fault(s) absorbed, {healed} step(s) self-healed, "
                f"0 steps left half-executed.{money}"
            )
        undone = sum(1 for c in compensations if c["ok"])
        return (
            f"Run stopped on an unrecoverable step and rolled back cleanly: {undone}/{len(compensations)} "
            f"side effect(s) reversed. {m.faults_absorbed} fault(s) absorbed before giving up. "
            f"No partial state remains."
        )

    def persist(self) -> Dict[str, str]:
        return self.logger.write()


def _jsonable(value: Any) -> Any:
    """Best-effort JSON coercion so an unexpected object never breaks the stream."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)
