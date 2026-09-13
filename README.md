# Triadr - Self-Healing Multi-App Agent & Reliability Engine

<img width="2988" height="1716" alt="image" src="https://github.com/user-attachments/assets/dfe3da29-83ed-4c0d-90de-d7710ce3aeb1" />


> Built for the **Multi-App AI Agent Hackathon** (`multiappagenthackathon.com`)
> **Connected apps:** GitHub (code audit) · Telegram (team approval) · Stripe (escrow payout)
> **Stack:** Model Context Protocol · Python 3.11+ · FastAPI · Next.js 14 · Tailwind CSS
> **License:** Apache 2.0

---

## The problem

Most multi-app agents are linear scripts. They work in a demo and fail in production,
because the failure they are least prepared for is the ordinary one: a 429, a 502, a
vendor quietly renaming a field. When step 4 of 6 dies, steps 1–3 have already
happened. The Telegram approval card is still sitting in the chat. The money already
moved. Nobody can reconstruct what the agent actually did.

**Triadr is the engine that makes that impossible.** Every side effect across all three
apps passes through one gate that validates, retries, reroutes, deduplicates and - when
a step is genuinely unrecoverable - rolls the whole workflow back.

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

Reproduce: `python3 scripts/campaign.py --runs 40`

---

## Quickstart

No credentials required - every app falls back to a deterministic simulator, so the
full demo runs offline.

```bash
git clone <this repo> && cd Triadr

# 1. The agent, end to end, in your terminal
python3 main.py --scenario all      # stdlib only, no pip install needed

# 2. The web app
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn server:app --port 8000   # control plane
npm install && npm run dev                 # http://localhost:3000
```

| Route | |
|---|---|
| `/` | Landing page - the problem, the three apps, the eight gate stages, the evidence, and how to run it. Works with the control plane down; enriches itself with live app status and a freshly measured benchmark when it is up. |
| `/dashboard` | The live visualiser. Pick a scenario, run the agent, watch every gate decision stream in. |

Add real credentials by copying `.env.example` to `.env`; each app switches itself to
`LIVE` mode the moment its token is present, and the dashboard says which mode it is in.

### Going live

```bash
python3 scripts/live_check.py                 # prove each app against its real API, read-only
python3 scripts/live_check.py --write --approve --payout   # + writes, a real approval, a $1 transfer
python3 scripts/live_check.py --run clean     # the whole saga, LIVE
```

[docs/LIVE_SETUP.md](docs/LIVE_SETUP.md) lists the minimum scopes per app and the one-command
Stripe test setup. The LIVE request paths are also covered by `tests/test_live_paths.py`
(method, URL, JSON-vs-form encoding, auth and idempotency headers), so the only things left
to go wrong with real credentials are the credentials.

---

## The four scenarios

`python3 main.py --scenario <name>`

| Scenario | What it proves |
|---|---|
| `clean` | The happy path: 6 steps, 3 apps, one settled payout. |
| `chaos` | ~75% of calls fail first try. The gate heals them; the payout still settles once. |
| `rollback` | Stripe goes hard-down *after* the approval card is posted. Triadr retracts the Telegram card and resets the commit status. No money moved, no stale approval left behind. |
| `rejected` | The reviewer says no. The payout step is skipped by condition, not by accident. |

```
  scenario   outcome      steps   faults  healed  undone  chain       ms
  clean      APPLIED      6/6     0       0       0       valid      602
  chaos      APPLIED      6/6     15      6       0       valid     1384
  rollback   ROLLED BACK  2/5     4       0       2       valid      612
  rejected   APPLIED      4/6     0       0       0       valid      460
```

---

## Architecture

```
        "Audit PR #42, get sign-off in #eng-approvals, pay $2,500 from escrow"
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

### What the gate actually does

Every call to any of the three apps goes through `ReliabilityGate.guard()`, in order:

1. **Idempotency ledger** - a replayed key returns the recorded result. A retried payout whose response was lost in flight cannot pay twice.
2. **Input schema validation** - zero-LLM, ~1.4 µs. A malformed payload is blocked *before* the executor runs, so a bad call has no side effect at all.
3. **Token bucket** - client-side rate shaping sized below each vendor's documented ceiling, so Triadr sheds load before the vendor does.
4. **Circuit breakers** - per endpoint, `CLOSED → OPEN → HALF_OPEN`. An open endpoint is never selected, and costs no retry budget. If the whole fleet is open, one probe is still admitted rather than failing a workflow a single call would have saved.
5. **Execution with typed faults** - every failure is classified (`RATE_LIMITED`, `TIMEOUT`, `AUTH_EXPIRED`, `PERMISSION_DENIED`, …). Retryable faults back off exponentially with full jitter and honour `Retry-After`; terminal faults like a 403 are never retried.
6. **Endpoint failover** - attempts cycle across health-ranked MCP gateways, not the same dead host.
7. **Response contract checking** - declared `outputSchema` catches drift on the very first call; a learned per-tool fingerprint catches it thereafter. A vendor renaming `decision` to `decision_v2` is caught and rerouted instead of silently corrupting the payout decision.
8. **Compensation** - if a critical step is unrecoverable, completed side effects are undone in reverse order.

Measured on this machine (`python3 main.py --bench`):

| Phase | p50 | p99 |
|---|---|---|
| Input schema validation | **1.42 µs** | 1.71 µs |
| Full pre-flight (+ drift fingerprint) | **4.92 µs** | 6.54 µs |

These are measured at runtime, not asserted. The dashboard shows the percentiles from
your own run.

---

## Triadr as an MCP server

The 14 tools are exposed over the standard MCP stdio transport, dependency-free -
and every call an MCP host makes is gate-supervised, so the host inherits retry,
rerouting, idempotency and rollback for free.

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

## The audit log

Each run writes a SHA-256 hash-chained JSONL log plus an attestation:

```
digest(n) = SHA256( digest(n-1) ‖ canonical_json(entry(n)) )
```

Editing, reordering or deleting any entry breaks verification at exactly the corrupted
index. The attestation carries a Merkle root over all entries and, with `TRIADR_LOG_KEY`
set, an HMAC signature.

```bash
python3 main.py --verify .triadr/<run_id>.jsonl
```

The reliability numbers Triadr reports are auditable rather than asserted.

---

## Safety

- Stripe refuses to move money on an `sk_live_` key unless `TRIADR_ALLOW_LIVE_MONEY=1` is explicitly set.
- The planner's *shape* is fixed in code. An LLM may only extract parameters, never invent a step - a hallucinated extra `release_escrow` would be a financial incident.
- Condition evaluation is a deliberately tiny parser, not `eval`.
- Every payout carries an idempotency key derived from the workload, not the attempt.

---

## Tests

```bash
python3 -m pytest tests/ -q     # 164 tests
```

Covering schema validation, breakers, backoff bounds, endpoint routing, idempotency,
drift detection, chaos determinism, the MCP JSON-RPC protocol surface, hash-chain
tamper evidence, the LIVE request wiring for all 14 tools, and an 8-seed property test
asserting the core invariant: **every run ends fully applied or fully reverted.**

---

## Layout

| Path | |
|---|---|
| `risk_gate.py` | The reliability gate. Stdlib only, ~1000 lines, no LLM on the hot path. |
| `agents/orchestrator.py` | Saga engine with compensation. |
| `agents/planner.py` | Instruction → typed plan. |
| `agents/reliability_logger.py` | Hash-chained evaluation log. |
| `mcp_servers/` | The three app servers + registry + MCP stdio server. |
| `server.py` | FastAPI control plane with SSE streaming. |
| `app/page.tsx` | Landing page. |
| `app/dashboard/` | Live visualiser. |
| `components/landing/` | Landing page sections. |
| `lib/landing-content.ts` | Every figure quoted on the landing page, single-sourced. |
| `scripts/campaign.py` | Reproduces every number in this README. |
| `scripts/live_check.py` | Proves each app against its real API; funds and prepares Stripe test mode. |
| `env.py` | Stdlib `.env` loader - every entry point calls it, so credentials are never silently ignored. |
| `docs/RELIABILITY_BRIEF.md` | System & reliability brief. |
| `docs/LIVE_SETUP.md` | Credentials, minimum scopes, and what is real vs injected in LIVE mode. |

---

## License

Apache 2.0
