// Shared shapes between the FastAPI control plane and the visualiser.

export type Verdict =
  | 'ALLOW' | 'SELF_HEALED' | 'DEDUPED' | 'DEGRADED' | 'BLOCKED' | 'COMPENSATE'

export type StepStatus =
  | 'pending' | 'running' | 'succeeded' | 'healed' | 'skipped' | 'failed' | 'compensated'

export interface AppStatus {
  app: string
  mode: 'LIVE' | 'SIMULATED'
  tools: number
  calls: number
  credentials_required: string[]
  credentials_missing: string[]
  connected: boolean
}

export interface Scenario {
  id: string
  label: string
  description: string
}

export interface AppsResponse {
  apps: AppStatus[]
  connected_count: number
  live_count: number
  tool_count: number
  total_calls: number
  scenarios: Scenario[]
  /** Built server-side from TRIADR_* env, so a LIVE setup names real identifiers. */
  default_instruction?: string
}

export interface GateAttempt {
  index: number
  endpoint: string
  duration_ms: number
  ok: boolean
  fault: string | null
  message: string
  backoff_ms: number
}

export interface GateOutcome {
  app: string
  tool: string
  verdict: Verdict
  ok: boolean
  fault: string | null
  reason: string
  attempts: GateAttempt[]
  attempt_count: number
  endpoint_used: string | null
  gate_overhead_us: number
  total_ms: number
  idempotency_key: string | null
  healed: boolean
}

export interface StepView {
  id: string
  app: string
  tool: string
  title: string
  status: StepStatus
  note: string
  duration_ms: number
  output: unknown
  gate: GateOutcome | null
}

export interface Metrics {
  total_calls: number
  clean_calls: number
  self_healed: number
  deduped: number
  degraded: number
  blocked: number
  compensated: number
  total_attempts: number
  faults_absorbed: number
  faults_by_type: Record<string, number>
  drift_events: number
  reliability_score: number
  gate_latency: { p50_us: number; p95_us: number; p99_us: number; max_us: number; mean_us: number }
}

export interface RouteHealth {
  url: string
  score: number
  successes: number
  failures: number
  latency_ms: number
  breaker: { state: 'CLOSED' | 'OPEN' | 'HALF_OPEN'; failures: number; trip_count: number }
}

export interface Attestation {
  run_id: string
  entry_count: number
  entry_kinds: Record<string, number>
  head_digest: string
  merkle_root: string
  chain_valid: boolean
  chain_reason: string
  signature: string | null
  signed: boolean
  outcome?: string
  duration_s: number
}

export interface Compensation {
  undid: string
  tool: string
  ok: boolean
  verdict: Verdict
  reason: string
}

export interface RunResult {
  run_id: string
  instruction: string
  ok: boolean
  summary: string
  duration_ms: number
  steps: StepView[]
  compensations: Compensation[]
  gate: {
    metrics: Metrics
    routes: Record<string, RouteHealth[]>
    chaos: Record<string, unknown>
    chaos_injected: Record<string, number>
    idempotency_entries: number
    idempotency_hits: number
  }
  attestation: Attestation
}

export interface TriadrEvent {
  event: string
  run_id?: string
  ts?: number
  [key: string]: unknown
}

export interface AuditEntry {
  index: number
  ts: number
  kind: string
  app: string | null
  tool: string | null
  payload: Record<string, unknown>
  prev_hash: string
  digest: string
}
