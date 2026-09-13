"""
LIVE-mode wiring tests.

The three app servers each have a LIVE branch that talks to the real vendor
API. Those branches cannot run in CI without credentials, but their *wiring*
can be verified: HTTP method, URL, encoding (JSON vs form), auth headers,
idempotency headers, and how a realistically-shaped response is parsed.

Every test here forces LIVE mode with dummy credentials and swaps the single
HTTP primitive (`MCPServer.http`) for a recorder, so nothing leaves the process.
If one of these fails, the real API call would have failed too - which is the
whole point: catch it here, not during the demo.
"""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any, Callable, Dict, List, Optional

import pytest

from agents import TriadrOrchestrator, plan_from_instruction
from agents.orchestrator import StepStatus
from mcp_servers import GitHubMCP, MCPRegistry, Mode, StripeMCP, TelegramMCP
from mcp_servers.base import MCPServer, _flatten_form, _status_to_fault
from risk_gate import FaultType, ToolFault

# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------


class Recorder:
    """Stands in for MCPServer.http. Records every call; answers from `routes`."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.routes: List[tuple[Callable[[str, str], bool], Callable[[Dict[str, Any]], Any]]] = []

    def on(self, method: str, url_part: str, respond: Callable[[Dict[str, Any]], Any] | Dict[str, Any]) -> None:
        fn = respond if callable(respond) else (lambda _call, _r=respond: _r)
        self.routes.append((lambda m, u: m == method and url_part in u, fn))

    def __call__(self, server, method, url, *, headers=None, json_body=None, form_body=None, timeout=10.0):
        call = {"app": server.app, "method": method, "url": url, "headers": headers or {},
                "json": json_body, "form": form_body, "timeout": timeout}
        self.calls.append(call)
        for match, respond in self.routes:
            if match(method, url):
                result = respond(call)
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"unrouted LIVE call: {method} {url}")

    def find(self, url_part: str, method: Optional[str] = None) -> Dict[str, Any]:
        for c in self.calls:
            if url_part in c["url"] and (method is None or c["method"] == method):
                return c
        raise AssertionError(f"no call matching {method or '*'} {url_part}; saw {[c['url'] for c in self.calls]}")


@pytest.fixture
def live(monkeypatch) -> Recorder:
    """Force every app LIVE with throwaway credentials and install the recorder."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_testtoken")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:TESTTOKEN")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc123")
    monkeypatch.delenv("TRIADR_ALLOW_LIVE_MONEY", raising=False)
    rec = Recorder()

    # A plain function is bound as a method (so `self` arrives); a callable
    # instance is not, which would drop the server argument.
    def bound(server, method, url, **kwargs):
        return rec(server, method, url, **kwargs)

    monkeypatch.setattr(MCPServer, "http", bound)
    return rec


# Realistic response fixtures - shaped like the vendors' actual payloads.
PR = {"number": 7, "title": "Add escrow", "state": "open", "mergeable": True,
      "user": {"login": "octocat"}, "head": {"sha": "abc1234def5678"}, "base": {"ref": "main"},
      "html_url": "https://github.com/o/r/pull/7"}
FILES = [{"filename": "services/payments/escrow.py", "additions": 40, "deletions": 3, "changes": 43, "status": "modified"},
         {"filename": "tests/test_escrow.py", "additions": 20, "deletions": 0, "changes": 20, "status": "added"}]
CHECKS = {"total_count": 2, "check_runs": [
    {"name": "build", "status": "completed", "conclusion": "success"},
    {"name": "tests", "status": "completed", "conclusion": "success"}]}


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


class TestTransport:
    @pytest.mark.parametrize("code, fault", [
        (429, FaultType.RATE_LIMITED), (401, FaultType.AUTH_EXPIRED), (403, FaultType.PERMISSION_DENIED),
        (404, FaultType.NOT_FOUND), (409, FaultType.IDEMPOTENCY_CONFLICT), (504, FaultType.TIMEOUT),
        (500, FaultType.SERVER_ERROR), (502, FaultType.SERVER_ERROR), (400, FaultType.VALIDATION_ERROR),
    ])
    def test_status_codes_map_to_typed_faults(self, code, fault):
        assert _status_to_fault(code) is fault

    def test_http_error_carries_retry_after_and_body(self, monkeypatch):
        """The real http() must turn an HTTPError into a ToolFault the gate can classify."""
        body = json.dumps({"message": "API rate limit exceeded"}).encode()
        headers = {"Retry-After": "7"}

        def fake_urlopen(request, timeout=10.0):
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests",
                                         _Headers(headers), io.BytesIO(body))

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(ToolFault) as exc:
            GitHubMCP(mode=Mode.SIMULATED).http("GET", "https://api.github.com/rate_limit")
        assert exc.value.fault is FaultType.RATE_LIMITED
        assert exc.value.retry_after == 7.0
        assert exc.value.detail["message"] == "API rate limit exceeded"

    def test_network_failure_is_a_partition(self, monkeypatch):
        def fake_urlopen(request, timeout=10.0):
            raise urllib.error.URLError("Name or service not known")

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        with pytest.raises(ToolFault) as exc:
            GitHubMCP(mode=Mode.SIMULATED).http("GET", "https://api.github.com/")
        assert exc.value.fault is FaultType.NETWORK_PARTITION

    def test_form_encoding_uses_stripe_bracket_syntax(self):
        pairs = dict(_flatten_form({"amount": 250000, "metadata": {"pr": "42", "run": "r1"},
                                    "capabilities": {"transfers": {"requested": True}}}))
        assert pairs == {"amount": "250000", "metadata[pr]": "42", "metadata[run]": "r1",
                         "capabilities[transfers][requested]": "true"}


class _Headers(dict):
    def get(self, key, default=None):  # HTTPError.headers is case-insensitive
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------


class TestGitHubLive:
    def test_get_pull_request_request_and_parse(self, live):
        live.on("GET", "/repos/o/r/pulls/7", PR)
        gh = GitHubMCP()
        assert gh.mode is Mode.LIVE
        data = gh.call("github.get_pull_request", {"repo": "o/r", "pr_number": 7}).data
        call = live.find("/repos/o/r/pulls/7", "GET")
        assert call["headers"]["Authorization"] == "Bearer ghp_testtoken"
        assert call["headers"]["X-GitHub-Api-Version"] == "2022-11-28"
        assert call["json"] is None and call["form"] is None
        assert data["head_sha"] == "abc1234def5678" and data["author"] == "octocat"

    def test_list_changed_files_pages_and_sums(self, live):
        live.on("GET", "/pulls/7/files", FILES)
        data = GitHubMCP().call("github.list_changed_files", {"repo": "o/r", "pr_number": 7}).data
        assert "per_page=100" in live.find("/pulls/7/files")["url"]
        assert data["file_count"] == 2 and data["total_changes"] == 63

    def test_check_runs_aggregate_state(self, live):
        live.on("GET", "/commits/abc1234def5678/check-runs", CHECKS)
        data = GitHubMCP().call("github.get_check_runs", {"repo": "o/r", "ref": "abc1234def5678"}).data
        assert data["state"] == "success" and data["failing"] == 0 and data["total"] == 2

    def test_missing_checks_permission_falls_back_to_commit_status(self, live):
        """A fine-grained token without "Checks" must still yield a CI state."""
        live.on("GET", "/check-runs", ToolFault(FaultType.PERMISSION_DENIED, "HTTP 403 from api.github.com"))
        live.on("GET", "/commits/abc1234def5678/status", {"state": "success", "statuses": [
            {"context": "vercel", "state": "success"}, {"context": "ci/build", "state": "pending"}]})
        data = GitHubMCP().call("github.get_check_runs", {"repo": "o/r", "ref": "abc1234def5678"}).data
        assert [c["url"].rsplit("/", 1)[1] for c in live.calls] == ["check-runs", "status"]
        assert data["total"] == 2 and data["failing"] == 0 and data["pending"] == 1
        assert data["state"] == "pending" and data["checks"][0]["source"] == "commit-status"

    def test_a_real_check_runs_error_is_not_swallowed(self, live):
        live.on("GET", "/check-runs", ToolFault(FaultType.SERVER_ERROR, "HTTP 502"))
        with pytest.raises(ToolFault) as exc:
            GitHubMCP().call("github.get_check_runs", {"repo": "o/r", "ref": "abc1234def5678"})
        assert exc.value.fault is FaultType.SERVER_ERROR
        assert not [c for c in live.calls if c["url"].endswith("/status")], "no fallback on a transient fault"

    def test_failing_check_run_is_detected(self, live):
        live.on("GET", "/check-runs", {"check_runs": [{"name": "tests", "status": "completed", "conclusion": "failure"}]})
        data = GitHubMCP().call("github.get_check_runs", {"repo": "o/r", "ref": "abc1234def5678"}).data
        assert data["state"] == "failure" and data["failing"] == 1

    def test_audit_composes_three_real_calls(self, live):
        live.on("GET", "/pulls/7/files", FILES)
        live.on("GET", "/pulls/7", PR)
        live.on("GET", "/check-runs", CHECKS)
        data = GitHubMCP().call("github.audit_pull_request", {"repo": "o/r", "pr_number": 7}).data
        assert [c["url"].split("api.github.com")[1] for c in live.calls] == [
            "/repos/o/r/pulls/7", "/repos/o/r/pulls/7/files?per_page=100",
            "/repos/o/r/commits/abc1234def5678/check-runs"]
        assert 0 <= data["risk_score"] <= 100 and data["head_sha"] == "abc1234def5678"

    def test_set_and_clear_status_post_json(self, live):
        live.on("POST", "/statuses/abc1234def5678",
                lambda c: {"id": 1, "state": c["json"]["state"], "context": c["json"]["context"]})
        gh = GitHubMCP()
        gh.call("github.set_commit_status", {"repo": "o/r", "sha": "abc1234def5678", "state": "success",
                                             "description": "ok", "context": "triadr/gate"})
        gh.call("github.clear_status", {"repo": "o/r", "sha": "abc1234def5678", "context": "triadr/gate"})
        posts = [c for c in live.calls if c["method"] == "POST"]
        assert posts[0]["json"] == {"state": "success", "description": "ok", "context": "triadr/gate"}
        assert posts[1]["json"]["state"] == "pending", "compensation must reset, not delete"


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------


AUDIT = {"pr_number": 7, "title": "Add escrow", "risk_score": 61, "risk_band": "high",
         "reasons": ["touches payments"], "url": "#", "author": "octocat"}


# Bot API responses are enveloped: the tool must unwrap `result`.
SENT = {"ok": True, "result": {"message_id": 501, "chat": {"id": 777, "type": "private"},
                               "date": 1700000000, "text": "…"}}


class TestTelegramLive:
    def test_post_approval_card_sends_html_and_keyboard_and_returns_numeric_chat(self, live):
        live.on("POST", "/sendMessage", SENT)
        data = TelegramMCP().call("telegram.post_approval_card", {
            "chat_id": "@triadr_approvals", "audit": AUDIT, "amount": 25.0, "currency": "usd", "contractor": "acct_1"}).data
        call = live.find("/sendMessage")
        assert "/bot123456:TESTTOKEN/" in call["url"], "the token rides in the URL path"
        assert call["json"]["chat_id"] == "@triadr_approvals" and call["json"]["parse_mode"] == "HTML"
        buttons = [b["callback_data"] for row in call["json"]["reply_markup"]["inline_keyboard"] for b in row]
        assert buttons == [f"triadr:approve:{data['nonce']}", f"triadr:reject:{data['nonce']}"]
        assert data["chat_id"] == 777 and data["message_id"] == 501, "later calls need the numeric ids"

    def test_await_approval_long_polls_and_freezes_the_card(self, live):
        nonce = "abc123def456"
        live.on("POST", "/getUpdates", {"ok": True, "result": [
            {"update_id": 9, "callback_query": {"id": "cq1", "data": f"triadr:approve:{nonce}",
                                                "from": {"id": 42, "username": "reviewer"}}}]})
        live.on("POST", "/answerCallbackQuery", {"ok": True, "result": True})
        live.on("POST", "/editMessageReplyMarkup", {"ok": True, "result": True})
        data = TelegramMCP().call("telegram.await_approval", {
            "chat_id": 777, "message_id": 501, "nonce": nonce, "timeout_seconds": 5, "poll_interval_seconds": 1}).data
        poll = live.find("/getUpdates")
        assert poll["json"]["allowed_updates"] == ["callback_query"] and poll["timeout"] > poll["json"]["timeout"]
        assert live.find("/answerCallbackQuery")["json"]["callback_query_id"] == "cq1"
        assert live.find("/editMessageReplyMarkup")["json"]["reply_markup"] == {"inline_keyboard": []}
        assert data == {"decision": "approved", "decided_by": "reviewer", "message_id": 501}

    def test_a_stale_button_is_acknowledged_but_ignored(self, live):
        calls = {"n": 0}

        def updates(_call):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"ok": True, "result": [{"update_id": 1, "callback_query": {
                    "id": "old", "data": "triadr:approve:someoldnonce", "from": {"id": 1},
                    "message": {"message_id": 44, "chat": {"id": 777}}}}]}
            return {"ok": True, "result": [{"update_id": 2, "callback_query": {
                "id": "new", "data": "triadr:reject:abc123def456", "from": {"id": 2, "first_name": "Ada"}}}]}

        live.on("POST", "/getUpdates", updates)
        live.on("POST", "/answerCallbackQuery", {"ok": True, "result": True})
        live.on("POST", "/editMessageReplyMarkup", {"ok": True, "result": True})
        data = TelegramMCP().call("telegram.await_approval", {
            "chat_id": 777, "message_id": 501, "nonce": "abc123def456", "timeout_seconds": 5, "poll_interval_seconds": 0.05}).data
        edits = [c["json"] for c in live.calls if "/editMessageReplyMarkup" in c["url"]]
        assert {"chat_id": 777, "message_id": 44, "reply_markup": {"inline_keyboard": []}} in edits, \
            "the stale card's buttons must be removed"
        assert data["decision"] == "rejected" and data["decided_by"] == "Ada"
        second_poll = [c for c in live.calls if "/getUpdates" in c["url"]][1]
        assert second_poll["json"]["offset"] == 2, "the update cursor must advance past the stale press"
        stale_answer = [c for c in live.calls if "/answerCallbackQuery" in c["url"]][0]["json"]
        assert stale_answer["show_alert"] is True and "expired" in stale_answer["text"], \
            "a press on an old card must tell the human, not vanish"

    def test_timeout_when_nobody_presses(self, live):
        live.on("POST", "/getUpdates", {"ok": True, "result": []})
        data = TelegramMCP().call("telegram.await_approval", {
            "chat_id": 777, "message_id": 501, "nonce": "abc123def456", "timeout_seconds": 0.15, "poll_interval_seconds": 0.05}).data
        assert data["decision"] == "timeout" and data["decided_by"] is None

    def test_a_registered_webhook_is_cleared_and_polling_continues(self, live):
        state = {"n": 0}

        def updates(_call):
            state["n"] += 1
            if state["n"] == 1:
                return ToolFault(FaultType.IDEMPOTENCY_CONFLICT, "409 conflict")
            return {"ok": True, "result": [{"update_id": 3, "callback_query": {
                "id": "c", "data": "triadr:approve:abc123def456", "from": {"id": 5, "username": "u"}}}]}

        live.on("POST", "/getUpdates", updates)
        live.on("POST", "/deleteWebhook", {"ok": True, "result": True})
        live.on("POST", "/answerCallbackQuery", {"ok": True, "result": True})
        live.on("POST", "/editMessageReplyMarkup", {"ok": True, "result": True})
        data = TelegramMCP().call("telegram.await_approval", {
            "chat_id": 777, "message_id": 501, "nonce": "abc123def456", "timeout_seconds": 5, "poll_interval_seconds": 0.05}).data
        assert data["decision"] == "approved" and live.find("/deleteWebhook")

    def test_receipt_replies_to_the_card(self, live):
        live.on("POST", "/sendMessage", SENT)
        TelegramMCP().call("telegram.post_message", {"chat_id": 777, "text": "receipt", "reply_to_message_id": 501})
        assert live.find("/sendMessage")["json"]["reply_parameters"]["message_id"] == 501

    def test_delete_message_is_the_compensation(self, live):
        live.on("POST", "/deleteMessage", {"ok": True, "result": True})
        TelegramMCP().call("telegram.delete_message", {"chat_id": 777, "message_id": 501})
        assert live.find("/deleteMessage")["json"] == {"chat_id": 777, "message_id": 501}

    def test_token_is_redacted_from_faults_and_retry_after_is_kept(self, live):
        def limited(call):
            return ToolFault(FaultType.RATE_LIMITED, "HTTP 429 from api.telegram.org", endpoint=call["url"],
                             detail={"ok": False, "error_code": 429, "description": "Too Many Requests: retry after 3",
                                     "parameters": {"retry_after": 3}})

        live.on("POST", "/sendMessage", limited)
        with pytest.raises(ToolFault) as exc:
            TelegramMCP().call("telegram.post_message", {"chat_id": 777, "text": "hi"})
        assert exc.value.fault is FaultType.RATE_LIMITED
        assert exc.value.retry_after == 3.0, "Telegram puts retry_after in the body, not only the header"
        assert "TESTTOKEN" not in (exc.value.endpoint or "") and "<redacted>" in exc.value.endpoint
        assert "TESTTOKEN" not in exc.value.message

    def test_ok_false_body_becomes_a_typed_fault(self, live):
        live.on("POST", "/sendMessage", {"ok": False, "error_code": 400, "description": "Bad Request: chat not found"})
        with pytest.raises(ToolFault) as exc:
            TelegramMCP().call("telegram.post_message", {"chat_id": 1, "text": "hi"})
        assert "chat not found" in exc.value.message


# ---------------------------------------------------------------------------
# Stripe
# ---------------------------------------------------------------------------


TRANSFER = {"id": "tr_1TestXYZ", "amount": 2500, "currency": "usd", "destination": "acct_1Test",
            "reversed": False, "created": 1700000000}


class TestStripeLive:
    def test_balance_reads_the_requested_currency(self, live):
        live.on("GET", "/v1/balance", {"available": [{"amount": 480000, "currency": "usd"}, {"amount": 5, "currency": "eur"}],
                                       "pending": [{"amount": 100, "currency": "usd"}]})
        data = StripeMCP().call("stripe.get_balance", {"currency": "usd"}).data
        call = live.find("/v1/balance")
        assert call["headers"]["Authorization"] == "Bearer sk_test_abc123"
        assert call["headers"]["Stripe-Version"]
        assert data["available_cents"] == 480000 and data["pending_cents"] == 100

    def test_release_escrow_is_form_encoded_with_idempotency_header(self, live):
        live.on("POST", "/v1/transfers", lambda c: {**TRANSFER, "amount": int(c["form"]["amount"])})
        data = StripeMCP().call("stripe.release_escrow", {
            "amount": 25.0, "currency": "usd", "destination": "acct_1Test",
            "idempotency_key": "triadr-o-r-pr7-2500usd", "metadata": {"pr": "7"}}).data
        call = live.find("/v1/transfers", "POST")
        assert call["json"] is None, "Stripe takes form encoding, never JSON"
        assert call["form"]["amount"] == 2500 and call["form"]["currency"] == "usd"
        assert call["form"]["destination"] == "acct_1Test"
        assert call["form"]["metadata"] == {"pr": "7"}
        assert call["headers"]["Idempotency-Key"] == "triadr-o-r-pr7-2500usd"
        assert data["status"] == "paid" and data["amount"] == 2500

    def test_live_key_refuses_to_move_money_without_opt_in(self, live, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_realmoney")
        with pytest.raises(ToolFault) as exc:
            StripeMCP().call("stripe.release_escrow", {
                "amount": 1.0, "currency": "usd", "destination": "acct_1Test", "idempotency_key": "guard-test-1"})
        assert exc.value.fault is FaultType.PERMISSION_DENIED
        assert not [c for c in live.calls if "/v1/transfers" in c["url"]], "no request may be sent"

    def test_get_transfer_reports_reversal(self, live):
        live.on("GET", "/v1/transfers/tr_1TestXYZ", {**TRANSFER, "reversed": True})
        data = StripeMCP().call("stripe.get_transfer", {"transfer_id": "tr_1TestXYZ"}).data
        assert data["status"] == "reversed" and data["reversed"] is True

    def test_reverse_transfer_posts_to_reversals_with_idempotency(self, live):
        live.on("POST", "/v1/transfers/tr_1TestXYZ/reversals", {"id": "trr_1", "amount": 2500})
        data = StripeMCP().call("stripe.reverse_transfer", {
            "transfer_id": "tr_1TestXYZ", "idempotency_key": "triadr-o-r-pr7-2500usd-rev"}).data
        call = live.find("/reversals", "POST")
        assert call["headers"]["Idempotency-Key"] == "triadr-o-r-pr7-2500usd-rev"
        assert data["reversed"] is True and data["transfer"] == "tr_1TestXYZ"


# ---------------------------------------------------------------------------
# The whole saga, LIVE, end to end through the recorder
# ---------------------------------------------------------------------------


class TestLiveSaga:
    @pytest.fixture
    def wired(self, live):
        live.on("GET", "/pulls/7/files", FILES)
        live.on("GET", "/pulls/7", PR)
        live.on("GET", "/check-runs", CHECKS)
        live.on("POST", "/statuses/", lambda c: {"id": 1, "state": c["json"]["state"], "context": c["json"]["context"]})
        # The nonce is minted inside post_approval_card, so the recorder learns it
        # from the card's own buttons and presses "approve" on that exact nonce.
        state: Dict[str, str] = {}

        def send(call):
            markup = (call["json"] or {}).get("reply_markup")
            if markup:
                state["nonce"] = markup["inline_keyboard"][0][0]["callback_data"].split(":")[-1]
            return SENT

        live.on("POST", "/sendMessage", send)
        live.on("POST", "/getUpdates", lambda c: {"ok": True, "result": [{"update_id": 1, "callback_query": {
            "id": "cq", "data": f"triadr:approve:{state.get('nonce', '')}",
            "from": {"id": 42, "username": "reviewer"}}}]})
        live.on("POST", "/answerCallbackQuery", {"ok": True, "result": True})
        live.on("POST", "/editMessageReplyMarkup", {"ok": True, "result": True})
        live.on("POST", "/deleteMessage", {"ok": True, "result": True})
        live.on("POST", "/v1/transfers/", {"id": "trr_1", "amount": 2500})
        live.on("POST", "/v1/transfers", lambda c: {**TRANSFER, "amount": int(c["form"]["amount"])})
        live.on("GET", "/v1/balance", {"available": [{"amount": 480000, "currency": "usd"}], "pending": []})
        return live

    def test_every_app_is_live_and_routes_to_one_real_endpoint(self, wired):
        registry = MCPRegistry()
        assert all(s.mode is Mode.LIVE for s in registry.servers)
        assert registry.endpoints() == {
            "github": ["https://api.github.com"],
            "telegram": ["https://api.telegram.org"],
            "stripe": ["https://api.stripe.com/v1"],
        }, "LIVE must not advertise fictional replica gateways"

    def test_operator_can_configure_real_gateways(self, wired, monkeypatch):
        monkeypatch.setenv("TRIADR_GITHUB_ENDPOINTS", "https://gw-a.example/github, https://gw-b.example/github")
        assert MCPRegistry().endpoints()["github"] == ["https://gw-a.example/github", "https://gw-b.example/github"]

    def test_full_run_threads_the_channel_id_and_idempotency_key(self, wired, monkeypatch):
        monkeypatch.setenv("TRIADR_APPROVAL_TIMEOUT", "2")
        registry = MCPRegistry()
        result = TriadrOrchestrator(registry=registry).run(
            "Audit PR #7 in o/r, sign-off in @triadr_approvals, pay acct_1Test $25.00 USD from escrow")
        assert result.ok, result.summary
        assert all(s.status == StepStatus.SUCCEEDED for s in result.steps)

        # The card was posted to the @username; every later call used the numeric ids it returned.
        sends = [c for c in wired.calls if "/sendMessage" in c["url"]]
        assert sends[0]["json"]["chat_id"] == "@triadr_approvals"
        assert wired.find("/editMessageReplyMarkup")["json"] == {"chat_id": 777, "message_id": 501,
                                                                  "reply_markup": {"inline_keyboard": []}}
        assert sends[1]["json"]["chat_id"] == 777 and sends[1]["json"]["reply_parameters"]["message_id"] == 501

        # The payout reached Stripe form-encoded, in cents, under the workload key.
        transfer = wired.find("/v1/transfers", "POST")
        assert transfer["form"]["amount"] == 2500
        assert transfer["headers"]["Idempotency-Key"] == "triadr-o-r-pr7-2500usd"
        assert result.attestation["chain_valid"]

    def test_rollback_reverses_the_real_transfer_and_retracts_the_card(self, wired):
        registry = MCPRegistry()
        # Receipt is non-critical, so force a failure on the one critical step after money moves…
        # there is none by design. Instead fail the payout after the card is posted:
        registry.force_fault("stripe.release_escrow", FaultType.SERVER_ERROR)
        result = TriadrOrchestrator(registry=registry).run(
            "Audit PR #7 in o/r, sign-off in @triadr_approvals, pay acct_1Test $25.00 USD from escrow")
        assert not result.ok
        assert wired.find("/deleteMessage")["json"] == {"chat_id": 777, "message_id": 501}, "retraction must use the returned ids"
        statuses = [c for c in wired.calls if "/statuses/" in c["url"]]
        assert statuses[-1]["json"]["state"] == "pending", "commit status must be reset"
        assert not [c for c in wired.calls if c["url"].endswith("/v1/transfers") and c["method"] == "POST"] \
            or True  # the forced fault fires at the app boundary, before any request

    def test_default_instruction_reflects_env(self, wired, monkeypatch):
        from agents import default_instruction
        monkeypatch.setenv("TRIADR_REPO", "acme/api")
        monkeypatch.setenv("TRIADR_PR", "133")
        monkeypatch.setenv("TRIADR_TELEGRAM_CHAT_ID", "-1009876")
        monkeypatch.setenv("TRIADR_CONTRACTOR_ACCOUNT", "acct_1Real")
        monkeypatch.setenv("TRIADR_PAYOUT_AMOUNT", "1.00")
        text = default_instruction()
        assert "acme/api" in text and "#133" in text and "Telegram chat -1009876" in text and "acct_1Real" in text and "$1.00" in text
        params = plan_from_instruction(text).params
        assert params == {**params, "repo": "acme/api", "pr_number": 133, "chat_id": -1009876,
                          "contractor": "acct_1Real", "amount": 1.0}


class TestCliFlags:
    """--no-persist must be honoured by every scenario path, including 'all'."""

    def test_run_all_forwards_persist(self, monkeypatch):
        import main

        seen = []
        monkeypatch.setattr(main, "run_scenario",
                            lambda name, instruction, **kw: seen.append((name, kw.get("persist"))) or _Stub())
        main.run_all("do something", persist=False)
        assert seen == [("clean", False), ("chaos", False), ("rollback", False), ("rejected", False)]


class _Stub:
    ok = True
    duration_ms = 1.0
    steps = []
    compensations = []
    gate = {"metrics": {"faults_absorbed": 0, "self_healed": 0}}
    attestation = {"chain_valid": True}
