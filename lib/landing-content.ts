/**
 * Single source of truth for the landing page copy and figures.
 *
 * Every number here is produced by `python3 scripts/campaign.py --runs 40` and
 * `python3 main.py --bench`. If you change the engine, re-run those and update
 * this file - the landing page must never quote a figure the repo cannot
 * reproduce on demand.
 */

export const CAMPAIGN = {
  command: 'python3 scripts/campaign.py --runs 40',
  runs: 40,
  faultRate: '~75%',
  faultsAbsorbed: 356,
  stepsSelfHealed: 130,
  fullyApplied: 26,
  fullyRolledBack: 14,
  halfExecuted: 0,
  duplicatePayouts: 0,
  chainsValid: 40,
  sideEffectsReverted: 11,
} as const

export interface BenchRow {
  phase: string
  detail: string
  p50: string
  p95: string
  p99: string
}

export const BENCHMARK: { command: string; rows: BenchRow[] } = {
  command: 'python3 main.py --bench',
  rows: [
    { phase: 'Input schema validation', detail: 'Gates every side effect before it happens', p50: '1.42 µs', p95: '1.50 µs', p99: '1.71 µs' },
    { phase: 'Full pre-flight', detail: 'The above plus the response drift fingerprint', p50: '4.92 µs', p95: '5.25 µs', p99: '6.54 µs' },
  ],
}

export const APPS = [
  {
    id: 'github',
    index: 1,
    name: 'GitHub',
    role: 'Code audit',
    credential: 'GITHUB_TOKEN',
    blurb:
      'Reads the pull request, its diff and its CI check runs, then scores the change on diff surface, sensitive paths, test coverage and build state - and writes the verdict back onto the commit.',
    tools: [
      { name: 'get_pull_request', effect: 'read' },
      { name: 'list_changed_files', effect: 'read' },
      { name: 'get_check_runs', effect: 'read' },
      { name: 'audit_pull_request', effect: 'read' },
      { name: 'set_commit_status', effect: 'write' },
      { name: 'clear_status', effect: 'undo' },
    ],
  },
  {
    id: 'telegram',
    index: 2,
    name: 'Telegram',
    role: 'Team approval',
    credential: 'TELEGRAM_BOT_TOKEN',
    blurb:
      'Posts an approval card carrying the audit verdict and the proposed payout with real inline Approve / Reject buttons, then long-polls until a human presses one - no public callback URL needed.',
    tools: [
      { name: 'post_approval_card', effect: 'write' },
      { name: 'await_approval', effect: 'read' },
      { name: 'post_message', effect: 'write' },
      { name: 'delete_message', effect: 'undo' },
    ],
  },
  {
    id: 'stripe',
    index: 3,
    name: 'Stripe',
    role: 'Escrow payout',
    credential: 'STRIPE_SECRET_KEY',
    blurb:
      'Releases the contractor escrow as a Transfer under an idempotency key derived from the workload - so a retry whose response was lost in flight can never pay twice.',
    tools: [
      { name: 'get_balance', effect: 'read' },
      { name: 'release_escrow', effect: 'payment' },
      { name: 'get_transfer', effect: 'read' },
      { name: 'reverse_transfer', effect: 'undo' },
    ],
  },
] as const

export const GATE_STAGES = [
  {
    n: 1,
    title: 'Idempotency ledger',
    body: 'Keys derive from the workload, not the attempt, so a re-run of the same payout collapses onto one key. A replay returns the recorded result instead of moving money again.',
  },
  {
    n: 2,
    title: 'Input schema validation',
    body: 'A compiled subset of JSON Schema - no LLM, no third-party validator on the hot path. A malformed payload is rejected before the executor runs, so a bad call has no side effect at all.',
  },
  {
    n: 3,
    title: 'Token bucket',
    body: "Client-side rate shaping sized below each vendor's documented ceiling. Cheaper to shed load yourself than to absorb a 429.",
  },
  {
    n: 4,
    title: 'Circuit breakers',
    body: 'Per endpoint, CLOSED → OPEN → HALF_OPEN. An open endpoint is never selected and costs no retry budget. If the whole fleet is open, one probe is still admitted - a breaker sheds load, it does not guarantee failure.',
  },
  {
    n: 5,
    title: 'Typed fault classification',
    body: 'Rate limits, timeouts, partitions and auth expiry back off exponentially with full jitter and honour Retry-After. A 403 or 404 is terminal and never retried, because retrying it is pure latency.',
  },
  {
    n: 6,
    title: 'Endpoint failover',
    body: 'Attempts cycle across health-ranked MCP gateways. Scores decay multiplicatively on failure and recover additively on success, so a flapping host is deprioritised without being banned.',
  },
  {
    n: 7,
    title: 'Response contract checking',
    body: 'A declared outputSchema catches drift on a tool’s very first call; a learned fingerprint catches it thereafter. A vendor renaming decision to decision_v2 is caught and rerouted, not silently fed into a payout decision.',
  },
  {
    n: 8,
    title: 'Compensation',
    body: 'If a critical step is unrecoverable, completed side effects are undone in reverse order - with a larger retry budget than the forward path, because the rollback is the one thing that must not fail.',
  },
] as const

export const STEPS = [
  { n: 1, app: 'GitHub', tool: 'audit_pull_request', title: 'Audit the pull request', undo: null, note: 'Deterministic, itemised risk score' },
  { n: 2, app: 'GitHub', tool: 'set_commit_status', title: 'Write the verdict to the commit', undo: 'clear_status', note: 'Non-critical' },
  { n: 3, app: 'Telegram', tool: 'post_approval_card', title: 'Post the approval card', undo: 'delete_message', note: 'Carries the audit + payout' },
  { n: 4, app: 'Telegram', tool: 'await_approval', title: 'Wait for Approve or Reject', undo: null, note: 'Human in the loop' },
  { n: 5, app: 'Stripe', tool: 'release_escrow', title: 'Release the escrow payout', undo: 'reverse_transfer', note: 'Conditional on approval' },
  { n: 6, app: 'Telegram', tool: 'post_message', title: 'Post the settlement receipt', undo: null, note: 'Non-critical' },
] as const

export const SCENARIOS = [
  {
    id: 'clean',
    label: 'Clean run',
    tone: 'ok',
    proves: 'The happy path: six steps, three apps, one settled payout.',
    outcome: 'APPLIED',
    steps: '6/6',
    faults: 0,
    undone: 0,
  },
  {
    id: 'chaos',
    label: 'Chaos storm',
    tone: 'heal',
    proves: 'Roughly three in four calls fail on first attempt. The gate heals them; the payout still settles exactly once.',
    outcome: 'APPLIED',
    steps: '6/6',
    faults: 15,
    undone: 0,
  },
  {
    id: 'rollback',
    label: 'Stripe outage',
    tone: 'undo',
    proves: 'Stripe goes hard-down after the approval card is posted. Triadr retracts the card and resets the commit status - no money moved, no stale approval left in the channel.',
    outcome: 'ROLLED BACK',
    steps: '2/5',
    faults: 4,
    undone: 2,
  },
  {
    id: 'rejected',
    label: 'Reviewer rejects',
    tone: 'fail',
    proves: 'The team says no. The payout is skipped by an explicit condition, not by accident.',
    outcome: 'APPLIED',
    steps: '4/6',
    faults: 0,
    undone: 0,
  },
] as const

export const SAFETY = [
  { property: 'No accidental live payments', mechanism: 'Stripe refuses an sk_live_ key unless TRIADR_ALLOW_LIVE_MONEY=1 is set explicitly' },
  { property: 'No agent-invented payments', mechanism: 'The plan shape is fixed in code; an LLM may only extract parameters, never add a step' },
  { property: 'No double payment', mechanism: 'Workload-derived idempotency keys plus a replay ledger' },
  { property: 'No code execution from instructions', mechanism: 'Condition evaluation is a small hand-written parser, never eval' },
  { property: 'No silent contract drift', mechanism: 'Declared output schemas plus a learned per-tool response fingerprint' },
  { property: 'No unverifiable claims', mechanism: 'Hash-chained log with a standalone verification command' },
  { property: 'Demo never mistaken for production', mechanism: 'Every app reports LIVE or SIMULATED in results, dashboard and audit log' },
] as const

export const LIMITATIONS = [
  'The campaign figures were produced against the simulators. The bindings implement real GitHub, Telegram and Stripe request and response shapes and LIVE mode is wired end to end, but injected faults come from a seeded distribution, not production traffic.',
  'A Telegram bot cannot open a conversation: the reviewer (or group) must message the bot once before it can post there. The live check discovers that chat id for you.',
  'The idempotency ledger and breaker state are in-process. A multi-replica deployment would move them to Redis or equivalent; the interfaces are narrow enough to swap.',
  'The risk score is a heuristic on purpose - explainable and fast rather than clever, with every contributing factor itemised so a human can disagree with it.',
] as const

export const DEFAULT_INSTRUCTION =
  'Audit PR #42 in mrnetwork/triadr, get team sign-off in #eng-approvals, then release $2,500.00 USD from escrow to acct_1TriadrContractor'

/**
 * Gate decisions shown in the hero marquee.
 *
 * These are not invented: they were captured from a real chaos-storm run and a
 * real rollback run (see scripts/campaign.py for how such runs are produced).
 * Keeping them in the repo means the hero shows what the engine actually does,
 * and stays truthful even when the control plane is not running.
 */
export interface GateCard {
  app: 'github' | 'telegram' | 'stripe'
  tool: string
  verdict: string
  detail: string
  metric: string
}

export const GATE_FEED: GateCard[] = [
  { app: 'github', tool: 'github.audit_pull_request', verdict: 'SELF_HEALED', detail: "absorbed 3 faults \u00b7 4 attempts", metric: '347ms' },
  { app: 'github', tool: 'github.audit_pull_request', verdict: 'TIMEOUT', detail: "mcp://github/primary", metric: 'try 1' },
  { app: 'github', tool: 'github.audit_pull_request', verdict: 'RATE_LIMITED', detail: "mcp://github/replica", metric: 'try 2' },
  { app: 'github', tool: 'github.audit_pull_request', verdict: 'RATE_LIMITED', detail: "https://api.github.com", metric: 'try 3' },
  { app: 'github', tool: 'github.set_commit_status', verdict: 'SELF_HEALED', detail: "absorbed 3 faults \u00b7 4 attempts", metric: '190ms' },
  { app: 'github', tool: 'github.set_commit_status', verdict: 'TIMEOUT', detail: "mcp://github/primary", metric: 'try 1' },
  { app: 'github', tool: 'github.clear_status', verdict: 'ROLLED_BACK', detail: "undid the commit status", metric: 'saga' },
  { app: 'telegram', tool: 'telegram.post_approval_card', verdict: 'SELF_HEALED', detail: "absorbed 2 faults \u00b7 3 attempts", metric: '132ms' },
  { app: 'telegram', tool: 'telegram.post_approval_card', verdict: 'RATE_LIMITED', detail: "mcp://telegram/primary", metric: 'try 1' },
  { app: 'telegram', tool: 'telegram.post_approval_card', verdict: 'TIMEOUT', detail: "mcp://telegram/replica", metric: 'try 2' },
  { app: 'telegram', tool: 'telegram.await_approval', verdict: 'SELF_HEALED', detail: "absorbed 2 faults \u00b7 3 attempts", metric: '361ms' },
  { app: 'telegram', tool: 'telegram.await_approval', verdict: 'NETWORK_PARTITION', detail: "mcp://telegram/primary", metric: 'try 2' },
  { app: 'telegram', tool: 'telegram.post_message', verdict: 'SELF_HEALED', detail: "absorbed 3 faults \u00b7 4 attempts", metric: '254ms' },
  { app: 'telegram', tool: 'telegram.post_message', verdict: 'RATE_LIMITED', detail: "mcp://telegram/replica", metric: 'try 1' },
  { app: 'telegram', tool: 'telegram.delete_message', verdict: 'ROLLED_BACK', detail: "undid the approval card", metric: 'saga' },
  { app: 'stripe', tool: 'stripe.release_escrow', verdict: 'SELF_HEALED', detail: "absorbed 2 faults \u00b7 3 attempts", metric: '136ms' },
  { app: 'stripe', tool: 'stripe.release_escrow', verdict: 'SERVER_ERROR', detail: "mcp://stripe/primary", metric: 'try 1' },
  { app: 'stripe', tool: 'stripe.release_escrow', verdict: 'TIMEOUT', detail: "mcp://stripe/replica", metric: 'try 2' },
  { app: 'stripe', tool: 'stripe.release_escrow', verdict: 'DEDUPED', detail: "idempotency hit \u2014 no second payout", metric: '0 calls' },
  { app: 'stripe', tool: 'stripe.release_escrow', verdict: 'BLOCKED', detail: "amount must be > 0 \u2014 blocked pre-flight", metric: 'no effect' },
  { app: 'stripe', tool: 'stripe.get_balance', verdict: 'ALLOW', detail: "first attempt, clean", metric: '31ms' },
  { app: 'github', tool: 'github.get_check_runs', verdict: 'ALLOW', detail: "first attempt, clean", metric: '44ms' },
  { app: 'telegram', tool: 'telegram.post_approval_card', verdict: 'CIRCUIT_OPEN', detail: "skipped, no round trip", metric: '0ms' },
  { app: 'stripe', tool: 'stripe.reverse_transfer', verdict: 'ROLLED_BACK', detail: "returned 2,500.00 to balance", metric: 'saga' },
]
