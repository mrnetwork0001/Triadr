"""
Triadr - live readiness check.

Proves each connected app against its REAL API using the credentials in .env,
one tool at a time, and reports PASS / FAIL / SKIP per check. This is how you
know the demo will not secretly be running on the simulators.

    python3 scripts/live_check.py                 # read-only checks, safe to run any time
    python3 scripts/live_check.py --write         # + a write and its undo on each app
    python3 scripts/live_check.py --approve       # + post a real approval card; press a button
    python3 scripts/live_check.py --stripe-setup  # fund the test balance, create a test payee
    python3 scripts/live_check.py --payout        # + a $1.00 transfer, then reverse it
    python3 scripts/live_check.py --run clean     # the whole 6-step saga, LIVE
    python3 scripts/live_check.py --run rollback  # same, with Stripe forced down -> real rollback

Nothing here ever touches a live-mode Stripe key: an sk_live_ key fails every
write check by design (see StripeMCP._guard_live_money).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from env import load_env  # noqa: E402

load_env()

from agents import TriadrOrchestrator, default_instruction, defaults  # noqa: E402
from mcp_servers import MCPRegistry, Mode  # noqa: E402
from risk_gate import FaultType, ToolFault  # noqa: E402

# /v2/core/* endpoints refuse requests without an explicit version, and at the
# time of writing Accounts v2 is only reachable through a .preview version.
STRIPE_V2_VERSION = "2025-09-30.preview"

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
GREEN, YELLOW, RED, CYAN = "\033[32m", "\033[33m", "\033[31m", "\033[36m"

Result = Tuple[str, str]  # (status, message) where status in PASS / FAIL / SKIP


class Report:
    def __init__(self) -> None:
        self.rows: List[Tuple[str, str, str, str]] = []  # app, check, status, message

    def run(self, app: str, name: str, fn: Callable[[], str], *, skip: Optional[str] = None) -> Optional[str]:
        """Execute one check. Returns the message on PASS so later checks can chain."""
        if skip:
            self._row(app, name, "SKIP", skip)
            return None
        try:
            message = fn()
            self._row(app, name, "PASS", message)
            return message
        except ToolFault as fault:
            hint = _hint(app, fault)
            self._row(app, name, "FAIL", f"{fault.fault.value}: {fault.message}{hint}")
        except Exception as exc:  # noqa: BLE001 - a check must never take the runner down
            self._row(app, name, "FAIL", f"{type(exc).__name__}: {exc}")
        return None

    def _row(self, app: str, name: str, status: str, message: str) -> None:
        self.rows.append((app, name, status, message))
        colour = {"PASS": GREEN, "FAIL": RED, "SKIP": DIM}[status]
        print(f"  {colour}{status:<4}{RESET} {app:<7} {name:<28} {DIM}{message[:110]}{RESET}")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.rows if r[2] == "FAIL")

    @property
    def passed(self) -> int:
        return sum(1 for r in self.rows if r[2] == "PASS")


def _hint(app: str, fault: ToolFault) -> str:
    """Turn the most common live failures into the exact fix."""
    text = (fault.message + " " + str(fault.detail)).lower()
    hints = {
        "github": [
            ("bad credentials", "GITHUB_TOKEN is invalid or expired"),
            ("not found", "check TRIADR_REPO / TRIADR_PR, and that the token can see that repository"),
            ("resource not accessible", "the token needs Pull requests: read, Checks: read, Commit statuses: read & write"),
        ],
        "telegram": [
            ("unauthorized", "TELEGRAM_BOT_TOKEN is invalid - copy it again from @BotFather"),
            ("chat not found", "TRIADR_TELEGRAM_CHAT_ID is wrong, or that chat has never messaged the bot"),
            ("bot was blocked", "the user blocked the bot - unblock it in Telegram and re-run"),
            ("not enough rights", "in a group the bot needs permission to send and delete messages"),
            ("message can't be deleted", "bots can only delete messages younger than 48h that they sent"),
            ("conflict", "a webhook is registered for this bot - the check clears it; just re-run"),
        ],
        "stripe": [
            ("invalid api key", "STRIPE_SECRET_KEY is invalid - use the test-mode key, sk_test_…"),
            ("balance_insufficient", "run --stripe-setup to fund the test balance"),
            ("insufficient", "run --stripe-setup to fund the test balance"),
            ("no such destination", "TRIADR_CONTRACTOR_ACCOUNT is not a connected account of this platform - run --stripe-setup"),
            ("capabilit", "the connected account has not activated transfers - open the onboarding link from --stripe-setup"),
            ("accounts v1", "this Stripe account requires Accounts v2 - update Triadr; --stripe-setup now uses /v2/core/accounts"),
            ("insufficient_capabilities_for_transfer", "the payee has not finished onboarding - run --stripe-setup to (re)open the onboarding link and use the test-mode skip"),
            ("connect", "enable Connect in the Stripe dashboard (Connect → Get started), then re-run --stripe-setup"),
        ],
    }
    for needle, fix in hints.get(app, []):
        if needle in text:
            return f"  →  {fix}"
    return ""


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_github(reg: MCPRegistry, rep: Report, args) -> None:
    d = defaults()
    repo, pr = d["repo"], d["pr_number"]
    gh = reg.github

    # Token first: /user works for any token, so a bad or expired one is
    # reported as such rather than as a misleading 404 on the repository.
    def whoami() -> str:
        me = gh.http("GET", f"{gh.api_base}/user", headers=gh._headers())
        return f"token belongs to @{me.get('login')}"

    rep.run("github", "token", whoami)
    if not os.environ.get("TRIADR_REPO"):
        rep.run("github", "repo access", lambda: "", skip="set TRIADR_REPO in .env")
        return

    def repo_access() -> str:
        meta = gh.http("GET", f"{gh.api_base}/repos/{repo}", headers=gh._headers())
        perms = meta.get("permissions") or {}
        return (f"{meta.get('full_name')} ({meta.get('visibility')}, default {meta.get('default_branch')}) - "
                f"push={'yes' if perms.get('push') else 'no'}")

    if rep.run("github", "repo access", repo_access) is None:
        return
    if not os.environ.get("TRIADR_PR"):
        rep.run("github", "get_pull_request", lambda: "", skip="set TRIADR_PR in .env to an open PR number")
        return

    meta = rep.run("github", "get_pull_request", lambda: _summary(reg.call("github.get_pull_request", {"repo": repo, "pr_number": pr})))
    rep.run("github", "list_changed_files", lambda: _summary(reg.call("github.list_changed_files", {"repo": repo, "pr_number": pr})))
    sha = None
    if meta:
        sha = reg.call("github.get_pull_request", {"repo": repo, "pr_number": pr}).data["head_sha"]
        rep.run("github", "get_check_runs", lambda: _summary(reg.call("github.get_check_runs", {"repo": repo, "ref": sha})))
    rep.run("github", "audit_pull_request", lambda: _summary(reg.call("github.audit_pull_request", {"repo": repo, "pr_number": pr})))

    if not args.write:
        rep.run("github", "set_commit_status", lambda: "", skip="pass --write to exercise the write path")
        return
    if not sha:
        rep.run("github", "set_commit_status", lambda: "", skip="no head sha (get_pull_request failed)")
        return
    rep.run("github", "set_commit_status", lambda: _summary(reg.call("github.set_commit_status", {
        "repo": repo, "sha": sha, "state": "success", "context": "triadr/live-check",
        "description": "Triadr live check passed"})))


def check_telegram(reg: MCPRegistry, rep: Report, args) -> None:
    tg = reg.telegram

    def get_me() -> str:
        me = tg.get_me()
        return f"bot @{me.get('username')} ({me.get('first_name')})"

    rep.run("telegram", "getMe", get_me)

    chat_id = os.environ.get("TRIADR_TELEGRAM_CHAT_ID")
    if not chat_id:
        def discover() -> str:
            found = tg.discover_chat()
            if not found:
                raise ToolFault(FaultType.NOT_FOUND,
                                "no chat has messaged the bot yet - open it in Telegram, press Start, "
                                "send any message, then re-run")
            os.environ["TRIADR_TELEGRAM_CHAT_ID"] = str(found["id"])
            print(f"\n  {BOLD}Add to .env:{RESET}  TRIADR_TELEGRAM_CHAT_ID={found['id']}   "
                  f"{DIM}({found['type']}: {found['title']}){RESET}\n")
            return f"discovered chat {found['id']} ({found['type']}: {found['title']}) - using it for this run"

        if rep.run("telegram", "discover chat", discover) is None:
            return
        chat_id = os.environ["TRIADR_TELEGRAM_CHAT_ID"]
    target = defaults()["chat_id"]

    if args.write or args.approve:
        posted: Dict[str, Any] = {}

        def post() -> str:
            posted.update(reg.call("telegram.post_message", {
                "chat_id": target, "text": "Triadr live check - this message deletes itself in a moment."}).data)
            return f"message {posted['message_id']} in chat {posted['chat_id']}"

        rep.run("telegram", "post_message", post)
        if posted:
            time.sleep(1.2)
            rep.run("telegram", "delete_message", lambda: _summary(reg.call("telegram.delete_message", {
                "chat_id": posted["chat_id"], "message_id": posted["message_id"]})))
    else:
        rep.run("telegram", "post_message", lambda: "", skip="pass --write to post and delete a message")

    if not args.approve:
        rep.run("telegram", "await_approval", lambda: "", skip="pass --approve to post a real card and press a button")
        return

    timeout = float(os.environ.get("TRIADR_APPROVAL_TIMEOUT", "120"))
    card: Dict[str, Any] = {}

    def post_card() -> str:
        card.update(reg.call("telegram.post_approval_card", {
            "chat_id": target, "amount": 1.00, "currency": defaults()["currency"],
            "contractor": defaults()["contractor"],
            "audit": {"pr_number": defaults()["pr_number"], "title": "live check", "author": "triadr",
                      "risk_score": 42, "risk_band": "medium", "url": "",
                      "reasons": ["this is a live readiness check - press Approve or Reject"]}}).data)
        return f"card posted - message {card['message_id']} in chat {card['chat_id']}"

    rep.run("telegram", "post_approval_card", post_card)
    if card:
        print(f"\n  {BOLD}{YELLOW}→ Press Approve (or Reject) on the card in Telegram within {timeout:.0f}s{RESET}\n")
        rep.run("telegram", "await_approval", lambda: _summary(reg.call("telegram.await_approval", {
            "chat_id": card["chat_id"], "message_id": card["message_id"], "nonce": card["nonce"],
            "timeout_seconds": min(timeout, 900), "poll_interval_seconds": 2})))
        rep.run("telegram", "delete_message (card)", lambda: _summary(reg.call("telegram.delete_message", {
            "chat_id": card["chat_id"], "message_id": card["message_id"]})))


def check_stripe(reg: MCPRegistry, rep: Report, args) -> None:
    stripe = reg.stripe
    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if key.startswith("sk_live_"):
        print(f"\n  {RED}{BOLD}STRIPE_SECRET_KEY is a LIVE key. Every money-moving check will be refused. "
              f"Use sk_test_… for the hackathon.{RESET}\n")

    rep.run("stripe", "get_balance", lambda: _summary(reg.call("stripe.get_balance", {"currency": defaults()["currency"]})))

    if args.stripe_setup:
        stripe_setup(reg, rep)

    account = os.environ.get("TRIADR_CONTRACTOR_ACCOUNT") or defaults()["contractor"]
    if not args.payout:
        rep.run("stripe", "release_escrow", lambda: "", skip="pass --payout to move $1.00 and reverse it")
        return
    if account.startswith("acct_1Triadr"):
        rep.run("stripe", "release_escrow", lambda: "", skip="TRIADR_CONTRACTOR_ACCOUNT is the placeholder - run --stripe-setup")
        return

    stamp = int(time.time())
    transfer: Dict[str, Any] = {}

    def release() -> str:
        transfer.update(reg.call("stripe.release_escrow", {
            "amount": 1.00, "currency": defaults()["currency"], "destination": account,
            "idempotency_key": f"triadr-live-check-{stamp}", "description": "Triadr live check"}).data)
        return f"{transfer['id']} - {transfer['amount']} cents to {account}"

    rep.run("stripe", "release_escrow", release)
    if transfer:
        rep.run("stripe", "release_escrow (replay)", lambda: _assert(
            reg.call("stripe.release_escrow", {
                "amount": 1.00, "currency": defaults()["currency"], "destination": account,
                "idempotency_key": f"triadr-live-check-{stamp}", "description": "Triadr live check"}).data["id"] == transfer["id"],
            "same idempotency key returned the same transfer - no double payment"))
        rep.run("stripe", "get_transfer", lambda: _summary(reg.call("stripe.get_transfer", {"transfer_id": transfer["id"]})))
        rep.run("stripe", "reverse_transfer", lambda: _summary(reg.call("stripe.reverse_transfer", {
            "transfer_id": transfer["id"], "idempotency_key": f"triadr-live-check-{stamp}-rev",
            "reason": "live check cleanup"})))


def stripe_setup(reg: MCPRegistry, rep: Report) -> None:
    """Make a fresh test-mode account able to run the payout: funds + a payee."""
    stripe = reg.stripe
    base = stripe.api_base
    currency = defaults()["currency"]

    def fund() -> str:
        balance = reg.call("stripe.get_balance", {"currency": currency}).data
        if balance["available_cents"] >= 5_000:
            return f"already funded - {balance['available']:,.2f} {currency.upper()} available"
        # tok_bypassPending makes the funds available immediately in test mode.
        raw = stripe.http("POST", f"{base}/charges", headers=stripe._headers(f"triadr-topup-{int(time.time())}"),
                          form_body={"amount": 100_00, "currency": currency, "source": "tok_bypassPending",
                                     "description": "Triadr test balance"})
        return f"charged {raw['amount'] / 100:,.2f} {currency.upper()} via tok_bypassPending - funds available now"

    rep.run("stripe", "fund test balance", fund)

    # New Connect platforms must use Accounts v2: v1 POST /accounts is rejected
    # outright ("Stripe no longer recommends Accounts v1 for new Connect
    # integrations"). v2 takes JSON and needs an explicit preview API version.
    v2_headers = {"Authorization": f"Bearer {stripe.credential('STRIPE_SECRET_KEY')}",
                  "Stripe-Version": STRIPE_V2_VERSION}

    def onboarding_link(account: str) -> str:
        link = stripe.http("POST", "https://api.stripe.com/v2/core/account_links", headers=v2_headers, json_body={
            "account": account,
            "use_case": {"type": "account_onboarding",
                         "account_onboarding": {"configurations": ["recipient"],
                                                "refresh_url": "https://example.com/triadr/refresh",
                                                "return_url": "https://example.com/triadr/return"}},
        })
        return link["url"]

    account = os.environ.get("TRIADR_CONTRACTOR_ACCOUNT")
    if account:
        def check_payee() -> str:
            acct = stripe.http("GET", f"https://api.stripe.com/v2/core/accounts/{account}?include=configuration.recipient",
                               headers=v2_headers)
            cap = (((acct.get("configuration") or {}).get("recipient") or {}).get("capabilities") or {}) \
                .get("stripe_balance", {}).get("stripe_transfers", {})
            status = cap.get("status", "unknown")
            if status != "active":
                url = onboarding_link(account)
                print(f"\n  {BOLD}Payee {account} cannot receive transfers yet ({status}).{RESET}")
                print(f"  {BOLD}Open:{RESET} {url}")
                print(f"  {DIM}Test mode: use the 'Skip this account form' option at the top, then re-run --payout.{RESET}\n")
                raise ToolFault(FaultType.PERMISSION_DENIED, f"stripe_transfers capability is {status} - onboarding link printed above")
            return f"{account} - stripe_transfers capability active"

        rep.run("stripe", "payee ready", check_payee)
        return

    def create_payee() -> str:
        acct = stripe.http("POST", "https://api.stripe.com/v2/core/accounts",
                           headers={**v2_headers, "Idempotency-Key": f"triadr-payee-{int(time.time())}"},
                           json_body={
                               "display_name": "Triadr test contractor",
                               "contact_email": "triadr-contractor@example.com",
                               "identity": {"country": "us", "entity_type": "individual"},
                               "dashboard": "express",
                               "defaults": {"responsibilities": {"fees_collector": "application",
                                                                 "losses_collector": "application"}},
                               "configuration": {"recipient": {"capabilities": {"stripe_balance": {
                                   "stripe_transfers": {"requested": True}}}}},
                               "include": ["configuration.recipient", "requirements"],
                           })
        url = onboarding_link(acct["id"])
        print(f"\n  {BOLD}Add to .env:{RESET}  TRIADR_CONTRACTOR_ACCOUNT={acct['id']}")
        print(f"  {BOLD}Then open:{RESET}   {url}")
        print(f"  {DIM}Test mode: use the 'Skip this account form' option at the top, then re-run with --payout.{RESET}\n")
        return f"created {acct['id']} via Accounts v2 (recipient, stripe_transfers requested)"

    rep.run("stripe", "create test payee", create_payee)


# ---------------------------------------------------------------------------
# Full saga
# ---------------------------------------------------------------------------


def run_saga(reg: MCPRegistry, scenario: str) -> int:
    instruction = default_instruction()
    print(f"\n{BOLD}  Full LIVE saga - {scenario}{RESET}")
    print(f"  {DIM}{instruction}{RESET}")
    if scenario == "rollback":
        reg.force_fault("stripe.release_escrow", FaultType.SERVER_ERROR)
        print(f"  {DIM}stripe.release_escrow is forced down - expect the card to be retracted and the status reset{RESET}")
    if reg.telegram.mode is Mode.LIVE:
        timeout = os.environ.get("TRIADR_APPROVAL_TIMEOUT", "30")
        print(f"\n  {BOLD}{YELLOW}→ When the approval card appears in Telegram, press Approve within {timeout}s{RESET}\n")

    orchestrator = TriadrOrchestrator(registry=reg, run_id=f"live_{scenario}_{int(time.time())}")
    result = orchestrator.run(instruction)

    for step in result.steps:
        colour = {"succeeded": GREEN, "healed": YELLOW, "failed": RED, "compensated": CYAN}.get(step.status, DIM)
        print(f"  {colour}{step.status:<12}{RESET} {step.step.id:<14} {DIM}{step.step.tool:<28}{RESET} {step.duration_ms:>7.0f}ms")
    for comp in result.compensations:
        print(f"  {CYAN}{'undone':<12}{RESET} {comp['undid']:<14} {DIM}via {comp['tool']}{RESET}")
    paths = orchestrator.persist()
    print(f"\n  {BOLD}{result.summary}{RESET}")
    print(f"  {DIM}chain valid: {result.attestation['chain_valid']} · audit log {paths['log']}{RESET}\n")
    expected_ok = scenario == "clean"
    return 0 if result.ok == expected_ok else 1


# ---------------------------------------------------------------------------


def _summary(result) -> str:
    return result.summary or "ok"


def _assert(condition: bool, message: str) -> str:
    if not condition:
        raise AssertionError(message)
    return message


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="also exercise writes and their undo")
    parser.add_argument("--approve", action="store_true", help="post a real approval card and wait for a button press")
    parser.add_argument("--stripe-setup", action="store_true", help="fund the test balance and create a test payee")
    parser.add_argument("--payout", action="store_true", help="transfer $1.00 to the contractor account, then reverse it")
    parser.add_argument("--run", choices=["clean", "rollback"], help="execute the full saga LIVE")
    args = parser.parse_args()

    reg = MCPRegistry()
    print(f"\n{BOLD}  Triadr live readiness{RESET}")
    live = 0
    for app in reg.status()["apps"]:
        colour = GREEN if app["mode"] == "LIVE" else YELLOW
        note = "" if app["mode"] == "LIVE" else f" {DIM}- set {', '.join(app['credentials_missing'])}{RESET}"
        print(f"  {colour}●{RESET} {app['app']:<7} {app['mode']}{note}")
        live += app["mode"] == "LIVE"
    print()

    if live == 0:
        print(f"  {YELLOW}No app is LIVE. Copy .env.example to .env and add at least one credential.{RESET}\n")
        sys.exit(2)

    rep = Report()
    if reg.github.mode is Mode.LIVE:
        check_github(reg, rep, args)
    if reg.telegram.mode is Mode.LIVE:
        check_telegram(reg, rep, args)
    if reg.stripe.mode is Mode.LIVE:
        check_stripe(reg, rep, args)

    print(f"\n  {BOLD}{rep.passed} passed · {rep.failed} failed · "
          f"{sum(1 for r in rep.rows if r[2] == 'SKIP')} skipped{RESET}")
    simulated = [a["app"] for a in reg.status()["apps"] if a["mode"] != "LIVE"]
    if simulated:
        print(f"  {YELLOW}Still simulated: {', '.join(simulated)}{RESET}")
    print()

    code = 1 if rep.failed else 0
    if args.run and not rep.failed:
        code = run_saga(reg, args.run)
    elif args.run:
        print(f"  {RED}Not running the saga while checks are failing.{RESET}\n")
    sys.exit(code)


if __name__ == "__main__":
    main()
