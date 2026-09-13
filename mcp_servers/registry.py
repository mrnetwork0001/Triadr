"""
Triadr - MCP tool registry.

One namespace across all three connected apps. The registry is what the agent
and the FastAPI layer talk to; it resolves a fully-qualified tool name
(`stripe.release_escrow`) to the owning server, and exposes the combined
`tools/list` catalogue an MCP host would see.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .base import JSONDict, MCPServer, Mode, ToolResult, ToolSpec
from .github_mcp import GitHubMCP
from .telegram_mcp import TelegramMCP
from .stripe_mcp import StripeMCP


class MCPRegistry:
    """Aggregates the three app servers into a single MCP surface."""

    def __init__(self, *, mode: Optional[Mode] = None, auto_approve: bool = True, seed: int = 20260913) -> None:
        self.github = GitHubMCP(mode=mode, seed=seed)
        self.telegram = TelegramMCP(mode=mode, seed=seed, auto_approve=auto_approve)
        self.stripe = StripeMCP(mode=mode, seed=seed)
        self._servers: Dict[str, MCPServer] = {
            "github": self.github,
            "telegram": self.telegram,
            "stripe": self.stripe,
        }

    # -- discovery ---------------------------------------------------------

    @property
    def servers(self) -> List[MCPServer]:
        return list(self._servers.values())

    def server_for(self, tool_name: str) -> MCPServer:
        app = tool_name.split(".", 1)[0]
        if app not in self._servers:
            raise KeyError(f"unknown app '{app}' in tool name '{tool_name}'")
        return self._servers[app]

    def spec(self, tool_name: str) -> ToolSpec:
        return self.server_for(tool_name).spec(tool_name)

    def list_tools(self) -> List[JSONDict]:
        catalogue: List[JSONDict] = []
        for server in self._servers.values():
            catalogue.extend(server.list_tools())
        return catalogue

    def tool_names(self) -> List[str]:
        return [t["name"] for t in self.list_tools()]

    def endpoints(self) -> Dict[str, List[str]]:
        """Gateway list the reliability gate routes across, per app.

        SIMULATED: three logical gateways (primary, replica, vendor), so the
        failover path is exercised and visible in the dashboard.

        LIVE: exactly one endpoint - the real vendor API - unless the operator
        configures more via TRIADR_<APP>_ENDPOINTS (comma-separated). The
        in-process servers have no second real gateway to reroute to, and
        reporting "rerouted to replica" when both names hit the same API would
        be a cosmetic claim. Retry, backoff, breakers, idempotency and rollback
        are all still fully real against a single endpoint.
        """
        out: Dict[str, List[str]] = {}
        for app, server in self._servers.items():
            configured = os.environ.get(f"TRIADR_{app.upper()}_ENDPOINTS", "")
            custom = [e.strip() for e in configured.split(",") if e.strip()]
            if custom:
                out[app] = custom
            elif server.mode is Mode.LIVE:
                out[app] = [server.api_base]
            else:
                out[app] = [f"mcp://{app}/primary", f"mcp://{app}/replica", server.api_base]
        return out

    # -- execution ---------------------------------------------------------

    def call(self, tool_name: str, args: JSONDict, *, endpoint: str = "") -> ToolResult:
        return self.server_for(tool_name).call(tool_name, args, endpoint=endpoint)

    def force_fault(self, tool_name: str, fault) -> None:
        """Pin one tool to a hard outage - used by the rollback demo scenario."""
        self.server_for(tool_name).force_fault(tool_name, fault)

    # -- status ------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        apps = [s.status() for s in self._servers.values()]
        return {
            "apps": apps,
            "connected_count": sum(1 for a in apps if a["connected"]),
            "live_count": sum(1 for a in apps if a["mode"] == Mode.LIVE.value),
            "tool_count": sum(a["tools"] for a in apps),
            "total_calls": sum(a["calls"] for a in apps),
        }
