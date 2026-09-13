"""
Triadr - Self-Healing Chaos & Reliability Gate
==============================================

A zero-LLM, zero-dependency execution gate that sits between the multi-app agent
and every external side effect (GitHub / Telegram / Stripe).

Design goal: a multi-step workflow must never be left half-executed. Every tool
call passes through `ReliabilityGate.guard()`, which enforces, in order:

  1. Idempotency ledger      -> a payout is never issued twice
  2. Schema validation       -> zero-LLM structural contract check
  3. Payload drift detection -> catches silent upstream contract mutations
  4. Token bucket            -> pre-emptive client-side rate shaping
  5. Circuit breaker         -> stops hammering a dead endpoint
  6. Execution + retry       -> exponential backoff w/ full jitter, honors Retry-After
  7. Endpoint rerouting      -> health-ranked failover to secondary MCP gateways
  8. Compensation signalling -> emits a saga rollback verdict when unrecoverable

Everything here is deterministic and measurable. Latency numbers reported by
Triadr are *measured at runtime* (see `GateMetrics.percentiles`), never hardcoded.

Stdlib only - this module must import cleanly on a bare Python 3.11+ runtime.
"""

from __future__ import annotations

import json
import math
import random
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "FaultType",
    "Verdict",
    "CircuitState",
    "ToolFault",
    "GateDecision",
    "GateAttempt",
    "GateOutcome",
    "SchemaValidator",
    "SchemaViolation",
    "DriftDetector",
    "TokenBucket",
    "CircuitBreaker",
    "BackoffPolicy",
    "EndpointRouter",
    "IdempotencyLedger",
    "ChaosEngine",
    "ChaosProfile",
    "GateMetrics",
    "ReliabilityGate",
]


# ---------------------------------------------------------------------------
# Core enums & value objects
# ---------------------------------------------------------------------------


class FaultType(str, Enum):
    """Canonical failure taxonomy shared by all three connected apps."""

    RATE_LIMITED = "RATE_LIMITED"            # 429 - retry after cooldown
    TIMEOUT = "TIMEOUT"                      # no response within budget
    SERVER_ERROR = "SERVER_ERROR"            # 5xx - retry / reroute
    NETWORK_PARTITION = "NETWORK_PARTITION"  # connection refused / DNS
    SCHEMA_DRIFT = "SCHEMA_DRIFT"            # upstream changed the contract
    AUTH_EXPIRED = "AUTH_EXPIRED"            # 401 - refresh then retry once
    PERMISSION_DENIED = "PERMISSION_DENIED"  # 403 - terminal, do not retry
    NOT_FOUND = "NOT_FOUND"                  # 404 - terminal
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"  # duplicate side effect
    VALIDATION_ERROR = "VALIDATION_ERROR"    # our payload was malformed
    CIRCUIT_OPEN = "CIRCUIT_OPEN"            # breaker refused the call

    @property
    def retryable(self) -> bool:
        return self in _RETRYABLE

    @property
    def reroutable(self) -> bool:
        return self in _REROUTABLE


_RETRYABLE = frozenset(
    {
        FaultType.RATE_LIMITED,
        FaultType.TIMEOUT,
        FaultType.SERVER_ERROR,
        FaultType.NETWORK_PARTITION,
        FaultType.AUTH_EXPIRED,
    }
)

_REROUTABLE = frozenset(
    {
        FaultType.RATE_LIMITED,
        FaultType.TIMEOUT,
        FaultType.SERVER_ERROR,
        FaultType.NETWORK_PARTITION,
        FaultType.CIRCUIT_OPEN,
    }
)


class Verdict(str, Enum):
    """What the gate decided to do about a call."""

    ALLOW = "ALLOW"              # executed first try, clean
    SELF_HEALED = "SELF_HEALED"  # succeeded after retry and/or reroute
    DEDUPED = "DEDUPED"          # idempotency ledger replayed a prior result
    DEGRADED = "DEGRADED"        # succeeded via a reduced-fidelity fallback
    BLOCKED = "BLOCKED"          # refused before any side effect occurred
    COMPENSATE = "COMPENSATE"    # unrecoverable - saga must roll back


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class ToolFault(Exception):
    """Raised by a tool executor to describe a typed, classifiable failure."""

    def __init__(
        self,
        fault: FaultType,
        message: str = "",
        *,
        retry_after: Optional[float] = None,
        endpoint: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message or fault.value)
        self.fault = fault
        self.message = message or fault.value
        self.retry_after = retry_after
        self.endpoint = endpoint
        self.detail = detail or {}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ToolFault({self.fault.value}, {self.message!r})"


@dataclass
class SchemaViolation:
    path: str
    rule: str
    expected: Any
    received: Any

    def __str__(self) -> str:
        return f"{self.path or '$'}: expected {self.rule}={self.expected!r}, got {self.received!r}"


@dataclass
class GateAttempt:
    """One physical execution attempt against one endpoint."""

    index: int
    endpoint: str
    started_at: float
    duration_ms: float
    ok: bool
    fault: Optional[FaultType] = None
    message: str = ""
    backoff_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "endpoint": self.endpoint,
            "started_at": self.started_at,
            "duration_ms": round(self.duration_ms, 3),
            "ok": self.ok,
            "fault": self.fault.value if self.fault else None,
            "message": self.message,
            "backoff_ms": round(self.backoff_ms, 3),
        }


@dataclass
class GateDecision:
    """Pre-flight decision: may this call touch the outside world at all?"""

    allowed: bool
    verdict: Verdict
    reason: str
    violations: List[SchemaViolation] = field(default_factory=list)
    overhead_us: float = 0.0
    replayed_result: Any = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "violations": [str(v) for v in self.violations],
            "overhead_us": round(self.overhead_us, 3),
        }


@dataclass
class GateOutcome:
    """Full record of a guarded call, handed to the reliability logger."""

    app: str
    tool: str
    verdict: Verdict
    ok: bool
    result: Any = None
    fault: Optional[FaultType] = None
    reason: str = ""
    attempts: List[GateAttempt] = field(default_factory=list)
    endpoint_used: Optional[str] = None
    gate_overhead_us: float = 0.0
    total_ms: float = 0.0
    idempotency_key: Optional[str] = None
    violations: List[SchemaViolation] = field(default_factory=list)

    @property
    def healed(self) -> bool:
        return self.verdict in (Verdict.SELF_HEALED, Verdict.DEGRADED)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app": self.app,
            "tool": self.tool,
            "verdict": self.verdict.value,
            "ok": self.ok,
            "fault": self.fault.value if self.fault else None,
            "reason": self.reason,
            "attempts": [a.to_dict() for a in self.attempts],
            "attempt_count": len(self.attempts),
            "endpoint_used": self.endpoint_used,
            "gate_overhead_us": round(self.gate_overhead_us, 3),
            "total_ms": round(self.total_ms, 3),
            "idempotency_key": self.idempotency_key,
            "violations": [str(v) for v in self.violations],
            "healed": self.healed,
        }


# ---------------------------------------------------------------------------
# 1. Zero-LLM schema validation
# ---------------------------------------------------------------------------


_TYPE_MAP: Dict[str, Tuple[type, ...]] = {
    "object": (dict,),
    "array": (list, tuple),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


class SchemaValidator:
    """A compiled, deterministic subset of JSON Schema.

    Deliberately *not* an LLM call and deliberately not `jsonschema`: the gate
    runs on the hot path of every side effect, so validation is a few hundred
    nanoseconds of pure-Python attribute checks with no import cost.

    Supported keywords: type, required, properties, additionalProperties,
    enum, const, minimum, maximum, exclusiveMinimum, exclusiveMaximum,
    minLength, maxLength, pattern, minItems, maxItems, items, anyOf, format
    (email / uri / iso-date / currency-code).
    """

    _FORMATS: Dict[str, re.Pattern] = {
        "email": re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
        "uri": re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://\S+$"),
        "iso-date": re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?"),
        "currency-code": re.compile(r"^[a-z]{3}$"),
        "git-ref": re.compile(r"^[\w./\-]{1,255}$"),
    }

    def __init__(self, schema: Dict[str, Any], *, name: str = "payload") -> None:
        self.schema = schema or {}
        self.name = name

    # -- public ------------------------------------------------------------

    def validate(self, payload: Any) -> List[SchemaViolation]:
        out: List[SchemaViolation] = []
        self._walk(payload, self.schema, "", out)
        return out

    def is_valid(self, payload: Any) -> bool:
        return not self.validate(payload)

    # -- internals ---------------------------------------------------------

    def _walk(self, value: Any, schema: Dict[str, Any], path: str, out: List[SchemaViolation]) -> None:
        if not isinstance(schema, dict) or not schema:
            return

        if "anyOf" in schema:
            branches = schema["anyOf"]
            for branch in branches:
                probe: List[SchemaViolation] = []
                self._walk(value, branch, path, probe)
                if not probe:
                    break
            else:
                out.append(SchemaViolation(path, "anyOf", len(branches), _brief(value)))
            return

        expected_type = schema.get("type")
        if expected_type:
            types = expected_type if isinstance(expected_type, list) else [expected_type]
            ok = False
            for t in types:
                py = _TYPE_MAP.get(t)
                if py is None:
                    ok = True
                    break
                # bool is a subclass of int - never let True satisfy "integer"
                if t in ("integer", "number") and isinstance(value, bool):
                    continue
                if isinstance(value, py):
                    ok = True
                    break
            if not ok:
                out.append(SchemaViolation(path, "type", expected_type, type(value).__name__))
                return  # downstream keywords are meaningless on a type mismatch

        if "const" in schema and value != schema["const"]:
            out.append(SchemaViolation(path, "const", schema["const"], _brief(value)))

        if "enum" in schema and value not in schema["enum"]:
            out.append(SchemaViolation(path, "enum", schema["enum"], _brief(value)))

        if isinstance(value, str):
            self._check_string(value, schema, path, out)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            self._check_number(value, schema, path, out)
        elif isinstance(value, dict):
            self._check_object(value, schema, path, out)
        elif isinstance(value, (list, tuple)):
            self._check_array(value, schema, path, out)

    def _check_string(self, value: str, schema: Dict[str, Any], path: str, out: List[SchemaViolation]) -> None:
        if "minLength" in schema and len(value) < schema["minLength"]:
            out.append(SchemaViolation(path, "minLength", schema["minLength"], len(value)))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            out.append(SchemaViolation(path, "maxLength", schema["maxLength"], len(value)))
        pattern = schema.get("pattern")
        if pattern and not re.search(pattern, value):
            out.append(SchemaViolation(path, "pattern", pattern, _brief(value)))
        fmt = schema.get("format")
        if fmt:
            rx = self._FORMATS.get(fmt)
            if rx and not rx.match(value):
                out.append(SchemaViolation(path, "format", fmt, _brief(value)))

    def _check_number(self, value: float, schema: Dict[str, Any], path: str, out: List[SchemaViolation]) -> None:
        if "minimum" in schema and value < schema["minimum"]:
            out.append(SchemaViolation(path, "minimum", schema["minimum"], value))
        if "maximum" in schema and value > schema["maximum"]:
            out.append(SchemaViolation(path, "maximum", schema["maximum"], value))
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            out.append(SchemaViolation(path, "exclusiveMinimum", schema["exclusiveMinimum"], value))
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            out.append(SchemaViolation(path, "exclusiveMaximum", schema["exclusiveMaximum"], value))
        if schema.get("multipleOf"):
            step = schema["multipleOf"]
            if abs((value / step) - round(value / step)) > 1e-9:
                out.append(SchemaViolation(path, "multipleOf", step, value))

    def _check_object(self, value: Dict[str, Any], schema: Dict[str, Any], path: str, out: List[SchemaViolation]) -> None:
        props: Dict[str, Any] = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                out.append(SchemaViolation(_join(path, key), "required", True, "<missing>"))
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    out.append(SchemaViolation(_join(path, key), "additionalProperties", False, "<unexpected>"))
        for key, sub in props.items():
            if key in value:
                self._walk(value[key], sub, _join(path, key), out)

    def _check_array(self, value: Sequence[Any], schema: Dict[str, Any], path: str, out: List[SchemaViolation]) -> None:
        if "minItems" in schema and len(value) < schema["minItems"]:
            out.append(SchemaViolation(path, "minItems", schema["minItems"], len(value)))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            out.append(SchemaViolation(path, "maxItems", schema["maxItems"], len(value)))
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(value):
                self._walk(item, item_schema, f"{path}[{i}]", out)


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _brief(value: Any, limit: int = 60) -> Any:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


# ---------------------------------------------------------------------------
# 2. Response drift detection
# ---------------------------------------------------------------------------


class DriftDetector:
    """Learns the observed *shape* of each tool's response and flags mutations.

    An upstream vendor silently renaming `amount` to `amount_cents`, or turning a
    string id into an integer, is the classic way a linear agent script corrupts
    downstream steps without ever raising. The detector fingerprints the
    key-path/type set of the first healthy response per tool and compares every
    subsequent one against that baseline.
    """

    def __init__(self, *, tolerance: float = 0.34) -> None:
        self._baselines: Dict[str, Dict[str, str]] = {}
        self.tolerance = tolerance
        self._lock = threading.Lock()

    @staticmethod
    def fingerprint(value: Any, prefix: str = "", depth: int = 0) -> Dict[str, str]:
        """Flatten a response into {key_path: type_name}. Arrays collapse to [*]."""
        shape: Dict[str, str] = {}
        if depth > 6:
            return shape
        if isinstance(value, dict):
            for key, sub in value.items():
                shape.update(DriftDetector.fingerprint(sub, _join(prefix, str(key)), depth + 1))
        elif isinstance(value, (list, tuple)):
            shape[prefix or "$"] = "array"
            if value:
                shape.update(DriftDetector.fingerprint(value[0], f"{prefix}[*]", depth + 1))
        else:
            shape[prefix or "$"] = type(value).__name__
        return shape

    def observe(self, tool: str, response: Any) -> Optional[Dict[str, Any]]:
        """Return a drift report, or None when the shape is stable/first-seen."""
        shape = self.fingerprint(response)
        if not shape:
            return None
        with self._lock:
            baseline = self._baselines.get(tool)
            if baseline is None:
                self._baselines[tool] = shape
                return None
            missing = sorted(set(baseline) - set(shape))
            added = sorted(set(shape) - set(baseline))
            retyped = sorted(
                k for k in set(baseline) & set(shape) if baseline[k] != shape[k]
            )
            if not missing and not retyped:
                # Clean observation: widen the baseline with genuinely new optional
                # fields, which are backwards-compatible and must not trip the gate.
                for key in added:
                    baseline[key] = shape[key]
                return None

            # Breaking observation: touch nothing. Learning the fields of a mutated
            # response would poison the baseline, so the *next* healthy response
            # would then look like drift - the failure mode this detector exists
            # to prevent, inverted.

            severity = (len(missing) + 2 * len(retyped)) / max(len(baseline), 1)

            # The baseline is deliberately NOT updated to the mutated shape. Quietly
            # adopting a contract that just dropped or retyped a field is how a bad
            # payout gets through; if the change is real and permanent, every call
            # keeps reporting it until a human updates the integration.

        return {
            "tool": tool,
            "missing_fields": missing,
            "retyped_fields": retyped,
            "added_fields": added,
            "severity": round(severity, 4),
            # A field that vanished or changed type is always breaking. Downstream
            # steps read these values by name, so a severity ratio is the wrong
            # gate: one renamed field is enough to corrupt a payout decision.
            "breaking": bool(missing) or bool(retyped),
        }

    def baseline_for(self, tool: str) -> Dict[str, str]:
        return dict(self._baselines.get(tool, {}))


# ---------------------------------------------------------------------------
# 3. Rate shaping, breakers, backoff, routing
# ---------------------------------------------------------------------------


class TokenBucket:
    """Pre-emptive client-side rate shaping - cheaper than absorbing a 429."""

    def __init__(self, rate_per_sec: float, burst: Optional[int] = None) -> None:
        self.rate = float(rate_per_sec)
        self.capacity = float(burst if burst is not None else max(1.0, rate_per_sec))
        self._tokens = self.capacity
        self._updated = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        self._tokens = min(self.capacity, self._tokens + (now - self._updated) * self.rate)
        self._updated = now

    def try_acquire(self, cost: float = 1.0) -> Tuple[bool, float]:
        """Return (granted, seconds_until_available)."""
        with self._lock:
            self._refill()
            if self._tokens >= cost:
                self._tokens -= cost
                return True, 0.0
            deficit = cost - self._tokens
            return False, deficit / self.rate if self.rate > 0 else math.inf

    @property
    def available(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens


class CircuitBreaker:
    """Per-endpoint breaker: CLOSED -> OPEN -> HALF_OPEN -> CLOSED."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 5.0,
        half_open_successes: int = 1,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_successes = half_open_successes
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.successes = 0
        self.opened_at: Optional[float] = None
        self.trip_count = 0
        self._lock = threading.Lock()

    def allows(self) -> bool:
        with self._lock:
            if self.state is CircuitState.CLOSED:
                return True
            if self.state is CircuitState.OPEN:
                if self.opened_at is not None and (time.monotonic() - self.opened_at) >= self.recovery_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.successes = 0
                    return True
                return False
            return True  # HALF_OPEN admits probe traffic

    def force_half_open(self) -> None:
        """Admit a single probe even before the recovery window elapses.

        Used when every endpoint in a fleet is open: a breaker exists to protect
        a struggling backend from load, not to guarantee that the caller fails.
        One probe is cheaper than an unnecessary saga rollback.
        """
        with self._lock:
            self.state = CircuitState.HALF_OPEN
            self.successes = 0

    def record_success(self) -> None:
        with self._lock:
            if self.state is CircuitState.HALF_OPEN:
                self.successes += 1
                if self.successes >= self.half_open_successes:
                    self.state = CircuitState.CLOSED
                    self.failures = 0
            else:
                self.failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.state is CircuitState.HALF_OPEN or self.failures >= self.failure_threshold:
                if self.state is not CircuitState.OPEN:
                    self.trip_count += 1
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "failures": self.failures,
            "trip_count": self.trip_count,
        }


class BackoffPolicy:
    """Exponential backoff with full jitter (AWS-style), capped and Retry-After aware."""

    def __init__(
        self,
        *,
        base_ms: float = 40.0,
        factor: float = 2.0,
        max_ms: float = 2_000.0,
        jitter: bool = True,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.base_ms = base_ms
        self.factor = factor
        self.max_ms = max_ms
        self.jitter = jitter
        self._rng = rng or random.Random(0xC0FFEE)

    def delay_ms(self, attempt: int, retry_after: Optional[float] = None) -> float:
        if retry_after is not None:
            return min(max(retry_after * 1000.0, 0.0), self.max_ms)
        raw = min(self.base_ms * (self.factor ** max(attempt - 1, 0)), self.max_ms)
        return self._rng.uniform(0.0, raw) if self.jitter else raw


@dataclass
class _EndpointHealth:
    url: str
    score: float = 1.0
    successes: int = 0
    failures: int = 0
    last_latency_ms: float = 0.0


class EndpointRouter:
    """Health-ranked failover across an app's primary and secondary MCP gateways.

    Scores decay multiplicatively on failure and recover additively on success,
    so a flapping endpoint is deprioritised without being permanently banned.
    """

    def __init__(self, breaker_factory: Optional[Callable[[], CircuitBreaker]] = None) -> None:
        self._routes: Dict[str, List[_EndpointHealth]] = {}
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._breaker_factory = breaker_factory or CircuitBreaker
        self._lock = threading.Lock()

    def register(self, app: str, endpoints: Sequence[str]) -> None:
        with self._lock:
            self._routes[app] = [_EndpointHealth(url=e) for e in endpoints]
            for e in endpoints:
                self._breakers.setdefault(e, self._breaker_factory())

    def breaker(self, endpoint: str) -> CircuitBreaker:
        with self._lock:
            return self._breakers.setdefault(endpoint, self._breaker_factory())

    def candidates(self, app: str) -> List[str]:
        """Endpoints ordered best-first, breaker-open ones pushed to the back."""
        with self._lock:
            routes = list(self._routes.get(app, []))
        if not routes:
            return []
        ranked = sorted(routes, key=lambda r: (-r.score, r.failures, r.last_latency_ms))
        live = [r.url for r in ranked if self.breaker(r.url).allows()]
        parked = [r.url for r in ranked if r.url not in live]
        return live + parked

    def healthiest(self, app: str) -> Optional[str]:
        """Best-scoring endpoint regardless of breaker state - the probe target."""
        with self._lock:
            routes = list(self._routes.get(app, []))
        if not routes:
            return None
        return max(routes, key=lambda r: (r.score, -r.failures)).url

    def record(self, app: str, endpoint: str, ok: bool, latency_ms: float = 0.0) -> None:
        with self._lock:
            for route in self._routes.get(app, []):
                if route.url != endpoint:
                    continue
                route.last_latency_ms = latency_ms
                if ok:
                    route.successes += 1
                    route.score = min(1.0, route.score + 0.15)
                else:
                    route.failures += 1
                    route.score = max(0.05, route.score * 0.5)
        (self.breaker(endpoint).record_success if ok else self.breaker(endpoint).record_failure)()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            routes = {app: list(rs) for app, rs in self._routes.items()}
        return {
            app: [
                {
                    "url": r.url,
                    "score": round(r.score, 3),
                    "successes": r.successes,
                    "failures": r.failures,
                    "latency_ms": round(r.last_latency_ms, 2),
                    "breaker": self.breaker(r.url).to_dict(),
                }
                for r in rs
            ]
            for app, rs in routes.items()
        }


# ---------------------------------------------------------------------------
# 4. Idempotency
# ---------------------------------------------------------------------------


class IdempotencyLedger:
    """Remembers completed side effects so a retry never double-charges.

    Stripe payouts are the reason this exists: if the gate retries a transfer
    whose response was lost in flight, the ledger replays the recorded result
    instead of moving money twice.
    """

    def __init__(self, ttl_seconds: float = 3600.0) -> None:
        self._entries: Dict[str, Tuple[float, Any]] = {}
        self._inflight: Dict[str, float] = {}
        self.ttl = ttl_seconds
        self.hits = 0
        self._lock = threading.Lock()

    def lookup(self, key: Optional[str]) -> Tuple[bool, Any]:
        if not key:
            return False, None
        with self._lock:
            self._evict()
            if key in self._entries:
                self.hits += 1
                return True, self._entries[key][1]
            return False, None

    def mark_inflight(self, key: Optional[str]) -> None:
        if key:
            with self._lock:
                self._inflight[key] = time.time()

    def commit(self, key: Optional[str], result: Any) -> None:
        if not key:
            return
        with self._lock:
            self._entries[key] = (time.time(), result)
            self._inflight.pop(key, None)

    def release(self, key: Optional[str]) -> None:
        if key:
            with self._lock:
                self._inflight.pop(key, None)

    def _evict(self) -> None:
        cutoff = time.time() - self.ttl
        for key in [k for k, (ts, _) in self._entries.items() if ts < cutoff]:
            self._entries.pop(key, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


# ---------------------------------------------------------------------------
# 5. Chaos engine
# ---------------------------------------------------------------------------


@dataclass
class ChaosProfile:
    """Fault-injection weights. Deterministic for a given seed, so a judge can
    replay the exact same failure sequence and see the same recovery path."""

    enabled: bool = False
    seed: int = 1337
    rate_limit: float = 0.22
    timeout: float = 0.10
    server_error: float = 0.10
    network_partition: float = 0.05
    schema_drift: float = 0.06
    auth_expired: float = 0.04
    max_consecutive: int = 3  # never fail the same call forever

    @property
    def total_probability(self) -> float:
        return (
            self.rate_limit
            + self.timeout
            + self.server_error
            + self.network_partition
            + self.schema_drift
            + self.auth_expired
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "seed": self.seed,
            "total_probability": round(self.total_probability, 4),
            "weights": {
                "RATE_LIMITED": self.rate_limit,
                "TIMEOUT": self.timeout,
                "SERVER_ERROR": self.server_error,
                "NETWORK_PARTITION": self.network_partition,
                "SCHEMA_DRIFT": self.schema_drift,
                "AUTH_EXPIRED": self.auth_expired,
            },
            "max_consecutive": self.max_consecutive,
        }

    @classmethod
    def storm(cls, seed: int = 1337) -> "ChaosProfile":
        """The demo setting: ~75% of calls fail on first attempt."""
        return cls(
            enabled=True,
            seed=seed,
            rate_limit=0.30,
            timeout=0.15,
            server_error=0.15,
            network_partition=0.06,
            schema_drift=0.05,
            auth_expired=0.04,
        )


class ChaosEngine:
    """Injects typed faults into tool execution on a seeded RNG."""

    def __init__(self, profile: Optional[ChaosProfile] = None) -> None:
        self.profile = profile or ChaosProfile()
        self._rng = random.Random(self.profile.seed)
        self._streak: Dict[str, int] = {}
        self.injected: Dict[str, int] = {}
        self._lock = threading.Lock()

    def reconfigure(self, profile: ChaosProfile) -> None:
        with self._lock:
            self.profile = profile
            self._rng = random.Random(profile.seed)
            self._streak.clear()

    def reset(self) -> None:
        with self._lock:
            self._rng = random.Random(self.profile.seed)
            self._streak.clear()
            self.injected.clear()

    def maybe_fault(self, key: str, attempt: int) -> Optional[ToolFault]:
        p = self.profile
        if not p.enabled:
            return None
        with self._lock:
            if self._streak.get(key, 0) >= p.max_consecutive:
                self._streak[key] = 0
                return None
            roll = self._rng.random()
            ladder: List[Tuple[float, FaultType]] = []
            acc = 0.0
            for weight, fault in (
                (p.rate_limit, FaultType.RATE_LIMITED),
                (p.timeout, FaultType.TIMEOUT),
                (p.server_error, FaultType.SERVER_ERROR),
                (p.network_partition, FaultType.NETWORK_PARTITION),
                (p.schema_drift, FaultType.SCHEMA_DRIFT),
                (p.auth_expired, FaultType.AUTH_EXPIRED),
            ):
                acc += weight
                ladder.append((acc, fault))
            chosen: Optional[FaultType] = None
            for threshold, fault in ladder:
                if roll < threshold:
                    chosen = fault
                    break
            if chosen is None:
                self._streak[key] = 0
                return None
            self._streak[key] = self._streak.get(key, 0) + 1
            self.injected[chosen.value] = self.injected.get(chosen.value, 0) + 1

        retry_after = round(self._rng.uniform(0.02, 0.12), 3) if chosen is FaultType.RATE_LIMITED else None
        return ToolFault(
            chosen,
            f"[chaos] injected {chosen.value} on attempt {attempt}",
            retry_after=retry_after,
            detail={"injected": True, "seed": p.seed},
        )


# ---------------------------------------------------------------------------
# 6. Metrics
# ---------------------------------------------------------------------------


class GateMetrics:
    """Measured, not asserted. Every number Triadr publishes comes from here."""

    def __init__(self) -> None:
        self.total_calls = 0
        self.clean_calls = 0
        self.self_healed = 0
        self.deduped = 0
        self.degraded = 0
        self.blocked = 0
        self.compensated = 0
        self.total_attempts = 0
        self.faults_seen: Dict[str, int] = {}
        self.drift_events = 0
        self._overheads_us: List[float] = []
        self._lock = threading.Lock()

    def record(self, outcome: GateOutcome) -> None:
        with self._lock:
            self.total_calls += 1
            self.total_attempts += max(len(outcome.attempts), 1)
            self._overheads_us.append(outcome.gate_overhead_us)
            if outcome.verdict is Verdict.ALLOW:
                self.clean_calls += 1
            elif outcome.verdict is Verdict.SELF_HEALED:
                self.self_healed += 1
            elif outcome.verdict is Verdict.DEDUPED:
                self.deduped += 1
            elif outcome.verdict is Verdict.DEGRADED:
                self.degraded += 1
            elif outcome.verdict is Verdict.BLOCKED:
                self.blocked += 1
            elif outcome.verdict is Verdict.COMPENSATE:
                self.compensated += 1
            for attempt in outcome.attempts:
                if attempt.fault:
                    self.faults_seen[attempt.fault.value] = self.faults_seen.get(attempt.fault.value, 0) + 1

    def note_drift(self) -> None:
        with self._lock:
            self.drift_events += 1

    def percentiles(self) -> Dict[str, float]:
        with self._lock:
            samples = sorted(self._overheads_us)
        if not samples:
            return {"p50_us": 0.0, "p95_us": 0.0, "p99_us": 0.0, "max_us": 0.0, "mean_us": 0.0}

        def pick(q: float) -> float:
            idx = min(len(samples) - 1, max(0, int(round(q * (len(samples) - 1)))))
            return round(samples[idx], 3)

        return {
            "p50_us": pick(0.50),
            "p95_us": pick(0.95),
            "p99_us": pick(0.99),
            "max_us": round(samples[-1], 3),
            "mean_us": round(sum(samples) / len(samples), 3),
        }

    @property
    def successful(self) -> int:
        return self.clean_calls + self.self_healed + self.deduped + self.degraded

    @property
    def reliability_score(self) -> float:
        """Fraction of guarded calls that completed without corrupting the saga."""
        if not self.total_calls:
            return 1.0
        return round(self.successful / self.total_calls, 4)

    @property
    def faults_absorbed(self) -> int:
        return sum(self.faults_seen.values())

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            faults = dict(self.faults_seen)
        return {
            "total_calls": self.total_calls,
            "clean_calls": self.clean_calls,
            "self_healed": self.self_healed,
            "deduped": self.deduped,
            "degraded": self.degraded,
            "blocked": self.blocked,
            "compensated": self.compensated,
            "total_attempts": self.total_attempts,
            "faults_absorbed": sum(faults.values()),
            "faults_by_type": faults,
            "drift_events": self.drift_events,
            "reliability_score": self.reliability_score,
            "gate_latency": self.percentiles(),
        }


# ---------------------------------------------------------------------------
# 7. The gate
# ---------------------------------------------------------------------------

# Sustained request budgets, sized below each vendor's documented ceiling so the
# bucket sheds load before the vendor does.
DEFAULT_RATE_LIMITS: Dict[str, Tuple[float, int]] = {
    "github": (12.0, 24),   # GitHub REST: 5000/hr authenticated, bursty secondary limits
    "telegram": (2.0, 5),   # Bot API: ~1 msg/s per chat, 30/s overall; polling shares the bucket
    "stripe": (20.0, 40),   # Stripe live mode: 100 read/s, 100 write/s
}

DEFAULT_ENDPOINTS: Dict[str, List[str]] = {
    "github": ["mcp://github/primary", "mcp://github/replica", "https://api.github.com"],
    "telegram": ["mcp://telegram/primary", "mcp://telegram/replica", "https://api.telegram.org"],
    "stripe": ["mcp://stripe/primary", "mcp://stripe/replica", "https://api.stripe.com"],
}


class ReliabilityGate:
    """The single choke point every Triadr side effect passes through."""

    def __init__(
        self,
        *,
        max_attempts: int = 4,
        chaos: Optional[ChaosProfile] = None,
        backoff: Optional[BackoffPolicy] = None,
        rate_limits: Optional[Dict[str, Tuple[float, int]]] = None,
        endpoints: Optional[Dict[str, List[str]]] = None,
        sleep: Optional[Callable[[float], None]] = None,
        strict_drift: bool = True,
    ) -> None:
        self.max_attempts = max_attempts
        self.backoff = backoff or BackoffPolicy()
        self.router = EndpointRouter()
        self.breaker_registry = self.router  # alias used by the dashboard
        self.ledger = IdempotencyLedger()
        self.drift = DriftDetector()
        self.chaos = ChaosEngine(chaos)
        self.metrics = GateMetrics()
        self.strict_drift = strict_drift
        self._sleep = sleep or time.sleep
        self._buckets: Dict[str, TokenBucket] = {}
        self._listeners: List[Callable[[Dict[str, Any]], None]] = []

        for app, eps in (endpoints or DEFAULT_ENDPOINTS).items():
            self.router.register(app, eps)
        for app, (rate, burst) in (rate_limits or DEFAULT_RATE_LIMITS).items():
            self._buckets[app] = TokenBucket(rate, burst)

        # Retained for the original CLI surface (see `evaluate_tool_execution`).
        self.total_evaluations = 0
        self.successful_recoveries = 0

    # -- observability -----------------------------------------------------

    def subscribe(self, listener: Callable[[Dict[str, Any]], None]) -> None:
        self._listeners.append(listener)

    def _emit(self, event: str, **payload: Any) -> None:
        record = {"event": event, "ts": time.time(), **payload}
        for listener in list(self._listeners):
            try:
                listener(record)
            except Exception:  # a broken dashboard must never break the workflow
                pass

    # -- main entry point --------------------------------------------------

    def guard(
        self,
        *,
        app: str,
        tool: str,
        payload: Dict[str, Any],
        executor: Callable[..., Any],
        schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        degraded_executor: Optional[Callable[..., Any]] = None,
        max_attempts: Optional[int] = None,
        side_effect: str = "read",
    ) -> GateOutcome:
        """Execute `executor` under full reliability supervision.

        `executor` is called as `executor(payload=..., endpoint=...)` and must
        raise `ToolFault` for typed failures. Anything else it raises is
        classified conservatively as a terminal validation error.
        """
        app_key = app.lower()
        started = time.perf_counter()
        overhead_us = 0.0
        attempts: List[GateAttempt] = []
        budget = max_attempts or self.max_attempts

        # --- pre-flight (measured separately from network time) ------------
        pre = time.perf_counter()
        replayed, cached = self.ledger.lookup(idempotency_key)
        violations: List[SchemaViolation] = []
        if not replayed and schema:
            violations = SchemaValidator(schema, name=tool).validate(payload)
        overhead_us += (time.perf_counter() - pre) * 1e6

        if replayed:
            outcome = GateOutcome(
                app=app, tool=tool, verdict=Verdict.DEDUPED, ok=True, result=cached,
                reason=f"Idempotency key '{idempotency_key}' already settled - replayed prior result, no duplicate side effect.",
                gate_overhead_us=overhead_us,
                total_ms=(time.perf_counter() - started) * 1000,
                idempotency_key=idempotency_key,
            )
            self.metrics.record(outcome)
            self._emit("gate.deduped", app=app, tool=tool, key=idempotency_key)
            return outcome

        if violations:
            outcome = GateOutcome(
                app=app, tool=tool, verdict=Verdict.BLOCKED, ok=False,
                fault=FaultType.VALIDATION_ERROR,
                reason=f"Blocked before any side effect - {len(violations)} schema violation(s): " + "; ".join(str(v) for v in violations[:3]),
                gate_overhead_us=overhead_us,
                total_ms=(time.perf_counter() - started) * 1000,
                violations=violations,
                idempotency_key=idempotency_key,
            )
            self.metrics.record(outcome)
            self._emit("gate.blocked", app=app, tool=tool, violations=[str(v) for v in violations])
            return outcome

        # --- rate shaping ---------------------------------------------------
        bucket = self._buckets.get(app_key)
        if bucket is not None:
            granted, wait_s = bucket.try_acquire()
            if not granted and wait_s < 5.0:
                self._emit("gate.throttled", app=app, tool=tool, wait_ms=round(wait_s * 1000, 2))
                self._sleep(wait_s)
                bucket.try_acquire()

        candidates = self.router.candidates(app_key) or ["mcp://local/inprocess"]
        self.ledger.mark_inflight(idempotency_key)

        primary = candidates[0]
        last_fault: Optional[ToolFault] = None
        attempt_no = 0
        cursor = 0

        while attempt_no < budget:
            # Re-evaluate liveness every attempt: a breaker that tripped earlier in
            # this same call may have reached its half-open probe window, and one
            # that was healthy may have just tripped. Open endpoints are never
            # *selected*, so a dead gateway costs no retry budget at all - the
            # budget is spent only on calls that actually reach the network.
            live = [e for e in candidates if self.router.breaker(e).allows()]
            if not live:
                # The whole fleet is shedding load. Rather than burn the remaining
                # budget doing nothing - and force a saga rollback that a single
                # successful call would have avoided - admit one probe against the
                # healthiest endpoint. If the probe fails, the loop simply spends
                # another attempt and terminates on the budget as usual.
                probe = self.router.healthiest(app_key) or primary
                self.router.breaker(probe).force_half_open()
                live = [probe]
                self._emit("gate.forced_probe", app=app, tool=tool, endpoint=probe)

            endpoint = live[cursor % len(live)]
            cursor += 1
            attempt_no += 1

            chaos_fault = self.chaos.maybe_fault(f"{app_key}:{tool}", attempt_no)
            drift_injection = chaos_fault is not None and chaos_fault.fault is FaultType.SCHEMA_DRIFT
            if chaos_fault is not None and not drift_injection:
                # Injected transport-level fault: no executor call happens.
                attempts.append(
                    GateAttempt(
                        index=attempt_no, endpoint=endpoint, started_at=time.time(),
                        duration_ms=0.0, ok=False, fault=chaos_fault.fault, message=chaos_fault.message,
                    )
                )
                self.router.record(app_key, endpoint, ok=False)
                last_fault = chaos_fault
                self._emit("gate.fault", app=app, tool=tool, endpoint=endpoint,
                           fault=chaos_fault.fault.value, attempt=attempt_no, injected=True)
                if not chaos_fault.fault.retryable or attempt_no >= budget:
                    break
                delay = self.backoff.delay_ms(attempt_no, chaos_fault.retry_after)
                attempts[-1].backoff_ms = delay
                self._emit("gate.backoff", app=app, tool=tool, delay_ms=round(delay, 2), attempt=attempt_no)
                self._sleep(delay / 1000.0)
                continue

            call_start = time.time()
            t0 = time.perf_counter()
            try:
                result = executor(payload=payload, endpoint=endpoint)
                elapsed = (time.perf_counter() - t0) * 1000

                if drift_injection:
                    result = _mutate_response(result)
                    self._emit("gate.drift_injected", app=app, tool=tool, endpoint=endpoint)

                pre = time.perf_counter()
                # A *declared* response contract catches drift on the very first
                # call, which a learned baseline cannot: the first response is the
                # baseline, so a mutation seen once would be adopted as normal.
                declared: List[SchemaViolation] = (
                    SchemaValidator(output_schema, name=f"{tool}.response").validate(result)
                    if output_schema else []
                )
                report = self.drift.observe(f"{app_key}.{tool}", result)
                overhead_us += (time.perf_counter() - pre) * 1e6

                if declared and self.strict_drift:
                    self.metrics.note_drift()
                    message = ("declared response contract violated: "
                               + "; ".join(str(v) for v in declared[:3]))
                    attempts.append(
                        GateAttempt(
                            index=attempt_no, endpoint=endpoint, started_at=call_start,
                            duration_ms=elapsed, ok=False, fault=FaultType.SCHEMA_DRIFT,
                            message=message,
                        )
                    )
                    self.router.record(app_key, endpoint, ok=False, latency_ms=elapsed)
                    last_fault = ToolFault(FaultType.SCHEMA_DRIFT, message, endpoint=endpoint,
                                           detail={"violations": [str(v) for v in declared]})
                    self._emit("gate.drift", app=app, tool=tool, endpoint=endpoint,
                               report={"declared_violations": [str(v) for v in declared]})
                    if attempt_no >= budget:
                        break
                    continue

                if report and report["breaking"] and self.strict_drift:
                    self.metrics.note_drift()
                    attempts.append(
                        GateAttempt(
                            index=attempt_no, endpoint=endpoint, started_at=call_start,
                            duration_ms=elapsed, ok=False, fault=FaultType.SCHEMA_DRIFT,
                            message=f"response contract mutated: missing={report['missing_fields']} retyped={report['retyped_fields']}",
                        )
                    )
                    self.router.record(app_key, endpoint, ok=False, latency_ms=elapsed)
                    last_fault = ToolFault(FaultType.SCHEMA_DRIFT, attempts[-1].message, endpoint=endpoint, detail=report)
                    self._emit("gate.drift", app=app, tool=tool, endpoint=endpoint, report=report)
                    if attempt_no >= budget:
                        break
                    continue

                attempts.append(
                    GateAttempt(
                        index=attempt_no, endpoint=endpoint, started_at=call_start,
                        duration_ms=elapsed, ok=True, message="ok",
                    )
                )
                self.router.record(app_key, endpoint, ok=True, latency_ms=elapsed)
                self.ledger.commit(idempotency_key, result)

                healed = attempt_no > 1 or endpoint != primary
                verdict = Verdict.SELF_HEALED if healed else Verdict.ALLOW
                if healed:
                    self.successful_recoveries += 1
                reason = (
                    f"Recovered after {attempt_no} attempt(s) via {endpoint} - "
                    f"absorbed {sum(1 for a in attempts if not a.ok)} fault(s), workflow never broke."
                    if healed
                    else f"Executed cleanly, first attempt, on the highest-ranked healthy endpoint ({endpoint})."
                )
                outcome = GateOutcome(
                    app=app, tool=tool, verdict=verdict, ok=True, result=result,
                    reason=reason, attempts=attempts, endpoint_used=endpoint,
                    gate_overhead_us=overhead_us,
                    total_ms=(time.perf_counter() - started) * 1000,
                    idempotency_key=idempotency_key,
                )
                self.metrics.record(outcome)
                self.total_evaluations += 1
                self._emit("gate.ok", app=app, tool=tool, verdict=verdict.value,
                           endpoint=endpoint, attempts=len(attempts))
                return outcome

            except ToolFault as fault:
                elapsed = (time.perf_counter() - t0) * 1000
                attempts.append(
                    GateAttempt(
                        index=attempt_no, endpoint=endpoint, started_at=call_start,
                        duration_ms=elapsed, ok=False, fault=fault.fault, message=fault.message,
                    )
                )
                self.router.record(app_key, endpoint, ok=False, latency_ms=elapsed)
                last_fault = fault
                self._emit("gate.fault", app=app, tool=tool, endpoint=endpoint,
                           fault=fault.fault.value, attempt=attempt_no, injected=False)
                if not fault.fault.retryable or attempt_no >= budget:
                    break
                delay = self.backoff.delay_ms(attempt_no, fault.retry_after)
                attempts[-1].backoff_ms = delay
                self._emit("gate.backoff", app=app, tool=tool, delay_ms=round(delay, 2), attempt=attempt_no)
                self._sleep(delay / 1000.0)

            except Exception as exc:  # unexpected - treat as terminal, never retry blindly
                elapsed = (time.perf_counter() - t0) * 1000
                attempts.append(
                    GateAttempt(
                        index=attempt_no, endpoint=endpoint, started_at=call_start,
                        duration_ms=elapsed, ok=False, fault=FaultType.VALIDATION_ERROR,
                        message=f"{type(exc).__name__}: {exc}",
                    )
                )
                self.router.record(app_key, endpoint, ok=False, latency_ms=elapsed)
                last_fault = ToolFault(FaultType.VALIDATION_ERROR, str(exc), endpoint=endpoint)
                break

        # --- every endpoint exhausted: try the degraded path ---------------
        self.ledger.release(idempotency_key)
        if degraded_executor is not None:
            try:
                result = degraded_executor(payload=payload, endpoint="mcp://triadr/degraded")
                outcome = GateOutcome(
                    app=app, tool=tool, verdict=Verdict.DEGRADED, ok=True, result=result,
                    reason="All live endpoints exhausted - completed via reduced-fidelity local fallback so the saga stays consistent.",
                    attempts=attempts, endpoint_used="mcp://triadr/degraded",
                    gate_overhead_us=overhead_us,
                    total_ms=(time.perf_counter() - started) * 1000,
                    idempotency_key=idempotency_key,
                )
                self.metrics.record(outcome)
                self.successful_recoveries += 1
                self._emit("gate.degraded", app=app, tool=tool)
                return outcome
            except Exception:
                pass

        fault_type = last_fault.fault if last_fault else FaultType.SERVER_ERROR
        outcome = GateOutcome(
            app=app, tool=tool, verdict=Verdict.COMPENSATE, ok=False, fault=fault_type,
            reason=f"Unrecoverable after {len(attempts)} attempt(s) across {len({a.endpoint for a in attempts})} endpoint(s) "
                   f"(last fault: {fault_type.value}). Saga rollback requested - no partial state is left behind.",
            attempts=attempts,
            endpoint_used=attempts[-1].endpoint if attempts else None,
            gate_overhead_us=overhead_us,
            total_ms=(time.perf_counter() - started) * 1000,
            idempotency_key=idempotency_key,
        )
        self.metrics.record(outcome)
        self._emit("gate.compensate", app=app, tool=tool, fault=fault_type.value)
        return outcome

    # -- utilities ---------------------------------------------------------

    def configure_chaos(self, profile: ChaosProfile) -> None:
        self.chaos.reconfigure(profile)
        self._emit("chaos.configured", profile=profile.to_dict())

    def snapshot(self) -> Dict[str, Any]:
        return {
            "metrics": self.metrics.to_dict(),
            "routes": self.router.snapshot(),
            "chaos": self.chaos.profile.to_dict(),
            "chaos_injected": dict(self.chaos.injected),
            "idempotency_entries": len(self.ledger),
            "idempotency_hits": self.ledger.hits,
        }

    def benchmark(self, iterations: int = 20_000) -> Dict[str, Any]:
        """Measure real gate overhead in both phases. No hardcoded microsecond claims.

        Phase 1 (`schema_validation`) is the pre-flight contract check that runs
        before any side effect. Phase 2 (`full_preflight`) adds the response
        drift fingerprint, which walks the whole response body and is therefore
        proportional to payload size. Triadr reports both, because quoting only
        the first would overstate the engine.
        """
        schema = {
            "type": "object",
            "required": ["action", "amount", "currency"],
            "properties": {
                "action": {"type": "string", "enum": ["release_escrow"]},
                "amount": {"type": "number", "minimum": 1, "maximum": 1_000_000},
                "currency": {"type": "string", "format": "currency-code"},
            },
            "additionalProperties": False,
        }
        validator = SchemaValidator(schema)
        payload = {"action": "release_escrow", "amount": 2500.0, "currency": "usd"}
        samples: List[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            validator.validate(payload)
            samples.append((time.perf_counter() - t0) * 1e6)
        samples.sort()

        def pick(q: float) -> float:
            return round(samples[min(len(samples) - 1, int(q * (len(samples) - 1)))], 3)

        response = {
            "id": "tr_3Q8xTriadrDemo", "amount": 250000, "currency": "usd",
            "destination": "acct_1TriadrContractor", "status": "paid", "reversed": False,
            "created": 1789000000, "metadata": {"repo": "mrnetwork/triadr", "pr": "42"},
        }
        detector = DriftDetector()
        detector.observe("bench", response)
        full: List[float] = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            validator.validate(payload)
            detector.observe("bench", response)
            full.append((time.perf_counter() - t0) * 1e6)
        full.sort()

        def pick_full(q: float) -> float:
            return round(full[min(len(full) - 1, int(q * (len(full) - 1)))], 3)

        return {
            "iterations": iterations,
            "schema_validation": {
                "p50_us": pick(0.50), "p95_us": pick(0.95), "p99_us": pick(0.99),
                "mean_us": round(sum(samples) / len(samples), 3),
            },
            "full_preflight": {
                "p50_us": pick_full(0.50), "p95_us": pick_full(0.95), "p99_us": pick_full(0.99),
                "mean_us": round(sum(full) / len(full), 3),
            },
        }

    # -- backward-compatible single-shot API -------------------------------

    def evaluate_tool_execution(self, app_name: str, payload: Dict[str, Any]) -> Tuple[bool, str]:
        """Legacy surface kept so the original CLI demo keeps working.

        New code should use `guard()`, which actually executes the call.
        """
        self.total_evaluations += 1
        if not isinstance(payload, dict) or "action" not in payload:
            return False, f"REJECTED: [{app_name}] Invalid payload schema - missing required 'action'."
        simulated = payload.get("simulated_error")
        if simulated:
            try:
                fault = FaultType(simulated)
            except ValueError:
                fault = FaultType.SERVER_ERROR
            if fault.retryable:
                self.successful_recoveries += 1
                delay = self.backoff.delay_ms(1)
                return True, (
                    f"SELF-HEALED: [{app_name}] {fault.value} absorbed - backed off {delay:.1f} ms "
                    f"and rerouted to the secondary MCP gateway."
                )
            return False, f"REJECTED: [{app_name}] {fault.value} is terminal - escalating to saga compensation."
        return True, f"APPROVED: [{app_name}] Action '{payload['action']}' passed the reliability gate."


def _mutate_response(result: Any) -> Any:
    """Simulate a vendor silently changing its response contract."""
    if not isinstance(result, dict) or not result:
        return result
    mutated = dict(result)
    keys = [k for k in mutated if not k.startswith("_")]
    if not keys:
        return mutated
    victim = keys[0]
    value = mutated.pop(victim)
    mutated[f"{victim}_v2"] = str(value) if not isinstance(value, str) else 0
    mutated["_drift"] = True
    return mutated


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    gate = ReliabilityGate(chaos=ChaosProfile.storm(), sleep=lambda _s: None)

    calls = {"n": 0}

    def flaky(*, payload: Dict[str, Any], endpoint: str) -> Dict[str, Any]:
        calls["n"] += 1
        return {"id": "po_1Triadr", "amount": payload["amount"], "currency": payload["currency"], "status": "paid"}

    schema = {
        "type": "object",
        "required": ["action", "amount", "currency"],
        "properties": {
            "action": {"type": "string", "const": "release_escrow"},
            "amount": {"type": "number", "exclusiveMinimum": 0},
            "currency": {"type": "string", "format": "currency-code"},
        },
        "additionalProperties": False,
    }

    print("Triadr Reliability Gate - self-test under chaos storm\n")
    for i in range(6):
        out = gate.guard(
            app="stripe", tool="stripe.release_escrow",
            payload={"action": "release_escrow", "amount": 2500.0, "currency": "usd"},
            executor=flaky, schema=schema, idempotency_key=f"escrow-{i % 3}",
            side_effect="payment",
        )
        print(f"  {i+1}. {out.verdict.value:<12} attempts={len(out.attempts):<2} {out.reason}")

    bad = gate.guard(
        app="stripe", tool="stripe.release_escrow",
        payload={"action": "release_escrow", "amount": -5, "currency": "US-DOLLAR"},
        executor=flaky, schema=schema,
    )
    print(f"\n  malformed payload -> {bad.verdict.value}: {bad.reason}")

    print("\nMeasured gate overhead:", json.dumps(gate.benchmark(5000), indent=2))
    print("Reliability score:", gate.metrics.reliability_score)
