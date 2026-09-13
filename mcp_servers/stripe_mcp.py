"""
Triadr - App #3: Stripe MCP server.

Tools cover settlement: check available balance, release the contractor escrow
as a Stripe Transfer, read it back, and reverse it. Every money-moving call
carries a caller-supplied Idempotency-Key, which is what lets the reliability
gate retry a payout whose response was lost in flight without paying twice.

LIVE mode needs STRIPE_SECRET_KEY. Use a test-mode key (sk_test_...) - Triadr
refuses to move money on a live key unless TRIADR_ALLOW_LIVE_MONEY=1.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict

from risk_gate import FaultType, ToolFault

from .base import JSONDict, MCPServer, Mode, SideEffect, ToolSpec

_CURRENCY = {"type": "string", "format": "currency-code", "description": "ISO-4217, lowercase"}
_IDEMPOTENCY = {"type": "string", "minLength": 8, "maxLength": 255,
                "description": "Idempotency key - replaying it must not move money twice"}


class StripeMCP(MCPServer):
    app = "stripe"
    api_base = "https://api.stripe.com/v1"
    credential_env = ("STRIPE_SECRET_KEY",)

    def __init__(self, *, mode=None, seed: int = 20260913) -> None:
        self._transfers: Dict[str, JSONDict] = {}
        self._by_idempotency: Dict[str, str] = {}
        self._balance_cents = 4_820_000  # $48,200.00 simulated available balance
        super().__init__(mode=mode, seed=seed)

    def _headers(self, idempotency_key: str | None = None) -> Dict[str, str]:
        key = self.credential("STRIPE_SECRET_KEY")
        headers = {"Authorization": f"Bearer {key}", "Stripe-Version": "2024-06-20"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _guard_live_money(self) -> None:
        key = os.environ.get("STRIPE_SECRET_KEY", "")
        if key.startswith("sk_live_") and os.environ.get("TRIADR_ALLOW_LIVE_MONEY") != "1":
            raise ToolFault(
                FaultType.PERMISSION_DENIED,
                "refusing to move real money: STRIPE_SECRET_KEY is a live key and "
                "TRIADR_ALLOW_LIVE_MONEY is not set to 1",
            )

    def register_tools(self) -> None:

        @self.tool(ToolSpec(
            name="stripe.get_balance",
            app=self.app,
            title="Get available balance",
            description="Read the connected Stripe account's available and pending balance before attempting a payout.",
            input_schema={
                "type": "object",
                "properties": {"currency": _CURRENCY},
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["currency", "available_cents"],
                "properties": {"currency": {"type": "string"},
                               "available_cents": {"type": "integer"},
                               "pending_cents": {"type": "integer"}},
            },
            side_effect=SideEffect.READ,
        ))
        def get_balance(args: JSONDict, ctx: JSONDict) -> JSONDict:
            currency = args.get("currency", "usd")
            if self.mode is Mode.LIVE:
                raw = self.http("GET", f"{self.api_base}/balance", headers=self._headers())
                available = next((b["amount"] for b in raw.get("available", []) if b["currency"] == currency), 0)
                pending = next((b["amount"] for b in raw.get("pending", []) if b["currency"] == currency), 0)
            else:
                self._latency(20, 65)
                available, pending = self._balance_cents, 132_500
            return {
                "currency": currency,
                "available_cents": available,
                "pending_cents": pending,
                "available": round(available / 100, 2),
                "_summary": f"{currency.upper()} {available / 100:,.2f} available, {pending / 100:,.2f} pending",
            }

        @self.tool(ToolSpec(
            name="stripe.release_escrow",
            app=self.app,
            title="Release contractor escrow",
            description=(
                "Release a held contractor payout as a Stripe Transfer to a connected account. "
                "Requires an idempotency key; replaying the same key returns the original transfer "
                "instead of moving money a second time."
            ),
            input_schema={
                "type": "object",
                "required": ["amount", "currency", "destination", "idempotency_key"],
                "properties": {
                    "amount": {"type": "number", "exclusiveMinimum": 0, "maximum": 1_000_000,
                               "description": "Major units, e.g. 2500.00 USD"},
                    "currency": _CURRENCY,
                    "destination": {"type": "string", "pattern": r"^acct_[A-Za-z0-9]+$",
                                    "description": "Stripe connected account id"},
                    "idempotency_key": _IDEMPOTENCY,
                    "description": {"type": "string", "maxLength": 200},
                    "metadata": {"type": "object"},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["id", "amount", "currency", "status"],
                "properties": {
                    "id": {"type": "string"}, "amount": {"type": "integer"},
                    "currency": {"type": "string"}, "status": {"type": "string"},
                    "destination": {"type": "string"}, "reversed": {"type": "boolean"},
                },
            },
            side_effect=SideEffect.PAYMENT,
            idempotent=True,
            compensated_by="stripe.reverse_transfer",
            timeout_s=20.0,
        ))
        def release_escrow(args: JSONDict, ctx: JSONDict) -> JSONDict:
            self._guard_live_money()
            cents = int(round(args["amount"] * 100))
            key = args["idempotency_key"]

            if self.mode is Mode.LIVE:
                body: JSONDict = {
                    "amount": cents,
                    "currency": args["currency"],
                    "destination": args["destination"],
                    "description": args.get("description", "Triadr contractor escrow release"),
                }
                if args.get("metadata"):
                    body["metadata"] = args["metadata"]
                raw = self.http("POST", f"{self.api_base}/transfers",
                                headers=self._headers(key), form_body=body)
                return {
                    "id": raw["id"], "amount": raw["amount"], "currency": raw["currency"],
                    "destination": raw["destination"], "status": "paid",
                    "reversed": bool(raw.get("reversed")), "created": raw.get("created"),
                    "_summary": f"transfer {raw['id']} - {raw['currency'].upper()} {raw['amount'] / 100:,.2f} released",
                }

            # --- simulated, but with real idempotency and real balance accounting
            self._latency(45, 140)
            if key in self._by_idempotency:
                existing = self._transfers[self._by_idempotency[key]]
                return {**existing, "_summary": f"idempotent replay of {existing['id']} - no second payout"}
            if cents > self._balance_cents:
                raise ToolFault(
                    FaultType.VALIDATION_ERROR,
                    f"insufficient available balance: need {cents / 100:,.2f}, have {self._balance_cents / 100:,.2f}",
                )
            transfer_id = self._fake_id("tr", key, cents, args["destination"])
            record = {
                "id": transfer_id, "amount": cents, "currency": args["currency"],
                "destination": args["destination"], "status": "paid", "reversed": False,
                "created": int(time.time()),
                "metadata": args.get("metadata", {}),
            }
            self._balance_cents -= cents
            self._transfers[transfer_id] = record
            self._by_idempotency[key] = transfer_id
            return {**record,
                    "_summary": f"transfer {transfer_id} - {args['currency'].upper()} {args['amount']:,.2f} released to {args['destination']}"}

        @self.tool(ToolSpec(
            name="stripe.get_transfer",
            app=self.app,
            title="Get transfer",
            description="Read a transfer back to confirm settlement - the verification step after a payout.",
            input_schema={
                "type": "object",
                "required": ["transfer_id"],
                "properties": {"transfer_id": {"type": "string", "pattern": r"^tr_[A-Za-z0-9]+$"}},
                "additionalProperties": False,
            },
            side_effect=SideEffect.READ,
        ))
        def get_transfer(args: JSONDict, ctx: JSONDict) -> JSONDict:
            tid = args["transfer_id"]
            if self.mode is Mode.LIVE:
                raw = self.http("GET", f"{self.api_base}/transfers/{tid}", headers=self._headers())
                return {"id": raw["id"], "amount": raw["amount"], "currency": raw["currency"],
                        "destination": raw["destination"], "reversed": bool(raw.get("reversed")),
                        "status": "reversed" if raw.get("reversed") else "paid",
                        "_summary": f"transfer {raw['id']} confirmed"}
            self._latency(15, 45)
            record = self._transfers.get(tid)
            if not record:
                raise ToolFault(FaultType.NOT_FOUND, f"no such transfer: {tid}")
            return {**record, "_summary": f"transfer {tid} confirmed - status {record['status']}"}

        @self.tool(ToolSpec(
            name="stripe.reverse_transfer",
            app=self.app,
            title="Reverse transfer (compensation)",
            description=(
                "Saga compensation for stripe.release_escrow - reverses a transfer so a workflow that "
                "failed after payment is left financially consistent rather than half-executed."
            ),
            input_schema={
                "type": "object",
                "required": ["transfer_id", "idempotency_key"],
                "properties": {
                    "transfer_id": {"type": "string", "pattern": r"^tr_[A-Za-z0-9]+$"},
                    "idempotency_key": _IDEMPOTENCY,
                    "amount": {"type": "number", "exclusiveMinimum": 0},
                    "reason": {"type": "string", "maxLength": 200},
                },
                "additionalProperties": False,
            },
            side_effect=SideEffect.PAYMENT,
            idempotent=True,
            compensates="stripe.release_escrow",
        ))
        def reverse_transfer(args: JSONDict, ctx: JSONDict) -> JSONDict:
            tid, key = args["transfer_id"], args["idempotency_key"]
            if self.mode is Mode.LIVE:
                body: JSONDict = {}
                if args.get("amount"):
                    body["amount"] = int(round(args["amount"] * 100))
                raw = self.http("POST", f"{self.api_base}/transfers/{tid}/reversals",
                                headers=self._headers(key), form_body=body or {"metadata": {"triadr": "compensation"}})
                return {"id": raw["id"], "transfer": tid, "amount": raw["amount"], "reversed": True,
                        "_summary": f"transfer {tid} reversed ({raw['amount'] / 100:,.2f})"}
            self._latency(30, 90)
            record = self._transfers.get(tid)
            if not record:
                raise ToolFault(FaultType.NOT_FOUND, f"no such transfer: {tid}")
            if record["reversed"]:
                return {"id": self._fake_id("trr", tid), "transfer": tid, "amount": record["amount"],
                        "reversed": True, "_summary": f"transfer {tid} was already reversed - idempotent no-op"}
            record["reversed"] = True
            record["status"] = "reversed"
            self._balance_cents += record["amount"]
            return {"id": self._fake_id("trr", tid, key), "transfer": tid, "amount": record["amount"],
                    "reversed": True, "reason": args.get("reason", "triadr saga compensation"),
                    "_summary": f"transfer {tid} reversed - {record['amount'] / 100:,.2f} returned to balance"}
