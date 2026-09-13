"""
Triadr - App #2: Telegram MCP server.

Tools cover the human-in-the-loop half: post an approval card carrying the
GitHub audit verdict with real inline Approve / Reject buttons, wait for a
human to press one, and post the settlement receipt. The card is
compensatable, so a failed payout retracts its own request instead of leaving
a stale approval sitting in the chat.

Why Telegram for approval: the Bot API delivers button presses through
long-polling (`getUpdates`), so the buttons genuinely work from a laptop with
no public callback URL - and a bot token takes one message to @BotFather.

LIVE mode needs TELEGRAM_BOT_TOKEN. The chat to post in comes from
TRIADR_TELEGRAM_CHAT_ID (a user or group must message the bot once first -
bots cannot open a conversation). Without a token the server simulates a
reviewer, so the whole demo runs offline.
"""

from __future__ import annotations

import html
import re
import secrets
import time
from typing import Any, Dict, List, Optional

from brand import RISK_BADGE, TRIADR_MARK
from risk_gate import FaultType, ToolFault

from .base import JSONDict, MCPServer, Mode, SideEffect, ToolSpec

# A chat is a numeric id (negative for groups) or a public @username.
_CHAT = {
    "anyOf": [
        {"type": "integer"},
        {"type": "string", "pattern": r"^(-?\d+|@[A-Za-z0-9_]{5,32})$"},
    ],
    "description": "Chat id (user or group) or public @channel username",
}
_MESSAGE_ID = {"type": "integer", "minimum": 1, "description": "Telegram message_id"}

_APPROVE = {"white_check_mark", "approve"}
_REJECT = {"x", "reject"}


class TelegramMCP(MCPServer):
    app = "telegram"
    api_base = "https://api.telegram.org"
    credential_env = ("TELEGRAM_BOT_TOKEN",)

    def __init__(self, *, mode=None, seed: int = 20260913, auto_approve: bool = True) -> None:
        self.auto_approve = auto_approve
        self._offset: Optional[int] = None      # getUpdates cursor
        self._decisions: Dict[int, JSONDict] = {}
        super().__init__(mode=mode, seed=seed)

    # -- transport ---------------------------------------------------------

    def _url(self, method: str) -> str:
        return f"{self.api_base}/bot{self.credential('TELEGRAM_BOT_TOKEN')}/{method}"

    @staticmethod
    def _redact(url: str) -> str:
        return re.sub(r"/bot[^/]+/", "/bot<redacted>/", url)

    def _tg(self, method: str, body: Optional[JSONDict] = None, *, timeout: float = 10.0) -> Any:
        """Call one Bot API method and unwrap `result`.

        The bot token lives in the URL path, so every fault the transport raises
        is re-raised with the token redacted before it can reach a log line.
        Telegram's 429 body carries `parameters.retry_after`, which the gate's
        backoff honours the same way it honours a Retry-After header.
        """
        try:
            raw = self.http("POST", self._url(method), json_body=body or {}, timeout=timeout)
        except ToolFault as fault:
            retry_after = fault.retry_after
            params = fault.detail.get("parameters") if isinstance(fault.detail, dict) else None
            if retry_after is None and isinstance(params, dict) and "retry_after" in params:
                retry_after = float(params["retry_after"])
            description = (fault.detail.get("description") if isinstance(fault.detail, dict) else None) or fault.message
            raise ToolFault(
                fault.fault, f"telegram.{method}: {description}",
                retry_after=retry_after, endpoint=self._redact(fault.endpoint or ""),
                detail={k: v for k, v in fault.detail.items() if k != "raw"} if isinstance(fault.detail, dict) else {},
            ) from None
        if not raw.get("ok"):
            raise ToolFault(FaultType.VALIDATION_ERROR, f"telegram.{method}: {raw.get('description', 'not ok')}",
                            detail=raw)
        return raw.get("result")

    def get_me(self) -> JSONDict:
        """Verify the token. Used by the live check; not a workflow tool."""
        return self._tg("getMe")

    def discover_chat(self) -> Optional[JSONDict]:
        """Find the most recent chat that has messaged the bot - the live check
        uses this to fill TRIADR_TELEGRAM_CHAT_ID for the operator."""
        self._tg("deleteWebhook", {"drop_pending_updates": False})
        updates = self._tg("getUpdates", {"timeout": 0, "allowed_updates": ["message"]}) or []
        for update in reversed(updates):
            chat = (update.get("message") or {}).get("chat")
            if chat:
                return {"id": chat["id"], "type": chat.get("type"),
                        "title": chat.get("title") or chat.get("username") or chat.get("first_name")}
        return None

    # -- card rendering ----------------------------------------------------

    @staticmethod
    def _card_text(audit: JSONDict, amount: float, currency: str, contractor: str) -> str:
        band = str(audit.get("risk_band", "unknown"))
        badge = RISK_BADGE.get(band, "[UNKNOWN]")
        reasons = [html.escape(str(r)) for r in (audit.get("reasons") or [])[:5]]
        title = html.escape(str(audit.get("title", "")))
        url = str(audit.get("url", "")) or ""
        pr_line = f'<a href="{html.escape(url)}">#{audit.get("pr_number")} {title}</a>' if url.startswith("http") \
            else f"#{audit.get('pr_number')} {title}"
        lines = [
            f"<b>{TRIADR_MARK} Triadr - payout approval required</b>",
            "",
            f"<b>Pull request</b>  {pr_line}",
            f"<b>Author</b>  {html.escape(str(audit.get('author', 'unknown')))}",
            f"<b>Risk</b>  <code>{badge}</code> {audit.get('risk_score')}/100",
            f"<b>Payout</b>  {currency.upper()} {amount:,.2f} → <code>{html.escape(contractor)}</code>",
        ]
        if reasons:
            lines += ["", "<b>Audit findings</b>"] + [f"• {r}" for r in reasons]
        lines += ["", f"<i>Posted {time.strftime('%H:%M:%S UTC', time.gmtime())} - press a button on this card.</i>",
                  "<i>Every step is gate-supervised and hash-chained.</i>"]
        return "\n".join(lines)

    @staticmethod
    def _keyboard(nonce: str) -> JSONDict:
        # callback_data is capped at 64 bytes; "triadr:approve:" + 12 hex = 27.
        return {"inline_keyboard": [[
            {"text": f"{TRIADR_MARK} Approve payout", "callback_data": f"triadr:approve:{nonce}"},
            {"text": "Reject", "callback_data": f"triadr:reject:{nonce}"},
        ]]}

    # -- tools -------------------------------------------------------------

    def register_tools(self) -> None:

        @self.tool(ToolSpec(
            name="telegram.post_approval_card",
            app=self.app,
            title="Post approval card",
            description=(
                "Post an approval card carrying the GitHub audit verdict and the proposed payout, "
                "with inline Approve / Reject buttons for the reviewing human."
            ),
            input_schema={
                "type": "object",
                "required": ["chat_id", "audit", "amount", "currency", "contractor"],
                "properties": {
                    "chat_id": _CHAT,
                    "audit": {"type": "object"},
                    "amount": {"type": "number", "exclusiveMinimum": 0, "maximum": 1_000_000},
                    "currency": {"type": "string", "format": "currency-code"},
                    "contractor": {"type": "string", "minLength": 1, "maxLength": 120},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["chat_id", "message_id", "nonce"],
                "properties": {"chat_id": _CHAT, "message_id": _MESSAGE_ID,
                               "nonce": {"type": "string", "minLength": 8}},
            },
            side_effect=SideEffect.WRITE,
            idempotent=False,
            compensated_by="telegram.delete_message",
        ))
        def post_approval_card(args: JSONDict, ctx: JSONDict) -> JSONDict:
            nonce = secrets.token_hex(6)
            text = self._card_text(args["audit"], args["amount"], args["currency"], args["contractor"])
            if self.mode is Mode.LIVE:
                sent = self._tg("sendMessage", {
                    "chat_id": args["chat_id"], "text": text, "parse_mode": "HTML",
                    "disable_web_page_preview": True, "reply_markup": self._keyboard(nonce),
                })
                return {"chat_id": sent["chat"]["id"], "message_id": sent["message_id"], "nonce": nonce,
                        "_summary": f"approval card posted to chat {sent['chat']['id']} (message {sent['message_id']})"}
            self._latency(35, 110)
            message_id = self._rng.randint(1000, 9999)
            return {"chat_id": args["chat_id"], "message_id": message_id, "nonce": nonce,
                    "_summary": f"approval card posted to chat {args['chat_id']} (message {message_id})"}

        @self.tool(ToolSpec(
            name="telegram.await_approval",
            app=self.app,
            title="Await human approval",
            description=(
                "Long-poll for the reviewer's button press on a posted approval card. Returns "
                "approved / rejected / timeout with who decided, and freezes the card's buttons."
            ),
            input_schema={
                "type": "object",
                "required": ["chat_id", "message_id", "nonce"],
                "properties": {
                    "chat_id": _CHAT,
                    "message_id": _MESSAGE_ID,
                    "nonce": {"type": "string", "minLength": 8},
                    "timeout_seconds": {"type": "number", "minimum": 0, "maximum": 900},
                    "poll_interval_seconds": {"type": "number", "minimum": 0.05, "maximum": 30},
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["decision", "message_id"],
                "properties": {
                    "decision": {"type": "string", "enum": ["approved", "rejected", "timeout"]},
                    "decided_by": {"type": ["string", "null"]},
                    "message_id": _MESSAGE_ID,
                },
            },
            side_effect=SideEffect.READ,
        ))
        def await_approval(args: JSONDict, ctx: JSONDict) -> JSONDict:
            chat_id, message_id, nonce = args["chat_id"], args["message_id"], args["nonce"]
            timeout = float(args.get("timeout_seconds", 30.0))
            interval = float(args.get("poll_interval_seconds", 2.0))
            approve, reject = f"triadr:approve:{nonce}", f"triadr:reject:{nonce}"

            if self.mode is Mode.LIVE:
                deadline = time.monotonic() + timeout
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    poll = int(max(0, min(interval, remaining, 25)))
                    params: JSONDict = {"timeout": poll, "allowed_updates": ["callback_query"]}
                    if self._offset is not None:
                        params["offset"] = self._offset
                    try:
                        updates = self._tg("getUpdates", params, timeout=poll + 15) or []
                    except ToolFault as fault:
                        # 409: a webhook is registered, which blocks polling. Clear it once.
                        if fault.fault is FaultType.IDEMPOTENCY_CONFLICT:
                            self._tg("deleteWebhook", {"drop_pending_updates": False})
                            continue
                        raise
                    for update in updates:
                        self._offset = update["update_id"] + 1
                        query = update.get("callback_query") or {}
                        data = query.get("data", "")
                        if data not in (approve, reject):
                            if query.get("id"):
                                self._tg("answerCallbackQuery", {
                                    "callback_query_id": query["id"], "show_alert": True,
                                    "text": "That card has expired - please use the newest card in this chat."})
                            stale = query.get("message") or {}
                            if stale.get("message_id") and data.startswith("triadr:"):
                                try:
                                    self._tg("editMessageReplyMarkup", {
                                        "chat_id": stale["chat"]["id"], "message_id": stale["message_id"],
                                        "reply_markup": {"inline_keyboard": []}})
                                except ToolFault:
                                    pass  # an already-frozen card is fine
                            continue
                        decision = "approved" if data == approve else "rejected"
                        who = query.get("from") or {}
                        decided_by = who.get("username") or who.get("first_name") or str(who.get("id", "reviewer"))
                        self._tg("answerCallbackQuery", {"callback_query_id": query["id"],
                                                         "text": f"Payout {decision}"})
                        # Freeze the card so a second press cannot flip the decision.
                        self._tg("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                                            "reply_markup": {"inline_keyboard": []}})
                        return {"decision": decision, "decided_by": decided_by, "message_id": message_id,
                                "_summary": f"{decision} by {decided_by}"}
                return {"decision": "timeout", "decided_by": None, "message_id": message_id,
                        "_summary": f"no decision within {timeout:.0f}s"}

            # Simulated reviewer: responds after a short, deterministic think time.
            self._latency(120, 260)
            decision = "approved" if self.auto_approve else "rejected"
            self._decisions[message_id] = {"decision": decision, "decided_by": "reviewer"}
            return {"decision": decision, "decided_by": "reviewer", "message_id": message_id,
                    "_summary": f"{decision} by reviewer (simulated)"}

        @self.tool(ToolSpec(
            name="telegram.post_message",
            app=self.app,
            title="Post message",
            description="Post an HTML-formatted status message - used for run receipts and incident notices.",
            input_schema={
                "type": "object",
                "required": ["chat_id", "text"],
                "properties": {
                    "chat_id": _CHAT,
                    "text": {"type": "string", "minLength": 1, "maxLength": 4000},
                    "reply_to_message_id": _MESSAGE_ID,
                },
                "additionalProperties": False,
            },
            output_schema={
                "type": "object",
                "required": ["chat_id", "message_id"],
                "properties": {"chat_id": _CHAT, "message_id": _MESSAGE_ID},
            },
            side_effect=SideEffect.WRITE,
            idempotent=False,
            compensated_by="telegram.delete_message",
        ))
        def post_message(args: JSONDict, ctx: JSONDict) -> JSONDict:
            if self.mode is Mode.LIVE:
                body: JSONDict = {"chat_id": args["chat_id"], "text": args["text"], "parse_mode": "HTML",
                                  "disable_web_page_preview": True}
                if args.get("reply_to_message_id"):
                    body["reply_parameters"] = {"message_id": args["reply_to_message_id"],
                                                "allow_sending_without_reply": True}
                sent = self._tg("sendMessage", body)
                return {"chat_id": sent["chat"]["id"], "message_id": sent["message_id"],
                        "_summary": f"message {sent['message_id']} posted to chat {sent['chat']['id']}"}
            self._latency(25, 80)
            message_id = self._rng.randint(1000, 9999)
            return {"chat_id": args["chat_id"], "message_id": message_id,
                    "_summary": f"message posted to chat {args['chat_id']}: {args['text'][:60]}"}

        @self.tool(ToolSpec(
            name="telegram.delete_message",
            app=self.app,
            title="Delete message (compensation)",
            description=(
                "Saga compensation for telegram.post_approval_card / telegram.post_message - retracts "
                "the card so no stale approval request is left behind."
            ),
            input_schema={
                "type": "object",
                "required": ["chat_id", "message_id"],
                "properties": {"chat_id": _CHAT, "message_id": _MESSAGE_ID},
                "additionalProperties": False,
            },
            side_effect=SideEffect.WRITE,
            compensates="telegram.post_approval_card",
        ))
        def delete_message(args: JSONDict, ctx: JSONDict) -> JSONDict:
            if self.mode is Mode.LIVE:
                self._tg("deleteMessage", {"chat_id": args["chat_id"], "message_id": args["message_id"]})
            else:
                self._latency(15, 40)
            return {"deleted": True, "chat_id": args["chat_id"], "message_id": args["message_id"],
                    "_summary": f"retracted message {args['message_id']} from chat {args['chat_id']}"}
