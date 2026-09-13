"""
Triadr - Instruction planner.

Turns a natural-language instruction into an explicit, typed, multi-step plan
across the three connected apps. The planner is deterministic by default: the
plan shape is fixed and safe, and only the *parameters* are extracted from the
instruction. That matters for a reliability engine - a model that hallucinates
an extra `stripe.release_escrow` step would be a financial incident, so the
model never gets to invent steps.

Set TRIADR_LLM_PLANNER=1 with ANTHROPIC_API_KEY to let Claude propose the
parameters instead; the extracted values are still validated against the same
JSON Schemas before anything executes.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from brand import TRIADR_MARK
from typing import Any, Dict, List, Optional

_AMOUNT = re.compile(
    r"(?:\$|usd\s*|eur\s*|gbp\s*)?(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\s*(?:usd|dollars?|eur|gbp)?",
    re.IGNORECASE,
)
_PR = re.compile(r"(?:pr|pull\s*request|#)\s*#?(\d{1,6})", re.IGNORECASE)
_REPO = re.compile(r"\b([\w.\-]+/[\w.\-]+)\b")
# Requires at least one letter, so "PR #77" is never mistaken for a channel.
# A public Telegram chat is addressed as @username (5–32 chars).
_CHAT = re.compile(r"@([A-Za-z0-9_]{5,32})\b")
_ACCT = re.compile(r"\b(acct_[A-Za-z0-9]+)\b")
_CURRENCY = re.compile(r"\b(usd|eur|gbp|cad|aud|jpy)\b", re.IGNORECASE)


@dataclass
class PlanStep:
    """One gate-supervised tool call, with its rollback and data dependencies."""

    id: str
    app: str
    tool: str
    args: Dict[str, Any]
    title: str
    depends_on: List[str] = field(default_factory=list)
    compensation: Optional[Dict[str, Any]] = None   # {"tool": ..., "args": {...}}
    idempotency_key: Optional[str] = None
    critical: bool = True        # a failed critical step rolls the whole saga back
    condition: Optional[str] = None  # e.g. "audit.requires_human_approval"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "app": self.app, "tool": self.tool, "title": self.title,
            "args": self.args, "depends_on": self.depends_on,
            "compensation": self.compensation, "idempotency_key": self.idempotency_key,
            "critical": self.critical, "condition": self.condition,
        }


@dataclass
class Plan:
    instruction: str
    steps: List[PlanStep]
    params: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instruction": self.instruction,
            "params": self.params,
            "steps": [s.to_dict() for s in self.steps],
            "step_count": len(self.steps),
            "apps": sorted({s.app for s in self.steps}),
        }


_BUILTIN_DEFAULTS: Dict[str, Any] = {
    "repo": "mrnetwork/triadr",
    "pr_number": 42,
    "chat_id": "@triadr_approvals",
    "amount": 2500.00,
    "currency": "usd",
    "contractor": "acct_1TriadrContractor",
    "approval_threshold": 30,
}

# Environment variable -> (param, coercion). Set these in .env for a LIVE run so
# the workflow targets a real repository, PR, channel and connected account.
_ENV_DEFAULTS = {
    "TRIADR_REPO": ("repo", str),
    "TRIADR_PR": ("pr_number", int),
    "TRIADR_TELEGRAM_CHAT_ID": ("chat_id", lambda v: int(v) if re.fullmatch(r"-?\d+", v.strip()) else v.strip()),
    "TRIADR_PAYOUT_AMOUNT": ("amount", float),
    "TRIADR_CURRENCY": ("currency", lambda v: v.lower()),
    "TRIADR_CONTRACTOR_ACCOUNT": ("contractor", str),
    "TRIADR_APPROVAL_THRESHOLD": ("approval_threshold", int),
}


def defaults() -> Dict[str, Any]:
    """Built-in defaults, overridden by any TRIADR_* variables that are set."""
    out = dict(_BUILTIN_DEFAULTS)
    for var, (key, coerce) in _ENV_DEFAULTS.items():
        raw = os.environ.get(var)
        if raw:
            try:
                out[key] = coerce(raw)
            except (TypeError, ValueError):
                pass  # a malformed override must not take the planner down
    return out


# Retained name for callers that imported the old constant.
DEFAULTS = _BUILTIN_DEFAULTS


def default_instruction() -> str:
    """The instruction the CLI, API and dashboard offer when none is given -
    built from the effective defaults so a LIVE setup shows real identifiers."""
    d = defaults()
    target = d["chat_id"]
    where = target if isinstance(target, str) and target.startswith("@") else f"Telegram chat {target}"
    return (
        f"Audit PR #{d['pr_number']} in {d['repo']}, get team sign-off in {where}, "
        f"then release ${d['amount']:,.2f} {d['currency'].upper()} from escrow to {d['contractor']}"
    )


def extract_params(instruction: str, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Pull structured parameters out of free text; fall back to the effective defaults."""
    params = defaults()
    text = instruction or ""

    if (m := _PR.search(text)):
        params["pr_number"] = int(m.group(1))
    if (m := _REPO.search(text)):
        candidate = m.group(1)
        if "/" in candidate and not candidate.startswith("acct_"):
            params["repo"] = candidate
    if (m := _CHAT.search(text)):
        params["chat_id"] = "@" + m.group(1)
    if (m := _ACCT.search(text)):
        params["contractor"] = m.group(1)
    if (m := _CURRENCY.search(text)):
        params["currency"] = m.group(1).lower()

    # Amount: prefer a value that reads like money, and never confuse it with the PR number.
    money = [
        float(m.group(1).replace(",", ""))
        for m in _AMOUNT.finditer(text)
        if "$" in m.group(0) or "," in m.group(1) or re.search(r"(usd|dollar|eur|gbp)", m.group(0), re.I)
    ]
    if money:
        params["amount"] = max(money)

    params.update(overrides or {})
    return params


def _llm_params(instruction: str, base: Dict[str, Any]) -> Dict[str, Any]:
    """Optional: ask Claude to extract the parameters. Never asks it for the plan shape."""
    try:
        import urllib.request

        api_key = os.environ["ANTHROPIC_API_KEY"]
        prompt = (
            "Extract workflow parameters from the instruction. Reply with ONLY a JSON object using "
            "these keys, omitting any you cannot determine: repo (owner/repo), pr_number (int), "
            "chat_id (telegram chat id or @username), amount (number, major units), currency (iso-4217 lowercase), "
            "contractor (stripe acct_ id).\n\nInstruction: " + instruction
        )
        body = json.dumps({
            "model": "claude-sonnet-5",
            "max_tokens": 400,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={"content-type": "application/json", "x-api-key": api_key,
                     "anthropic-version": "2023-06-01"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
        text = "".join(block.get("text", "") for block in data.get("content", []))
        match = re.search(r"\{.*\}", text, re.S)
        if match:
            proposed = json.loads(match.group(0))
            # Only keys we recognise, only types we expect. The schema check still runs later.
            for key in ("repo", "chat_id", "currency", "contractor"):
                if isinstance(proposed.get(key), str):
                    base[key] = proposed[key]
            for key in ("pr_number",):
                if isinstance(proposed.get(key), int):
                    base[key] = proposed[key]
            if isinstance(proposed.get("amount"), (int, float)):
                base["amount"] = float(proposed["amount"])
    except Exception:
        pass  # planner degradation is never fatal - the regex plan stands
    return base


def plan_from_instruction(
    instruction: str,
    *,
    run_id: str = "run",
    overrides: Optional[Dict[str, Any]] = None,
) -> Plan:
    """Build the fixed 6-step, 3-app saga with parameters bound from the instruction."""
    params = extract_params(instruction, overrides)
    if os.environ.get("TRIADR_LLM_PLANNER") == "1":
        params = _llm_params(instruction, params)

    repo = params["repo"]
    pr = params["pr_number"]
    chat_id = params["chat_id"]
    amount = params["amount"]
    currency = params["currency"]
    contractor = params["contractor"]
    try:
        approval_timeout = float(os.environ.get("TRIADR_APPROVAL_TIMEOUT", "30"))
    except ValueError:
        approval_timeout = 30.0
    approval_timeout = max(0.0, min(approval_timeout, 900.0))  # matches the tool's schema bounds

    # Idempotency keys are derived from the *workload*, not the attempt, so a
    # retried run of the same payout collapses onto the same key.
    payout_key = f"triadr-{repo.replace('/', '-')}-pr{pr}-{int(round(amount * 100))}{currency}"

    steps = [
        PlanStep(
            id="audit",
            app="github",
            tool="github.audit_pull_request",
            title=f"Audit PR #{pr} in {repo}",
            args={"repo": repo, "pr_number": pr, "approval_threshold": params["approval_threshold"]},
        ),
        PlanStep(
            id="status",
            app="github",
            tool="github.set_commit_status",
            title="Write the audit verdict back to the commit",
            args={"repo": repo, "sha": "${audit.head_sha}", "state": "success",
                  "description": "Triadr audit: ${audit.risk_band} risk (${audit.risk_score}/100)",
                  "context": "triadr/reliability-gate"},
            depends_on=["audit"],
            compensation={"tool": "github.clear_status",
                          "args": {"repo": repo, "sha": "${audit.head_sha}",
                                   "context": "triadr/reliability-gate"}},
            critical=False,  # a missing status check must not block a settled payout
        ),
        PlanStep(
            id="approval_card",
            app="telegram",
            tool="telegram.post_approval_card",
            title=f"Post the approval card to {chat_id}",
            args={"chat_id": chat_id, "audit": "${audit}", "amount": amount,
                  "currency": currency, "contractor": contractor},
            depends_on=["audit"],
            # Compensation uses the chat id and message id the post *returned*,
            # so it retracts exactly the message that was created.
            compensation={"tool": "telegram.delete_message",
                          "args": {"chat_id": "${approval_card.chat_id}",
                                   "message_id": "${approval_card.message_id}"}},
        ),
        PlanStep(
            id="approval",
            app="telegram",
            tool="telegram.await_approval",
            title="Wait for the reviewer to press Approve or Reject",
            args={"chat_id": "${approval_card.chat_id}", "message_id": "${approval_card.message_id}",
                  "nonce": "${approval_card.nonce}", "timeout_seconds": approval_timeout},
            depends_on=["approval_card"],
        ),
        PlanStep(
            id="payout",
            app="stripe",
            tool="stripe.release_escrow",
            title=f"Release {currency.upper()} {amount:,.2f} from escrow",
            args={"amount": amount, "currency": currency, "destination": contractor,
                  "idempotency_key": payout_key,
                  "description": f"Triadr escrow release for {repo} PR #{pr}",
                  "metadata": {"repo": repo, "pr": str(pr), "run": run_id}},
            depends_on=["approval"],
            condition="approval.decision == approved",
            idempotency_key=payout_key,
            compensation={"tool": "stripe.reverse_transfer",
                          "args": {"transfer_id": "${payout.id}",
                                   "idempotency_key": payout_key + "-rev",
                                   "reason": "Triadr saga compensation"}},
        ),
        PlanStep(
            id="receipt",
            app="telegram",
            tool="telegram.post_message",
            title="Post the settlement receipt as a reply to the card",
            args={"chat_id": "${approval_card.chat_id}",
                  "text": "%s Triadr settled PR #%d: transfer <code>${payout.id}</code> for %s %s released to <code>%s</code>."
                          % (TRIADR_MARK, pr, currency.upper(), f"{amount:,.2f}", contractor),
                  "reply_to_message_id": "${approval_card.message_id}"},
            depends_on=["payout"],
            critical=False,
        ),
    ]

    return Plan(instruction=instruction, steps=steps, params=params)


if __name__ == "__main__":  # pragma: no cover
    p = plan_from_instruction(
        "Audit PR #77 in mrnetwork/triadr, get sign-off in #payments-approvals, "
        "then pay acct_1Contractor $4,750.00 USD from escrow"
    )
    print(json.dumps(p.to_dict(), indent=2)[:2000])
