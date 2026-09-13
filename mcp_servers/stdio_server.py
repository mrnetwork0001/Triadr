"""
Triadr - MCP stdio server.

Exposes all 14 Triadr tools (GitHub + Telegram + Stripe) to any MCP host over the
standard newline-delimited JSON-RPC 2.0 stdio transport. Dependency-free.

Every tool call is executed *through the reliability gate*, so an MCP host
driving Triadr inherits retry, rerouting, idempotency and compensation for
free - the reliability engine is not a demo wrapper, it is the transport.

Register with Claude Code:

    claude mcp add triadr -- python3 /Users/mrnetwork/Triadr/mcp_servers/stdio_server.py

or in an MCP host config:

    {"mcpServers": {"triadr": {"command": "python3",
      "args": ["/Users/mrnetwork/Triadr/mcp_servers/stdio_server.py"]}}}
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from env import load_env  # noqa: E402

load_env()

from risk_gate import ChaosProfile, ReliabilityGate, ToolFault, Verdict  # noqa: E402
from mcp_servers.registry import MCPRegistry  # noqa: E402

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "triadr", "title": "Triadr Reliability Engine", "version": "1.0.0"}

INSTRUCTIONS = (
    "Triadr connects three external apps behind one self-healing gate: GitHub (code audit), "
    "Telegram (human approval) and Stripe (escrow payout). Every tool call is retried, rerouted, "
    "deduplicated and - if unrecoverable - compensated, so a multi-step workflow is never left "
    "half-executed. Call github.audit_pull_request first, gate the payout on "
    "telegram.await_approval, then settle with stripe.release_escrow using a stable idempotency_key."
)


class TriadrStdioServer:
    def __init__(self) -> None:
        chaos = ChaosProfile.storm() if os.environ.get("TRIADR_CHAOS") == "1" else ChaosProfile()
        self.registry = MCPRegistry()
        self.gate = ReliabilityGate(chaos=chaos, endpoints=self.registry.endpoints())
        self._initialized = False

    # -- JSON-RPC plumbing -------------------------------------------------

    def serve(self, stdin=sys.stdin, stdout=sys.stdout) -> None:
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                self._write(stdout, {"jsonrpc": "2.0", "id": None,
                                     "error": {"code": -32700, "message": "parse error"}})
                continue
            response = self.handle(message)
            if response is not None:
                self._write(stdout, response)

    @staticmethod
    def _write(stdout, message: Dict[str, Any]) -> None:
        stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
        stdout.flush()

    def handle(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

        # Notifications carry no id and expect no response.
        if msg_id is None and method and method.startswith("notifications/"):
            if method == "notifications/initialized":
                self._initialized = True
            return None

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}, "logging": {}},
                    "serverInfo": SERVER_INFO,
                    "instructions": INSTRUCTIONS,
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.registry.list_tools()}
            elif method == "tools/call":
                result = self._call_tool(params)
            else:
                return {"jsonrpc": "2.0", "id": msg_id,
                        "error": {"code": -32601, "message": f"method not found: {method}"}}
        except Exception as exc:  # protocol-level failure
            return {"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": -32603, "message": f"{type(exc).__name__}: {exc}"}}

        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    # -- tool execution through the gate -----------------------------------

    def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name", "")
        args = params.get("arguments") or {}
        spec = self.registry.spec(name)

        def executor(*, payload: Dict[str, Any], endpoint: str) -> Dict[str, Any]:
            return self.registry.call(name, payload, endpoint=endpoint).data

        outcome = self.gate.guard(
            app=spec.app,
            tool=name,
            payload=args,
            executor=executor,
            schema=spec.input_schema,
            output_schema=spec.output_schema,
            idempotency_key=args.get("idempotency_key"),
            side_effect=spec.side_effect.value,
        )

        header = f"[{outcome.verdict.value}] {outcome.reason}"
        if outcome.ok:
            body = json.dumps(outcome.result, indent=2, default=str)
            return {
                "content": [{"type": "text", "text": f"{header}\n\n{body}"}],
                "structuredContent": outcome.result if isinstance(outcome.result, dict) else {"result": outcome.result},
                "isError": False,
                "_meta": {"triadr/gate": outcome.to_dict()},
            }
        return {
            "content": [{"type": "text", "text": header}],
            "isError": True,
            "_meta": {"triadr/gate": outcome.to_dict()},
        }


def main() -> None:
    TriadrStdioServer().serve()


if __name__ == "__main__":
    main()
