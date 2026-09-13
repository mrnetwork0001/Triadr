# Triadr - System & Reliability Brief

**Multi-App AI Agent Hackathon submission**
Connected apps: GitHub · Telegram · Stripe · 14 MCP tools · Apache 2.0

---

## 1. What Triadr does

Triadr executes one business workflow that spans three external applications:

> *"Audit PR #42 in mrnetwork/triadr, get team sign-off in #eng-approvals, then release
> $2,500.00 USD from escrow to acct_1TriadrContractor."*

It turns that sentence into a six-step saga:

| # | App | Tool | Rollback |
|---|---|---|---|
| 1 | GitHub | `audit_pull_request` - deterministic risk score over diff surface, sensitive paths, test coverage, CI state | - (read) |
| 2 | GitHub | `set_commit_status` - writes the verdict back to the commit | `clear_status` |
| 3 | Telegram | `post_approval_card` - card carrying the audit and the proposed payout, with inline Approve / Reject buttons | `delete_message` |
| 4 | Telegram | `await_approval` - long-polls for the button press, then freezes the card | - (read) |
| 5 | Stripe | `release_escrow` - transfer to the connected account, idempotency-keyed | `reverse_transfer` |
| 6 | Telegram | `post_message` - settlement receipt as a reply to the card | - (non-critical) |

Step 5 is conditional on step 4 returning `approved`. Steps 2 and 6 are non-critical:
a missing status check or a missing receipt must never reverse a settled payment.

---

## 2. The reliability thesis

A multi-app agent's real failure mode is not a bad model output. It is an ordinary
transport failure at step 4 of 6, which leaves steps 1–3 applied and nobody able to say
what happened. The approval card sits in the channel forever. The money has moved.

**Triadr's claim: a multi-step workflow should end fully applied or fully reverted, and
the record of which should be independently verifiable.**

Everything below exists to make that true.

---

## 3. Architecture

```
  instruction ──▶ planner ──▶ saga orchestrator ──▶ ┌─────────────────────┐
                                                    │  RELIABILITY GATE   │
                                                    └──┬───────┬───────┬──┘
                                                       ▼       ▼       ▼
                                                   GitHub  Telegram  Stripe
                                                       └───────┼───────┘
                                                               ▼
                                                   SHA-256 hash-chained log
```

**The planner's shape is fixed in code.** An LLM may extract parameters (repo, amount,
channel); it can never add, remove or reorder a step. A hallucinated second
`release_escrow` would be a financial incident, so the model is not given that authority.
Whatever it returns is schema-validated before anything executes.

---

## 4. The gate - `risk_gate.py`

Every side effect in every app passes through `guard()`. In order:

**1. Idempotency ledger.** Keys are derived from the *workload*, not the attempt, so a
re-run of the same payout collapses onto the same key. A replay returns the recorded
result. This is what makes retrying a payment safe.

**2. Input schema validation.** A compiled subset of JSON Schema - deliberately not an
LLM call and not the `jsonschema` package, because this runs on the hot path of every
side effect. A malformed payload is rejected *before* the executor runs, so a bad call
has no side effect at all. Measured p50: **1.42 µs**.

**3. Token bucket.** Client-side rate shaping sized below each vendor's documented
ceiling (Telegram Bot API ≈ 1 msg/s per chat, GitHub REST 5000/hr, Stripe 100/s). Cheaper to shape
than to absorb a 429.

**4. Circuit breakers, per endpoint.** `CLOSED → OPEN → HALF_OPEN`. Two properties that
matter and are easy to get wrong:

- An open endpoint is never *selected*, so a dead gateway consumes no retry budget. One
  dead host cannot starve a call a healthy host would have served.
- If every endpoint in a fleet is open, the gate still admits **one probe** against the
  healthiest. A breaker exists to shed load from a struggling backend, not to guarantee
  the caller fails; one probe is cheaper than an unnecessary rollback.

**5. Typed fault classification.** `RATE_LIMITED`, `TIMEOUT`, `SERVER_ERROR`,
`NETWORK_PARTITION`, `AUTH_EXPIRED`, `PERMISSION_DENIED`, `NOT_FOUND`, `SCHEMA_DRIFT`,
`IDEMPOTENCY_CONFLICT`. Retryable faults back off exponentially with full jitter and
honour `Retry-After`. Terminal faults - a 403, a 404 - are never retried, because
retrying them is pure latency.

**6. Endpoint failover.** Attempts cycle across health-ranked MCP gateways. Scores decay
multiplicatively on failure and recover additively on success, so a flapping endpoint is
deprioritised without being permanently banned.

**7. Response contract checking - two layers.**

- *Declared*: tools publish an `outputSchema`, checked on every response. This catches
  drift on a tool's **first** call, which a learned baseline structurally cannot.
- *Learned*: a per-tool key-path/type fingerprint of the first healthy response.
  Subsequent responses are compared against it.

A field that vanished or changed type is always treated as breaking - a severity ratio
is the wrong gate, because downstream steps read these values *by name*. One renamed
field is enough to corrupt a payout decision. The baseline is never updated from a
breaking observation: quietly adopting a mutated payment contract is the failure this
detector exists to prevent.

**8. Compensation.** If a critical step is unrecoverable, completed side effects are
undone in reverse order, with a larger retry budget than the forward path - the rollback
is the one thing that must not fail.

---

## 5. Chaos engine

Faults are injected on a seeded RNG, so a judge can replay the exact failure sequence and
observe the identical recovery path. `ChaosProfile.storm()` fails roughly 75% of calls on
first attempt, mixing rate limits, timeouts, server errors, partitions, auth expiry and
response mutation.

The `rollback` scenario instead injects a hard outage at the app boundary
(`registry.force_fault("stripe.release_escrow", SERVER_ERROR)`), so every layer above
it - gate, saga, logger - behaves exactly as it would during a real Stripe incident.

---

## 6. Evidence

### Campaign - 40 runs under a ~75% fault storm

`python3 scripts/campaign.py --runs 40`

| Metric | Result |
|---|---|
| Runs | 40 |
| Fully applied | 26 |
| Fully rolled back | 14 |
| **Runs left half-executed** | **0** |
| **Duplicate payouts** | **0** |
| Faults absorbed | 356 |
| Steps self-healed | 130 |
| Side effects reverted | 11 |
| Audit chains valid | 40 / 40 |

The 14 rolled-back runs are the important column. Under this fault rate a linear script
would have left partial state in most of them - a posted approval card with no payout, or
a payment with no record. Triadr left none.

### Gate overhead - measured, not asserted

`python3 main.py --bench`

| Phase | p50 | p95 | p99 |
|---|---|---|---|
| Input schema validation | 1.42 µs | 1.50 µs | 1.71 µs |
| Full pre-flight (+ drift fingerprint) | 4.92 µs | 5.25 µs | 6.54 µs |

Both phases are reported because quoting only the first would overstate the engine. The
dashboard shows percentiles from the viewer's own run.

### Test suite

`python3 -m pytest tests/ -q` - **176 tests**, covering schema validation edge cases
(including `True` not satisfying `integer`), breaker state transitions, backoff bounds,
endpoint deprioritisation, idempotency, drift detection, chaos determinism, the MCP
JSON-RPC protocol surface, hash-chain tamper evidence, and an 8-seed property test
asserting the core invariant directly.

A structural test asserts that **every tool mutating remote state declares a
compensation** - the saga guarantee cannot silently rot as tools are added.

---

## 7. The audit log

```
digest(n) = SHA256( digest(n-1) ‖ canonical_json(entry(n)) )
```

Canonical serialisation fixes key order and separators, so an entry hashes identically on
any machine. Editing, reordering or deleting any entry breaks verification at exactly the
corrupted index - demonstrated by test, not just claimed.

The attestation carries a Merkle root over all entry digests and, with `TRIADR_LOG_KEY`
set, an HMAC-SHA256 signature over that root. `run.end` is recorded *before* the
attestation is sealed, so the commitment covers the complete log.

```bash
python3 main.py --verify .triadr/<run_id>.jsonl
```

This is what makes the numbers in §6 auditable rather than marketing.

---

## 8. Safety properties

| Property | Mechanism |
|---|---|
| No accidental live payments | Stripe refuses an `sk_live_` key unless `TRIADR_ALLOW_LIVE_MONEY=1` |
| No agent-invented payments | Plan shape fixed in code; LLM limited to parameter extraction |
| No double payment | Workload-derived idempotency keys + ledger |
| No code execution from instructions | Condition evaluation is a small hand-written parser, never `eval` |
| No silent contract drift | Declared + learned response contracts |
| No unverifiable claims | Hash-chained log with independent verification command |
| Demo never mistaken for production | Every app reports `LIVE` or `SIMULATED` in results, dashboard and audit log |

---

## 9. Running it

```bash
python3 main.py --scenario all        # four scenarios, stdlib only
python3 -m pytest tests/ -q           # test suite
python3 scripts/campaign.py --runs 40 # regenerate §6

.venv/bin/uvicorn server:app --port 8000
npm run dev                           # live visualiser on :3000
```

No credentials are required - each app falls back to a deterministic simulator, and says
so. Adding a token switches that app to `LIVE` with no code change.

---

## 10. Honest limitations

- **The campaign in §6 ran against the simulators.** The tool bindings implement the real
  GitHub, Telegram and Stripe request and response shapes, LIVE mode is wired end to end, and
  `tests/test_live_paths.py` verifies every tool's live request - method, URL, encoding,
  auth and idempotency headers - against a recorder. `scripts/live_check.py` then proves each
  app against its real API with your credentials. But the 40-run figures were produced
  offline, and injected faults are drawn from a seeded distribution, not production traffic.
- **Chaos faults are injected client-side.** In LIVE mode the fault fires before the request
  is sent; the vendor never sees it, and the recovery that follows is a real request. Every
  injected fault is labelled `[injected]` in the event stream and the audit log.
- **One real endpoint per app in LIVE mode.** The primary/replica gateways in simulated mode
  exercise the failover path, but there is no second real gateway to reroute to, so LIVE
  advertises exactly one endpoint unless the operator configures more. Retry, backoff,
  breakers, idempotency and rollback are unaffected.
- **A bot cannot open a conversation.** The reviewer or group must message the bot once
  before it can post there; the live check discovers that chat id. Approval itself is a real
  inline-button press delivered by long-polling - no public callback URL is needed.
- **Single process.** The idempotency ledger and breaker state are in-memory. A
  multi-replica deployment would need them in Redis or equivalent; the interfaces are
  narrow enough to swap.
- **The risk score is a heuristic**, deliberately. It is explainable and fast rather than
  clever, and every contributing factor is itemised in the output so a human can disagree
  with it.

---

*Triadr - one agent, three apps, zero half-executed workflows.*
