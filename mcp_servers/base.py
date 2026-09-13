"""
Triadr - MCP (Model Context Protocol) foundation layer.

Every external app Triadr touches is exposed as a set of MCP tools with real
JSON Schema contracts. `ToolSpec.to_mcp()` emits the exact shape the MCP
`tools/list` response expects, so these servers can be mounted by any MCP host
(Claude Desktop, Claude Code, an SDK agent) - see `mcp_servers/stdio_server.py`.

Each server runs in one of two modes, decided per-app at construction:

  * LIVE      - real credentials present in the environment; calls the vendor API
  * SIMULATED - deterministic in-process fixtures with realistic latency

Mode is surfaced everywhere (tool results, dashboard, audit log) so a demo is
never mistaken for production traffic.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from risk_gate import FaultType, SchemaValidator, ToolFault

JSONDict = Dict[str, Any]


class Mode(str, Enum):
    LIVE = "LIVE"
    SIMULATED = "SIMULATED"


class SideEffect(str, Enum):
    READ = "read"          # safe to repeat freely
    WRITE = "write"        # mutates remote state
    PAYMENT = "payment"    # moves money - always idempotency-keyed


@dataclass
class ToolSpec:
    """An MCP tool declaration plus the reliability metadata Triadr needs."""

    name: str
    app: str
    title: str
    description: str
    input_schema: JSONDict
    output_schema: Optional[JSONDict] = None
    side_effect: SideEffect = SideEffect.READ
    idempotent: bool = True
    compensates: Optional[str] = None      # tool that undoes this one
    compensated_by: Optional[str] = None   # tool that undoes *this*
    timeout_s: float = 10.0

    def to_mcp(self) -> JSONDict:
        """Serialise to the MCP `tools/list` entry shape."""
        spec: JSONDict = {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "readOnlyHint": self.side_effect is SideEffect.READ,
                "destructiveHint": self.side_effect is SideEffect.PAYMENT,
                "idempotentHint": self.idempotent,
                "openWorldHint": True,
            },
            "_triadr": {
                "app": self.app,
                "sideEffect": self.side_effect.value,
                "compensatedBy": self.compensated_by,
                "timeoutSeconds": self.timeout_s,
            },
        }
        if self.output_schema:
            spec["outputSchema"] = self.output_schema
        return spec


@dataclass
class ToolResult:
    """MCP `tools/call` result, plus Triadr provenance."""

    ok: bool
    data: JSONDict
    mode: Mode
    endpoint: str
    latency_ms: float = 0.0
    summary: str = ""

    def to_mcp(self) -> JSONDict:
        return {
            "content": [{"type": "text", "text": self.summary or json.dumps(self.data, indent=2)}],
            "structuredContent": self.data,
            "isError": not self.ok,
            "_meta": {
                "triadr/mode": self.mode.value,
                "triadr/endpoint": self.endpoint,
                "triadr/latencyMs": round(self.latency_ms, 2),
            },
        }


class MCPServer:
    """Base class for Triadr's three app servers.

    Subclasses register tools with `self.tool(spec)(handler)`. Handlers receive
    `(args, ctx)` where ctx carries the resolved endpoint and mode, and raise
    `ToolFault` for anything the reliability gate should classify and heal.
    """

    app: str = "generic"
    api_base: str = ""
    credential_env: tuple[str, ...] = ()

    def __init__(self, *, mode: Optional[Mode] = None, seed: int = 20260913) -> None:
        self._tools: Dict[str, ToolSpec] = {}
        self._handlers: Dict[str, Callable[[JSONDict, JSONDict], JSONDict]] = {}
        self._rng = random.Random(seed ^ hash(self.app) % (2**31))
        self.mode = mode or self._detect_mode()
        self.call_count = 0
        self._forced: Dict[str, FaultType] = {}
        self.register_tools()

    # -- registration ------------------------------------------------------

    def register_tools(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def tool(self, spec: ToolSpec) -> Callable[[Callable], Callable]:
        def decorator(fn: Callable[[JSONDict, JSONDict], JSONDict]) -> Callable:
            self._tools[spec.name] = spec
            self._handlers[spec.name] = fn
            return fn

        return decorator

    # -- discovery ---------------------------------------------------------

    @property
    def tools(self) -> List[ToolSpec]:
        return list(self._tools.values())

    def spec(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(f"{self.app}: unknown tool '{name}'")
        return self._tools[name]

    def list_tools(self) -> List[JSONDict]:
        return [t.to_mcp() for t in self._tools.values()]

    # -- credentials -------------------------------------------------------

    def _detect_mode(self) -> Mode:
        if all(os.environ.get(var) for var in self.credential_env) and self.credential_env:
            return Mode.LIVE
        return Mode.SIMULATED

    def credential(self, var: str) -> str:
        value = os.environ.get(var)
        if not value:
            raise ToolFault(FaultType.AUTH_EXPIRED, f"{var} is not set")
        return value

    def status(self) -> JSONDict:
        missing = [v for v in self.credential_env if not os.environ.get(v)]
        return {
            "app": self.app,
            "mode": self.mode.value,
            "tools": len(self._tools),
            "calls": self.call_count,
            "credentials_required": list(self.credential_env),
            "credentials_missing": missing,
            "connected": self.mode is Mode.LIVE or not missing,
        }

    # -- execution ---------------------------------------------------------

    def force_fault(self, tool_name: str, fault: Optional[FaultType]) -> None:
        """Pin a tool to always fail with `fault` (or clear it with None).

        This is how the rollback scenario is demonstrated without waiting for a
        real outage: the failure is injected at the app boundary, so every layer
        above it - gate, saga, logger - behaves exactly as it would in production.
        """
        if fault is None:
            self._forced.pop(tool_name, None)
        else:
            self._forced[tool_name] = fault

    def call(self, name: str, args: JSONDict, *, endpoint: str = "") -> ToolResult:
        """Execute a tool. Raises ToolFault - the gate is what catches it."""
        spec = self.spec(name)
        if name in self._forced:
            raise ToolFault(self._forced[name], f"{name}: injected outage at the app boundary",
                            endpoint=endpoint, detail={"forced": True})
        violations = SchemaValidator(spec.input_schema, name=name).validate(args)
        if violations:
            raise ToolFault(
                FaultType.VALIDATION_ERROR,
                f"{name}: " + "; ".join(str(v) for v in violations[:3]),
                endpoint=endpoint,
                detail={"violations": [str(v) for v in violations]},
            )

        ctx = {"endpoint": endpoint or self.api_base, "mode": self.mode, "spec": spec, "server": self}
        started = time.perf_counter()
        self.call_count += 1
        data = self._handlers[name](args, ctx)
        latency = (time.perf_counter() - started) * 1000
        return ToolResult(
            ok=True,
            data=data,
            mode=self.mode,
            endpoint=ctx["endpoint"],
            latency_ms=latency,
            summary=data.pop("_summary", "") if isinstance(data, dict) else "",
        )

    # -- simulation helpers ------------------------------------------------

    def _latency(self, lo_ms: float = 18.0, hi_ms: float = 90.0) -> None:
        """Simulated network time, so the visualiser shows a realistic waterfall."""
        time.sleep(self._rng.uniform(lo_ms, hi_ms) / 1000.0)

    def _fake_id(self, prefix: str, *parts: Any) -> str:
        digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
        return f"{prefix}_{digest[:20]}"

    # -- live HTTP helper --------------------------------------------------

    def http(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[JSONDict] = None,
        form_body: Optional[Dict[str, Any]] = None,
        timeout: float = 10.0,
    ) -> JSONDict:
        """Minimal JSON-over-HTTP client that maps transport errors to ToolFault.

        Kept dependency-free on purpose: the reliability story is weaker if the
        gate's own failure classification depends on a third-party client's
        retry behaviour. Triadr owns every retry decision.
        """
        body: Optional[bytes] = None
        hdrs = {"Accept": "application/json", "User-Agent": "Triadr/1.0 (+reliability-gate)"}
        hdrs.update(headers or {})

        if json_body is not None:
            body = json.dumps(json_body).encode()
            hdrs["Content-Type"] = "application/json"
        elif form_body is not None:
            body = urllib.parse.urlencode(_flatten_form(form_body)).encode()
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"

        request = urllib.request.Request(url, data=body, headers=hdrs, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8") or "{}"
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                detail = json.loads(raw)
            except ValueError:
                detail = {"raw": raw[:400]}
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            raise ToolFault(
                _status_to_fault(exc.code),
                f"HTTP {exc.code} from {urllib.parse.urlsplit(url).netloc}",
                retry_after=float(retry_after) if retry_after and retry_after.isdigit() else None,
                endpoint=url,
                detail=detail,
            ) from exc
        except TimeoutError as exc:
            raise ToolFault(FaultType.TIMEOUT, f"timed out after {timeout}s", endpoint=url) from exc
        except urllib.error.URLError as exc:
            raise ToolFault(FaultType.NETWORK_PARTITION, str(exc.reason), endpoint=url) from exc
        except json.JSONDecodeError as exc:
            raise ToolFault(FaultType.SCHEMA_DRIFT, "response was not valid JSON", endpoint=url) from exc


def _status_to_fault(code: int) -> FaultType:
    if code == 429:
        return FaultType.RATE_LIMITED
    if code == 401:
        return FaultType.AUTH_EXPIRED
    if code == 403:
        return FaultType.PERMISSION_DENIED
    if code == 404:
        return FaultType.NOT_FOUND
    if code == 409:
        return FaultType.IDEMPOTENCY_CONFLICT
    if code in (408, 504):
        return FaultType.TIMEOUT
    if code >= 500:
        return FaultType.SERVER_ERROR
    return FaultType.VALIDATION_ERROR


def _flatten_form(data: Dict[str, Any], prefix: str = "") -> List[tuple[str, str]]:
    """Stripe-style bracket encoding: {"metadata": {"pr": 42}} -> metadata[pr]=42."""
    pairs: List[tuple[str, str]] = []
    for key, value in data.items():
        field_name = f"{prefix}[{key}]" if prefix else key
        if isinstance(value, dict):
            pairs.extend(_flatten_form(value, field_name))
        elif isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    pairs.extend(_flatten_form(item, f"{field_name}[{i}]"))
                else:
                    pairs.append((f"{field_name}[{i}]", str(item)))
        elif isinstance(value, bool):
            pairs.append((field_name, "true" if value else "false"))
        elif value is not None:
            pairs.append((field_name, str(value)))
    return pairs
