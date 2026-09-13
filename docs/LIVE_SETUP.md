# Running Triadr against the real APIs

Triadr runs fully offline on deterministic simulators, and every app switches
itself to **LIVE** the moment its credential is present. This page is the
shortest path from "simulated" to "every call is real", with the minimum
scopes each app needs.

Every app reports its mode in the CLI, the dashboard, the API and the audit log,
so you always know which one you are looking at.

---

## 0. How you know it works

```bash
python3 scripts/live_check.py                 # read-only - safe to run any time
python3 scripts/live_check.py --write         # + one write and its undo per app
python3 scripts/live_check.py --approve       # + a real approval card you react to
python3 scripts/live_check.py --stripe-setup  # fund the test balance, create a test payee
python3 scripts/live_check.py --payout        # + $1.00 transfer, replayed, then reversed
python3 scripts/live_check.py --run clean     # the full 6-step saga, LIVE
python3 scripts/live_check.py --run rollback  # Stripe forced down -> real rollback
```

Each check prints `PASS` / `FAIL` / `SKIP` with the exact fix for the common
failures. Run the read-only form first; add flags as each app comes online.

The LIVE code paths are also covered by `tests/test_live_paths.py`, which
verifies the request shape of every tool - method, URL, JSON-vs-form encoding,
auth and idempotency headers - against a recorder, with no network. If that
suite is green, the only things left to go wrong are credentials and scopes,
which is what `live_check.py` is for.

---

## 1. GitHub - App #1, code audit

**Token.** GitHub → Settings → Developer settings → Fine-grained tokens.
Repository access: the repo you'll audit. Permissions:

| Permission | Level | Used by |
|---|---|---|
| Pull requests | Read | `get_pull_request`, `list_changed_files`, `audit_pull_request` |
| Commit statuses | Read and write | `set_commit_status`, `clear_status`, and the CI fallback below |
| Checks | Read - *optional* | `get_check_runs` prefers the check-runs API; without this permission it falls back to the commit-status API, which "Commit statuses" already covers. Not every account is offered it. |
| Metadata | Read | (granted automatically) |

A classic token works too: `repo:status` + `public_repo` (or `repo` for a
private repository).

**Target.** Any open pull request you can see. Its diff is scored by the
deterministic audit - a PR touching `payments/`, `auth/` or a migration will
score high and require approval, which makes for a better demo.

```dotenv
GITHUB_TOKEN=github_pat_…
TRIADR_REPO=owner/repo
TRIADR_PR=42
```

---

## 2. Telegram - App #2, team approval

**Bot.** In Telegram, open **@BotFather** → `/newbot` → pick a display name and a
username ending in `bot`. BotFather replies with the token. That is the whole setup:
no scopes, no OAuth, no workspace admin.

**Chat.** A bot cannot start a conversation, so the reviewer has to open the bot once:
search for its username, press **Start**, send any message. For a team, add the bot to
a group and send one message there instead. Then let the live check find the id:

```bash
python3 scripts/live_check.py          # prints: Add to .env: TRIADR_TELEGRAM_CHAT_ID=…
```

**Approving.** The card carries real inline **Approve** / **Reject** buttons.
Presses reach Triadr through `getUpdates` long-polling, so it works from a laptop
with no public URL; the buttons are removed the moment a decision lands, so a second
press cannot flip it. Give the human time:

```dotenv
TELEGRAM_BOT_TOKEN=123456789:AA…
TRIADR_TELEGRAM_CHAT_ID=987654321          # or -100… for a group, or @public_channel
TRIADR_APPROVAL_TIMEOUT=120                # seconds; the simulator uses 30
```

If a webhook was ever registered for this bot, polling returns 409 - Triadr clears it
automatically and carries on.

---

## 3. Stripe - App #3, escrow payout

**Key.** Dashboard → Developers → API keys, **test mode**, the secret key
`sk_test_…`. Triadr refuses to move money on an `sk_live_` key unless
`TRIADR_ALLOW_LIVE_MONEY=1` is also set. Do not set it for the hackathon.

**Connect.** The payout is a *Transfer* to a connected account - the real
shape of a contractor payout. Transfers need Connect enabled once per platform:
Dashboard → Connect → *Get started* (choose the platform option; no further
setup is required in test mode).

**Funding and a payee.** A fresh test account has no balance and no connected
accounts. One command fixes both:

```bash
python3 scripts/live_check.py --stripe-setup
```

It charges `tok_bypassPending` - Stripe's test token whose funds are available
immediately - and creates a recipient account through **Accounts v2**
(`POST /v2/core/accounts`; new Connect platforms reject the v1 endpoint), with
the `stripe_transfers` capability requested. It prints the `acct_…` id and an
onboarding link. Open the link and use the test-mode **"Skip this account form"**
option - until then the capability is `restricted` and every transfer fails with
`insufficient_capabilities_for_transfer`. Re-running `--stripe-setup` with the
account already in `.env` re-checks the capability and re-prints the link. Then:

```dotenv
STRIPE_SECRET_KEY=sk_test_…
TRIADR_CONTRACTOR_ACCOUNT=acct_…
TRIADR_PAYOUT_AMOUNT=25.00         # major units
TRIADR_CURRENCY=usd
```

Every transfer carries an idempotency key derived from the workload, and
`--payout` proves it: the same key is sent twice and Stripe returns the same
transfer id both times.

---

## 4. Putting it together

```bash
cp .env.example .env               # then fill in the values above
python3 scripts/live_check.py --write --approve --payout
python3 scripts/live_check.py --run clean
python3 scripts/live_check.py --run rollback
```

Start the app as usual. The dashboard's app cards turn from `SIMULATED` to
`LIVE`, and the default instruction in the run box is built from your
`TRIADR_*` values, so it names your real repo, channel and payee.

```bash
.venv/bin/uvicorn server:app --port 8000
npm run dev
```

---

## 5. What is real and what is not, in LIVE mode

| | |
|---|---|
| Every tool call | Real vendor API request, real response, real side effect |
| Retry, backoff, circuit breakers, idempotency, rollback | Real - these operate on the real calls |
| Chaos faults | **Injected client-side**, before the request is sent. The vendor never sees them; the recovery that follows is a real request. This is standard fault injection, and it is labelled `[injected]` in every event and audit entry. |
| The `rollback` scenario | A forced fault at the app boundary, so the retraction of the Telegram card and the reset of the commit status are real API calls |
| Endpoint rerouting | LIVE routes to the **one** real API. The primary/replica gateways shown in simulated mode are not advertised in LIVE unless you configure real ones with `TRIADR_GITHUB_ENDPOINTS=…` (comma-separated) |
| Approve / Reject buttons | Real - delivered by `getUpdates` long-polling, no callback URL |

The campaign figures in the README were produced against the simulators, and
say so. To produce a LIVE campaign, run `--run clean` as many times as you
like; each run writes its own hash-chained log to `.triadr/`.
