<img width="2988" height="1716" alt="Triadr" src="https://github.com/user-attachments/assets/dfe3da29-83ed-4c0d-90de-d7710ce3aeb1" />

# Triadr - Self-Healing Multi-App Agent & Reliability Engine

<img width="2988" height="1716" alt="image" src="https://github.com/user-attachments/assets/dfe3da29-83ed-4c0d-90de-d7710ce3aeb1" />


> Built for the **Multi-App AI Agent Hackathon** (`multiappagenthackathon.com`)
> **Connected apps:** GitHub (code audit) · Telegram (team approval) · Stripe (escrow payout)
> **Stack:** Model Context Protocol · Python 3.11+ · FastAPI · Next.js 14 · Tailwind CSS
> **License:** Apache 2.0

Triadr takes one sentence - *"Audit PR #42, get team sign-off on Telegram, then release
$2,500 from escrow to the contractor"* - and carries it across three external apps as a
six-step workflow. Every side effect passes through a reliability gate that validates,
retries, reroutes, deduplicates and, when a step is genuinely unrecoverable, rolls the
whole workflow back. Every decision lands on a SHA-256 hash chain you can verify yourself.

**The guarantee:** a run ends fully applied or fully reverted. Never half-executed.

---

## Contents

1. [What you will see](#1-what-you-will-see)
2. [Prerequisites](#2-prerequisites)
3. [Try it in five minutes - no accounts needed](#3-try-it-in-five-minutes---no-accounts-needed)
4. [Guided walkthrough of the dashboard](#4-guided-walkthrough-of-the-dashboard)
5. [Try it live - real GitHub, Telegram and Stripe](#5-try-it-live---real-github-telegram-and-stripe)
6. [Command reference](#6-command-reference)
7. [Configuration reference](#7-configuration-reference)
8. [Troubleshooting](#8-troubleshooting)
9. [How it works](#9-how-it-works)
10. [Evidence](#10-evidence)
11. [Triadr as an MCP server](#11-triadr-as-an-mcp-server)
12. [Safety](#12-safety)
13. [Repository layout](#13-repository-layout)

---

## 1. What you will see

The workflow Triadr runs, and what can go wrong at each step:

| # | App | Step | If it fails |
|---|---|---|---|
| 1 | GitHub | Audit the pull request - diff surface, sensitive paths, tests, CI - into a 0-100 risk score | retried, rerouted; unrecoverable → run stops cleanly |
| 2 | GitHub | Write the verdict onto the commit as a status check | non-critical: the run continues |
| 3 | Telegram | Post an approval card with real Approve / Reject buttons | unrecoverable → run stops cleanly |
| 4 | Telegram | Wait for a human to press a button | timeout → payout skipped, nothing moved |
| 5 | Stripe | Release the escrow payout as a transfer, under an idempotency key | unrecoverable → **the card is retracted and the status reset** |
| 6 | Telegram | Post the settlement receipt as a reply to the card | non-critical: the run continues |

Four scenarios exercise the happy path and every failure path - see [§6](#6-command-reference).

Under a fault storm that fails ~75% of calls on first attempt, across 40 runs:

| | |
|---|---|
| Faults absorbed | **356** |
| Steps self-healed | **130** |
| Runs ending fully applied | **26** |
| Runs ending fully rolled back | **14** |
| Runs left half-executed | **0** |
| Duplicate payouts | **0** |
| Audit chains that verify | **40 / 40** |

Reproduce it yourself: `python3 scripts/campaign.py --runs 40`

---

## 2. Prerequisites

| Requirement | Notes |
|---|---|
| **Python 3.11+** | The engine (`risk_gate.py`, `agents/`, `mcp_servers/`) is stdlib-only. `python3 main.py` needs nothing installed. |
| **Node.js 18+** and npm | Only for the web app. |
| macOS or Linux | Windows works under WSL. |
| *Optional:* GitHub, Telegram and Stripe accounts | Only for [§5](#5-try-it-live---real-github-telegram-and-stripe). Everything else runs on deterministic simulators. |

---

## 3. Try it in five minutes - no accounts needed

Every app falls back to a simulator when its credential is absent, and says so in every
result, so the whole demo runs offline.

### 3.1 Clone

```bash
git clone https://github.com/mrnetwork0001/Triadr.git
cd Triadr
```

### 3.2 Run the agent in your terminal (30 seconds)

```bash
python3 main.py --scenario all
```

You will see four runs and a comparison table:

```
  scenario   outcome      steps   faults  healed  undone  chain       ms
  clean      APPLIED      6/6     0       0       0       valid      602
  chaos      APPLIED      6/6     15      6       0       valid     1384
  rollback   ROLLED BACK  2/5     4       0       2       valid      612
  rejected   APPLIED      4/6     0       0       0       valid      460
```

How to read it: `chaos` absorbed 15 injected faults and still settled the payout once;
`rollback` lost Stripe after the approval card was posted, so it *undid* the two side
effects it had already made (`undone 2`) and moved no money; `rejected` skipped the payout
by an explicit condition. Every run's audit chain verifies.

Each run also writes `.triadr/<run_id>.jsonl` and an attestation. Verify one:

```bash
python3 main.py --verify .triadr/<run_id>.jsonl
```

### 3.3 Run the web app

Two processes: the FastAPI control plane and the Next.js front end.

```bash
# one-time setup
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm install

# terminal 1 - control plane (API + live event stream)
.venv/bin/uvicorn server:app --port 8000

# terminal 2 - front end
npm run dev            # http://localhost:3000
```

If port 8000 or 3000 is taken on your machine, pick others and tell the front end
where the API is:

```bash
.venv/bin/uvicorn server:app --port 8770
TRIADR_API_URL=http://127.0.0.1:8770 npx next dev --port 8771
```

| Route | What it is |
|---|---|
| `/` | Landing page: the problem, the three apps, the eight gate stages, scenarios, evidence, audit log, how to run it. Works with the API down; adds live app status and a freshly measured benchmark when it is up. |
| `/dashboard` | The run console. Pick a scenario, run the agent, watch every gate decision stream in, inspect the sealed audit chain. |

---

## 4. Guided walkthrough of the dashboard

Open `http://localhost:3000/dashboard`. Left to right, top to bottom:

1. **Left rail** - the five sections of the console, the three connected apps with a
   green dot for *live* or grey for *simulated*, and whether the control plane is online.
2. **Run console** - the instruction (pre-filled), a scenario selector, and **Run agent**.
   Start with **Clean run**.
3. Press **Run agent**. Within a second:
   - **KPI strip** fills with measured numbers: reliability score, faults absorbed, steps
     self-healed, and the gate's own overhead in microseconds.
   - **Execution tree** shows the six steps turning from *queued* to *running* to
     *applied*. Click any step to open its **gate attempts**: each physical attempt,
     which endpoint it hit, the fault it got, and the backoff before the next try.
   - **Gate event stream** scrolls every decision as it happens: `gate.fault`,
     `gate.backoff`, `gate.ok`, `saga.compensated` and so on.
   - **Cryptographic audit log** seals when the run ends: entry count, Merkle root, and
     a *Chain verified* badge that was recomputed from the entry bodies, not stamped.
4. Now run **Chaos storm**. Watch steps go amber (*self-healed*) and expand one - you
   will see `TIMEOUT` on the primary gateway, `RATE_LIMITED` on the replica, then success.
   The payout still settles exactly once.
5. Run **Stripe outage**. Stripe is forced down *after* the approval card is posted.
   Watch the run stop, then the **rollback**: the Telegram card is retracted and the
   commit status reset, in reverse order. Result banner: *rolled back cleanly, 2/2 side
   effects reversed, no partial state remains.*
6. Run **Reviewer rejects**. The payout step is *skipped* by condition, and the receipt with it.

Everything you just watched came from the simulators. To make it real, keep going.

---

## 5. Try it live - real GitHub, Telegram and Stripe

Each app switches itself to **LIVE** the moment its credential is present. You can bring
them up one at a time; the readiness check works per app. Full detail, including the
minimum scopes, is in [docs/LIVE_SETUP.md](docs/LIVE_SETUP.md).

### 5.1 Credentials (about 15 minutes total)

```bash
cp .env.example .env     # then fill in the values below
```

| App | What you need | Where |
|---|---|---|
| **GitHub** | A fine-grained personal access token scoped to **one repo you own**, with *Pull requests: read* and *Commit statuses: read & write* (*Checks: read* is optional). Plus an **open pull request** in that repo. | github.com → Settings → Developer settings → Fine-grained tokens |
| **Telegram** | A bot token from **@BotFather** (`/newbot`). Then open your bot and send it any message - bots cannot start a conversation. | Telegram app |
| **Stripe** | A **test-mode** secret key (`sk_test_…`), and **Connect enabled** once (Dashboard → Connect → Get started → *You collect payments and pay recipients*). | dashboard.stripe.com |

```dotenv
GITHUB_TOKEN=github_pat_…      TRIADR_REPO=owner/repo       TRIADR_PR=1
TELEGRAM_BOT_TOKEN=123456:AA…  TRIADR_TELEGRAM_CHAT_ID=      # left blank - discovered below
STRIPE_SECRET_KEY=sk_test_…    TRIADR_CONTRACTOR_ACCOUNT=    # left blank - created below
TRIADR_APPROVAL_TIMEOUT=120
```

### 5.2 Prove each app, in stages

```bash
python3 scripts/live_check.py
```

Read-only. Prints `PASS` / `FAIL` / `SKIP` per tool with the exact fix for each failure.
On the first run it also **discovers your Telegram chat id** and prints the line to add
to `.env`.

```bash
python3 scripts/live_check.py --stripe-setup
```

Funds the test balance (a $100 test-mode charge) and creates a **test payee** through
Stripe's Accounts v2 API, printing an `acct_…` id to add to `.env` **and an onboarding
link**. Open the link and complete the form with test data - use the *Test (Non-OAuth)*
bank and Stripe's test values (`000 000 0000`, DOB `01/01/1901`, SSN `0000`). Until this
is done the payee's transfers capability is `restricted` and every transfer is refused.

```bash
python3 scripts/live_check.py --write --payout
```

A real commit status on your PR, a real Telegram message that deletes itself, and a real
**$1.00 transfer, replayed under the same idempotency key (same transfer id comes back -
no double payment), then reversed.**

```bash
TRIADR_APPROVAL_TIMEOUT=300 python3 scripts/live_check.py --run clean
```

The whole saga, live. A card lands in your Telegram - **press ✓ Approve** - and the
$25 transfer settles, with the receipt posted under the card. Expected output:

```
  succeeded    audit          github.audit_pull_request     2641ms
  succeeded    status         github.set_commit_status      1763ms
  succeeded    approval_card  telegram.post_approval_card    933ms
  succeeded    approval       telegram.await_approval      48921ms   ← the human
  succeeded    payout         stripe.release_escrow         1356ms
  succeeded    receipt        telegram.post_message        10717ms

  6/6 steps applied across 3 apps. 0 fault(s) absorbed, 0 step(s) self-healed,
  0 steps left half-executed. Payout tr_… settled for USD 25.00.
  chain valid: True
```

`--run rollback` does the same with Stripe forced down: the card you just saw is
retracted and the commit status reset, for real.

### 5.3 The live demo from the dashboard

Restart the control plane after editing `.env` (it reads the file at startup), reload
`/dashboard`, and the app dots turn green. The run box now names your real repo, chat and
payee. Press **Run agent**, then **press Approve on your phone when the card arrives** -
the command bar tells you when the agent is waiting on you. Everything on screen is a
real API call; injected faults (Chaos storm) are labelled `[injected]` in the event stream.

Each live clean run moves $25 of test money to the test payee. `--stripe-setup` tops the
balance up again whenever it drops below $50.

---

## 6. Command reference

```bash
# The agent
python3 main.py                        # clean run
python3 main.py --scenario chaos       # clean | chaos | rollback | rejected | all
python3 main.py --instruction "Audit PR #7 in acme/api, sign-off on Telegram, pay acct_1X $50 USD"
python3 main.py --json                 # full result as JSON
python3 main.py --bench                # measured gate overhead, both phases
python3 main.py --verify <log.jsonl>   # re-verify a written audit chain

# Evidence
python3 scripts/campaign.py --runs 40  # regenerates every figure in this README
python3 -m pytest tests/ -q            # 171 tests

# Live readiness
python3 scripts/live_check.py                 # read-only checks per app
python3 scripts/live_check.py --write         # + a write and its undo per app
python3 scripts/live_check.py --approve       # + a real approval card; press a button
python3 scripts/live_check.py --stripe-setup  # fund test balance, create/inspect the payee
python3 scripts/live_check.py --payout        # + $1 transfer, replay, reversal
python3 scripts/live_check.py --run clean     # full saga, live
python3 scripts/live_check.py --run rollback  # full saga with Stripe forced down

# Web app
.venv/bin/uvicorn server:app --port 8000      # control plane (npm run api)
npm run dev                                   # front end (npm run build / npm start for production)
npm run typecheck
```

---

## 7. Configuration reference

All variables live in `.env` (see `.env.example`), loaded by every entry point. Existing
environment variables always win over the file.

| Variable | Purpose | Default |
|---|---|---|
| `GITHUB_TOKEN` | Fine-grained PAT; presence switches GitHub to LIVE | - |
| `TRIADR_REPO` / `TRIADR_PR` | Repository (`owner/name`) and open PR number to audit | `mrnetwork/triadr` / `42` |
| `TELEGRAM_BOT_TOKEN` | BotFather token; presence switches Telegram to LIVE | - |
| `TRIADR_TELEGRAM_CHAT_ID` | User or group id (negative for groups) or `@public_channel` | `@triadr_approvals` |
| `TRIADR_APPROVAL_TIMEOUT` | Seconds a human has to press Approve / Reject | `30` |
| `STRIPE_SECRET_KEY` | Test-mode key; presence switches Stripe to LIVE | - |
| `TRIADR_CONTRACTOR_ACCOUNT` | Connected account the escrow is released to | placeholder |
| `TRIADR_PAYOUT_AMOUNT` / `TRIADR_CURRENCY` | Payout amount (major units) and ISO currency | `2500.00` / `usd` |
| `TRIADR_ALLOW_LIVE_MONEY` | Must be `1` for an `sk_live_` key to move money. Leave unset. | - |
| `TRIADR_APPROVAL_THRESHOLD` | Risk score at or above which a human must approve | `30` |
| `TRIADR_LOG_KEY` | HMAC key that signs each run's attestation | unsigned |
| `TRIADR_LOG_DIR` | Where audit logs are written | `.triadr` |
| `TRIADR_<APP>_ENDPOINTS` | Comma-separated real gateways to fail over across in LIVE mode | one real API |
| `TRIADR_CHAOS` | `1` starts the MCP stdio server with chaos armed | - |
| `TRIADR_LLM_PLANNER` + `ANTHROPIC_API_KEY` | Let Claude extract instruction parameters (never invent steps) | off |
| `TRIADR_API_URL` | Where the front end proxies `/api/*` | `http://127.0.0.1:8000` |

---

## 8. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `address already in use` starting uvicorn or Next | Another process owns the port. Use other ports: `uvicorn server:app --port 8770` and `TRIADR_API_URL=http://127.0.0.1:8770 npx next dev --port 8771`. |
| Dashboard says *api offline* | The control plane is not running, or the front end proxies to the wrong port. Start uvicorn; check `TRIADR_API_URL`. |
| Apps still show *simulated* after adding credentials | The control plane reads `.env` at startup - restart uvicorn. The CLI and scripts read it on every run. |
| `python3 main.py --scenario clean` rolls back with Stripe LIVE | Your real key is in `.env`, so Stripe is live and the placeholder payee does not exist. Run `--stripe-setup` and complete onboarding, or remove the key to go back to the simulator. |
| Telegram: `no chat has messaged the bot yet` | Open your bot in Telegram, press **Start**, send any message, re-run `live_check.py`. |
| Telegram: `409 Conflict` | A webhook is registered for the bot. Triadr clears it automatically and continues. |
| Stripe: *Stripe no longer recommends Accounts v1* | Your platform requires Accounts v2 - `--stripe-setup` already uses it; update Triadr if you see this elsewhere. |
| Stripe: `insufficient_capabilities_for_transfer` | The payee has not finished onboarding. Re-run `--stripe-setup` to re-open the link, complete it with test data, retry `--payout`. |
| Stripe: *You can only create new accounts if you've signed up for Connect* | Dashboard → Connect → Get started, then re-run `--stripe-setup`. |
| GitHub: 404 on the repository | Fine-grained tokens are per-repo: the token must be granted access to `TRIADR_REPO`. |
| GitHub: no *Checks* permission offered | Optional. `get_check_runs` falls back to the commit-status API, which *Commit statuses* already covers. |
| The approval card arrived but the run timed out | Press the button on the **newest** card; older cards are disarmed and answer with an "expired" toast. Raise `TRIADR_APPROVAL_TIMEOUT`. |
| `npm run build` broke the running dev server | Both use `.next/`. Stop the dev server before building, then restart it. |

---

## 9. How it works

```
        "Audit PR #42, get sign-off on Telegram, then pay $2,500 from escrow"
                                      │
                                      ▼
                          ┌───────────────────────┐
                          │  Planner              │  deterministic plan shape,
                          │  agents/planner.py    │  parameters bound from text
                          └───────────┬───────────┘
                                      ▼
                          ┌───────────────────────┐
                          │  Saga orchestrator    │  6 steps, typed dependencies,
                          │  agents/orchestrator  │  every mutation has a rollback
                          └───────────┬───────────┘
                                      ▼
        ╔═════════════════════════════════════════════════════════════╗
        ║   RELIABILITY GATE - risk_gate.py                           ║
        ║   idempotency · schema · drift · rate shaping · breakers    ║
        ║   backoff+jitter · endpoint failover · compensation         ║
        ╚══════════┬═══════════════════┬══════════════════┬═══════════╝
                   ▼                   ▼                  ▼
            ┌────────────┐      ┌────────────┐    ┌────────────┐
            │  GitHub    │      │  Telegram  │    │  Stripe    │   MCP servers,
            │  6 tools   │      │  4 tools   │    │  4 tools   │   14 tools total
            └────────────┘      └────────────┘    └────────────┘
                   │                   │                  │
                   └───────────────────┼──────────────────┘
                                       ▼
                          ┌───────────────────────┐
                          │  SHA-256 hash chain   │  tamper-evident evaluation log
                          │  reliability_logger   │  + merkle root + HMAC signature
                          └───────────────────────┘
```

### The gate, in execution order

Every call to any of the three apps goes through `ReliabilityGate.guard()`:

1. **Idempotency ledger** - a replayed key returns the recorded result. A retried payout whose response was lost in flight cannot pay twice.
2. **Input schema validation** - zero-LLM, ~1.4 µs. A malformed payload is blocked *before* the executor runs, so a bad call has no side effect at all.
3. **Token bucket** - client-side rate shaping sized below each vendor's documented ceiling, so Triadr sheds load before the vendor does.
4. **Circuit breakers** - per endpoint, `CLOSED → OPEN → HALF_OPEN`. An open endpoint is never selected and costs no retry budget. If the whole fleet is open, one probe is still admitted rather than failing a workflow a single call would have saved.
5. **Execution with typed faults** - every failure is classified (`RATE_LIMITED`, `TIMEOUT`, `AUTH_EXPIRED`, `PERMISSION_DENIED`, …). Retryable faults back off exponentially with full jitter and honour `Retry-After`; terminal faults like a 403 are never retried.
6. **Endpoint failover** - attempts cycle across health-ranked gateways, not the same dead host.
7. **Response contract checking** - a declared `outputSchema` catches drift on the very first call; a learned per-tool fingerprint catches it thereafter. A vendor renaming `decision` to `decision_v2` is caught and rerouted instead of silently corrupting the payout decision.
8. **Compensation** - if a critical step is unrecoverable, completed side effects are undone in reverse order, with a larger retry budget than the forward path.

### The audit log

```
digest(n) = SHA256( digest(n-1) ‖ canonical_json(entry(n)) )
```

Editing, reordering or deleting any entry breaks verification at exactly the corrupted
index. The attestation carries a Merkle root over all entries and, with `TRIADR_LOG_KEY`
set, an HMAC signature. `run.end` is recorded before the seal, so the commitment covers
the complete log.

---

## 10. Evidence

Measured on a laptop (`python3 main.py --bench`), never hardcoded:

| Phase | p50 | p99 |
|---|---|---|
| Input schema validation | **1.42 µs** | 1.71 µs |
| Full pre-flight (+ drift fingerprint) | **4.92 µs** | 6.54 µs |

The landing page re-measures this on every load when the control plane is up, and the
dashboard shows the percentiles from your own run.

```bash
python3 -m pytest tests/ -q     # 171 tests
```

Covering schema validation edge cases, breaker transitions, backoff bounds, endpoint
routing, idempotency, drift detection, chaos determinism, the MCP JSON-RPC surface, the
LIVE request wiring for all 14 tools (method, URL, encoding, auth and idempotency
headers, verified against a recorder), hash-chain tamper evidence, and an 8-seed property
test asserting the core invariant: **every run ends fully applied or fully reverted.**
The suite is hermetic: a developer's `.env` can never turn a unit test live.

The full write-up for judges is [docs/RELIABILITY_BRIEF.md](docs/RELIABILITY_BRIEF.md).

---

## 11. Triadr as an MCP server

The 14 tools are exposed over the standard MCP stdio transport, dependency-free - and
every call an MCP host makes is gate-supervised, so the host inherits retry, rerouting,
idempotency and rollback for free.

```bash
claude mcp add triadr -- python3 /path/to/Triadr/mcp_servers/stdio_server.py
```

| App | Tools |
|---|---|
| **GitHub** | `get_pull_request` · `list_changed_files` · `get_check_runs` · `audit_pull_request` · `set_commit_status` · `clear_status` |
| **Telegram** | `post_approval_card` · `await_approval` · `post_message` · `delete_message` |
| **Stripe** | `get_balance` · `release_escrow` · `get_transfer` · `reverse_transfer` |

Every tool that mutates remote state declares the tool that undoes it - enforced by a test.

---

## 12. Safety

- Stripe refuses to move money on an `sk_live_` key unless `TRIADR_ALLOW_LIVE_MONEY=1` is explicitly set.
- The planner's *shape* is fixed in code. An LLM may only extract parameters, never invent a step - a hallucinated extra `release_escrow` would be a financial incident.
- Condition evaluation is a deliberately tiny parser, not `eval`.
- Every payout carries an idempotency key derived from the workload, not the attempt.
- Every app reports `LIVE` or `SIMULATED` in results, dashboard and audit log; injected faults are labelled `[injected]`.
- Secrets never reach a log: the Telegram bot token is redacted from every fault, and `.env` / `.triadr/` are git-ignored.

---

## 13. Repository layout

| Path | |
|---|---|
| `risk_gate.py` | The reliability gate. Stdlib only, no LLM on the hot path. |
| `agents/planner.py` | Instruction → typed plan with a fixed shape. |
| `agents/orchestrator.py` | Saga engine with reverse-order compensation. |
| `agents/reliability_logger.py` | Hash-chained evaluation log, Merkle root, signature. |
| `mcp_servers/` | GitHub, Telegram and Stripe servers, the registry, and the MCP stdio server. |
| `env.py` / `brand.py` | Stdlib `.env` loader; the text glyph used on Telegram and the CLI. |
| `main.py` | CLI: scenarios, benchmark, verifier. |
| `server.py` | FastAPI control plane with SSE streaming. |
| `scripts/campaign.py` | Reproduces every figure in this README. |
| `scripts/live_check.py` | Proves each app against its real API; Stripe test setup. |
| `tests/` | 171 tests, hermetic. |
| `app/page.tsx` · `components/landing/` · `lib/landing-content.ts` | Landing page, its sections, motion kit and single-sourced figures. |
| `app/dashboard/` · `components/dashboard/` · `components/` | Run console: sidebar, top bar, command bar, KPI strip and the live panels. |
| `public/brand/` · `public/logos/` · `app/icon.png` | Header lockup, vendor logos, favicon. |
| `docs/RELIABILITY_BRIEF.md` | System & reliability brief for judges. |
| `docs/LIVE_SETUP.md` | Credentials, minimum scopes, Stripe Connect setup, what is real vs injected. |
| `docs/BRAND_BRIEF.md` | Positioning, voice and vocabulary. |

---

## License

Apache 2.0
