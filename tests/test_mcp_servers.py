"""Tests for the three connected apps' MCP tool bindings."""

import json

import pytest

from mcp_servers import GitHubMCP, MCPRegistry, Mode, SideEffect, StripeMCP, TelegramMCP
from mcp_servers.stdio_server import TriadrStdioServer
from risk_gate import FaultType, ToolFault


@pytest.fixture
def registry() -> MCPRegistry:
    return MCPRegistry()


class TestCatalogue:
    def test_three_apps_are_connected(self, registry):
        assert {s.app for s in registry.servers} == {"github", "telegram", "stripe"}

    def test_every_tool_declares_a_valid_mcp_shape(self, registry):
        for tool in registry.list_tools():
            assert tool["name"] and tool["description"]
            assert tool["inputSchema"]["type"] == "object"
            assert set(tool["annotations"]) >= {"readOnlyHint", "idempotentHint"}
            assert tool["name"].split(".")[0] == tool["_triadr"]["app"]

    def test_catalogue_is_json_serialisable(self, registry):
        json.dumps(registry.list_tools())

    def test_every_write_tool_declares_a_compensation(self, registry):
        for tool in registry.list_tools():
            spec = registry.spec(tool["name"])
            if spec.side_effect in (SideEffect.WRITE, SideEffect.PAYMENT) and not spec.compensates:
                assert spec.compensated_by, f"{spec.name} mutates state with no rollback path"

    def test_no_credentials_means_simulated_mode(self, registry, monkeypatch):
        for app in registry.status()["apps"]:
            assert app["mode"] == "SIMULATED"


class TestGitHub:
    def test_audit_produces_a_bounded_explainable_score(self):
        gh = GitHubMCP()
        audit = gh.call("github.audit_pull_request", {"repo": "acme/api", "pr_number": 42}).data
        assert 0 <= audit["risk_score"] <= 100
        assert audit["risk_band"] in ("low", "medium", "high")
        assert audit["reasons"], "a risk score with no rationale is not auditable"

    def test_sensitive_paths_raise_the_score(self):
        gh = GitHubMCP()
        safe = gh._score([{"filename": "docs/readme.md", "changes": 4}], {"state": "success", "failing": 0})
        risky = gh._score([{"filename": "services/payments/stripe.py", "changes": 4}],
                          {"state": "success", "failing": 0})
        assert risky["risk_score"] > safe["risk_score"]

    def test_failing_checks_force_human_approval(self):
        gh = GitHubMCP()
        verdict = gh._score([{"filename": "tests/test_x.py", "changes": 2}], {"state": "failure", "failing": 1})
        assert verdict["requires_human_approval"] and not verdict["auto_mergeable"]

    def test_invalid_repo_is_rejected_by_the_schema(self):
        with pytest.raises(ToolFault) as exc:
            GitHubMCP().call("github.get_pull_request", {"repo": "not-a-repo", "pr_number": 1})
        assert exc.value.fault is FaultType.VALIDATION_ERROR


class TestTelegram:
    AUDIT = {"pr_number": 42, "title": "Add <escrow>", "risk_score": 88, "risk_band": "high",
             "reasons": ["touches payments & auth"], "url": "https://github.com/o/r/pull/42", "author": "octocat"}

    def test_card_text_carries_the_audit_and_escapes_html(self):
        text = TelegramMCP._card_text(self.AUDIT, 2500.0, "usd", "acct_1")
        assert "88/100" in text and "USD 2,500.00" in text and "acct_1" in text
        assert "&lt;escrow&gt;" in text and "payments &amp; auth" in text, "user content must be HTML-escaped"
        assert 'href="https://github.com/o/r/pull/42"' in text

    def test_keyboard_has_approve_and_reject_bound_to_the_nonce(self):
        kb = TelegramMCP._keyboard("abc123def456")
        buttons = [b for row in kb["inline_keyboard"] for b in row]
        assert [b["callback_data"] for b in buttons] == ["triadr:approve:abc123def456", "triadr:reject:abc123def456"]
        assert all(len(b["callback_data"].encode()) <= 64 for b in buttons), "Telegram caps callback_data at 64 bytes"

    def test_card_returns_ids_the_later_steps_need(self):
        tg = TelegramMCP()
        card = tg.call("telegram.post_approval_card", {
            "chat_id": "@triadr_approvals", "audit": self.AUDIT, "amount": 10.0,
            "currency": "usd", "contractor": "acct_1"}).data
        assert card["chat_id"] == "@triadr_approvals" and card["message_id"] >= 1 and len(card["nonce"]) >= 8

    def test_rejection_is_reported_faithfully(self):
        tg = TelegramMCP(auto_approve=False)
        card = tg.call("telegram.post_approval_card", {
            "chat_id": -1001, "audit": {"pr_number": 1}, "amount": 10.0,
            "currency": "usd", "contractor": "acct_1"}).data
        decision = tg.call("telegram.await_approval", {
            "chat_id": -1001, "message_id": card["message_id"], "nonce": card["nonce"]}).data
        assert decision["decision"] == "rejected"

    @pytest.mark.parametrize("chat", [12345, -1001234567890, "@triadr_approvals", "-42"])
    def test_chat_id_accepts_ints_negative_groups_and_usernames(self, chat):
        TelegramMCP().call("telegram.post_message", {"chat_id": chat, "text": "hi"})

    def test_a_bare_word_is_not_a_chat(self):
        with pytest.raises(ToolFault) as exc:
            TelegramMCP().call("telegram.post_message", {"chat_id": "eng-approvals", "text": "hi"})
        assert exc.value.fault is FaultType.VALIDATION_ERROR


class TestStripe:
    def test_a_replayed_idempotency_key_does_not_pay_twice(self):
        stripe = StripeMCP()
        args = {"amount": 100.0, "currency": "usd", "destination": "acct_1",
                "idempotency_key": "run-1-payout"}
        first = stripe.call("stripe.release_escrow", args).data
        before = stripe._balance_cents
        second = stripe.call("stripe.release_escrow", args).data
        assert first["id"] == second["id"]
        assert stripe._balance_cents == before, "a replay must not move money again"

    def test_reversal_restores_the_balance(self):
        stripe = StripeMCP()
        opening = stripe._balance_cents
        transfer = stripe.call("stripe.release_escrow", {
            "amount": 250.0, "currency": "usd", "destination": "acct_1",
            "idempotency_key": "run-2-payout"}).data
        assert stripe._balance_cents == opening - 25_000
        stripe.call("stripe.reverse_transfer", {"transfer_id": transfer["id"],
                                                "idempotency_key": "run-2-rev"})
        assert stripe._balance_cents == opening

    def test_double_reversal_is_a_no_op(self):
        stripe = StripeMCP()
        transfer = stripe.call("stripe.release_escrow", {
            "amount": 10.0, "currency": "usd", "destination": "acct_1",
            "idempotency_key": "run-3-payout"}).data
        stripe.call("stripe.reverse_transfer", {"transfer_id": transfer["id"], "idempotency_key": "run-3-rev-a"})
        opening = stripe._balance_cents
        stripe.call("stripe.reverse_transfer", {"transfer_id": transfer["id"], "idempotency_key": "run-3-rev-b"})
        assert stripe._balance_cents == opening

    def test_overdraft_is_refused(self):
        stripe = StripeMCP()
        with pytest.raises(ToolFault) as exc:
            stripe.call("stripe.release_escrow", {"amount": 999_999.0, "currency": "usd",
                                                  "destination": "acct_1", "idempotency_key": "overdraft-1"})
        assert exc.value.fault is FaultType.VALIDATION_ERROR
        assert "insufficient" in exc.value.message

    def test_a_live_key_cannot_move_money_without_an_explicit_opt_in(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_pretend")
        monkeypatch.delenv("TRIADR_ALLOW_LIVE_MONEY", raising=False)
        stripe = StripeMCP(mode=Mode.SIMULATED)
        with pytest.raises(ToolFault) as exc:
            stripe.call("stripe.release_escrow", {"amount": 1.0, "currency": "usd",
                                                  "destination": "acct_1", "idempotency_key": "live-guard-1"})
        assert exc.value.fault is FaultType.PERMISSION_DENIED

    def test_missing_transfer_is_not_found(self):
        with pytest.raises(ToolFault) as exc:
            StripeMCP().call("stripe.get_transfer", {"transfer_id": "tr_nope"})
        assert exc.value.fault is FaultType.NOT_FOUND


class TestFaultInjection:
    def test_forced_fault_surfaces_at_the_app_boundary(self, registry):
        registry.force_fault("stripe.release_escrow", FaultType.SERVER_ERROR)
        with pytest.raises(ToolFault) as exc:
            registry.call("stripe.release_escrow", {"amount": 1.0, "currency": "usd",
                                                    "destination": "acct_1", "idempotency_key": "x"})
        assert exc.value.fault is FaultType.SERVER_ERROR

    def test_forced_fault_can_be_cleared(self, registry):
        registry.force_fault("stripe.get_balance", FaultType.TIMEOUT)
        registry.force_fault("stripe.get_balance", None)
        assert registry.call("stripe.get_balance", {}).ok


class TestStdioProtocol:
    """The MCP JSON-RPC surface an external host would actually drive."""

    def setup_method(self):
        self.server = TriadrStdioServer()

    def rpc(self, method, params=None, msg_id=1):
        return self.server.handle({"jsonrpc": "2.0", "id": msg_id, "method": method,
                                   "params": params or {}})

    def test_initialize_advertises_tools(self):
        result = self.rpc("initialize")["result"]
        assert result["protocolVersion"]
        assert result["capabilities"]["tools"] is not None
        assert result["serverInfo"]["name"] == "triadr"

    def test_notifications_get_no_response(self):
        assert self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None

    def test_tools_list_returns_the_whole_catalogue(self):
        tools = self.rpc("tools/list")["result"]["tools"]
        assert len(tools) == 14
        assert {t["name"].split(".")[0] for t in tools} == {"github", "telegram", "stripe"}

    def test_tools_call_runs_through_the_gate(self):
        result = self.rpc("tools/call", {"name": "github.audit_pull_request",
                                         "arguments": {"repo": "a/b", "pr_number": 7}})["result"]
        assert result["isError"] is False
        assert result["_meta"]["triadr/gate"]["verdict"] in ("ALLOW", "SELF_HEALED")

    def test_a_bad_payload_is_blocked_not_executed(self):
        result = self.rpc("tools/call", {"name": "stripe.release_escrow",
                                         "arguments": {"amount": -1, "currency": "usd",
                                                       "destination": "acct_1",
                                                       "idempotency_key": "probe-key"}})["result"]
        assert result["isError"] is True
        assert result["_meta"]["triadr/gate"]["verdict"] == "BLOCKED"

    def test_unknown_method_returns_a_jsonrpc_error(self):
        assert self.rpc("does/not/exist")["error"]["code"] == -32601
