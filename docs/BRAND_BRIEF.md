# Triadr - brand brief

Reference document for anyone producing brand, identity or marketing work for Triadr.
It describes what the product is, who it is for, how it should feel and how it should
speak. It deliberately does not describe what the logo should look like.

---

## 1. One-line

**Triadr is a self-healing multi-app AI agent: it carries a business workflow across
GitHub, Telegram and Stripe, and guarantees the workflow ends fully applied or fully
reverted - never half-done.**

## 2. What it does, concretely

A user gives Triadr one sentence:

> "Audit PR #42, get team sign-off on Telegram, then release $2,500 from escrow to the contractor."

Triadr turns that into six gate-supervised steps across three external apps:

1. **GitHub** - reads the pull request, its diff and CI checks, and scores the risk (0-100) with an itemised rationale.
2. **GitHub** - writes the verdict back onto the commit as a status check.
3. **Telegram** - posts an approval card with working Approve / Reject buttons.
4. **Telegram** - waits for a real human to press one.
5. **Stripe** - releases the contractor's escrow payout as a transfer, under an idempotency key.
6. **Telegram** - posts the settlement receipt as a reply to the card.

Every one of those calls passes through a **reliability gate** that validates the payload,
detects when a vendor silently changes its response contract, rate-shapes, opens circuit
breakers on dead endpoints, retries with exponential backoff, deduplicates so money can never
move twice, and - if a step is genuinely unrecoverable - rolls back everything that was already
applied, in reverse order. Every decision the gate makes is written to a SHA-256 hash chain that
anyone can recompute.

## 3. The problem it exists for

Most "AI agents" that touch multiple apps are linear scripts. They work in a demo and break in
production, because the failure they are least prepared for is the ordinary one: a rate limit,
a 502, a renamed field. When step 4 of 6 dies, steps 1-3 have already happened. The approval
request is still sitting in the chat. The money already moved. Nobody can reconstruct what the
agent actually did.

Triadr's thesis: **a multi-step workflow should end fully applied or fully reverted, and the
record of which should be independently verifiable.**

## 4. Proof points (all measured, all reproducible from the repo)

- 40 workflow runs under a fault storm that fails ~75% of calls on first attempt:
  **356 faults absorbed, 130 steps self-healed, 0 runs left half-executed, 0 duplicate payouts,
  40/40 audit chains verify.**
- Gate overhead: input validation in **~1.4 µs** (p50), full pre-flight in **~4.9 µs**.
- 14 MCP tools across the three apps, every write tool declaring the tool that undoes it.
- 171 automated tests, including tamper-evidence tests on the audit chain.
- Verified live against the real GitHub, Telegram and Stripe APIs, including a real human
  button press and a real (test-mode) transfer.
- Exposed as a standard MCP server, so any MCP host inherits the reliability for free.

## 5. Audience

- **Primary:** engineers and technical founders building AI agents that take real actions -
  people who have been burned by an automation that left a mess.
- **Secondary:** engineering leaders evaluating whether agents can be trusted with money,
  approvals and production systems.
- **Immediate context:** judges and peers at a multi-app AI agent hackathon, who will read
  the evidence and may verify it themselves.

## 6. Positioning

- **Category:** reliability engine for multi-app AI agents (not "another agent framework").
- **Differentiator:** the guarantee and the proof. Others show an agent doing things; Triadr shows
  an agent that cannot leave things half-done, and hands you the receipts.
- **Competitive frame:** linear agent scripts, generic workflow tools, and orchestration
  frameworks that retry but do not roll back or attest.
- **What it is not:** not a chatbot, not a no-code builder, not a payments product, not a
  monitoring dashboard bolted onto someone else's agent.

## 7. Personality and tone

- **Calm under failure.** The product's whole point is composure when things go wrong; the brand
  should never feel frantic, flashy or hype-driven.
- **Precise.** Numbers are measured, not asserted. Claims come with a command that reproduces them.
- **Honest.** Limitations are stated up front. The product distinguishes "live" from "simulated"
  everywhere and labels injected faults as injected.
- **Engineered, not decorated.** Aesthetic of instrumentation, audit trails, control rooms,
  blueprints - not consumer gloss.
- **Quietly confident.** Short declarative sentences. No exclamation marks. No "revolutionary".

Voice examples that fit:
- "Never left half-executed."
- "Measured, not asserted."
- "Every run ends fully applied or fully reverted."
- "One agent, three apps, zero half-executed workflows."
- "Reliability claims you can recompute yourself."

Voice that does not fit: "supercharge", "10x", "magic", "effortless", "AI-powered everything".

## 8. Name

- **Triadr** - from *triad*: three connected apps, one engine. Pronounced "TRY-ad-er".
- Always written **Triadr** in prose; **TRIADR** is acceptable in wordmark/lockup contexts.
- Never "Triader", "Triadr AI", "TriadR".

## 9. Vocabulary the brand owns

- *the gate* - the reliability layer every side effect passes through
- *self-healing* - retry, reroute, deduplicate, roll back, automatically
- *half-executed* - the failure state Triadr eliminates
- *applied / rolled back* - the only two outcomes a run can have
- *hash chain, attestation, verify* - the audit language
- *live vs simulated* - always disclosed

## 10. Visual system already in use (for consistency, not prescription)

- Dark interface: near-black base (#07080c / #0b0d14), slate greys for text.
- A small set of signal colours with fixed meanings: green = applied/ok, amber = self-healed,
  red = fault, purple = rolled back, sky blue = live/active.
- Monospace type for anything machine-produced (tool names, hashes, commands); a clean
  sans-serif for prose.
- Recurring motifs: a gate/checkpoint, a path through three nodes, chained blocks, a status dot.
- Motion is restrained: reveals, counters, a slow marquee of real gate decisions.

## 11. Facts and constraints

- Open source, Apache 2.0.
- Built by Ifeanyichukwu Onwo (mrnetwork).
- Connected apps: GitHub, Telegram, Stripe. Built on the Model Context Protocol (MCP), Python,
  FastAPI and Next.js.
- Do not imply endorsement by GitHub, Telegram or Stripe; their logos appear only as
  "connected apps".
- Do not claim production traffic numbers; the campaign figures are from a controlled fault
  simulation and are labelled as such.

## 12. What good branding output would achieve

Someone who sees Triadr for five seconds should understand: *this is the layer that makes AI
agents safe to hand real actions to - and it can prove it.*
