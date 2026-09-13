import type { AppsResponse, RunResult, TriadrEvent } from './types'

/** All browser traffic goes through the Next rewrite, so there is one origin. */
export async function fetchApps(): Promise<AppsResponse> {
  const res = await fetch('/api/apps', { cache: 'no-store' })
  if (!res.ok) throw new Error(`apps: HTTP ${res.status}`)
  return res.json()
}

export async function fetchTools() {
  const res = await fetch('/api/tools', { cache: 'no-store' })
  if (!res.ok) throw new Error(`tools: HTTP ${res.status}`)
  return res.json()
}

export async function startRun(body: {
  instruction: string
  scenario: string
}): Promise<{ run_id: string; stream: string }> {
  const res = await fetch('/api/run', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`run: HTTP ${res.status}`)
  return res.json()
}

export async function fetchRun(runId: string): Promise<{ result: RunResult | null }> {
  const res = await fetch(`/api/runs/${runId}`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`run: HTTP ${res.status}`)
  return res.json()
}

export async function fetchAudit(runId: string) {
  const res = await fetch(`/api/runs/${runId}/audit`, { cache: 'no-store' })
  if (!res.ok) throw new Error(`audit: HTTP ${res.status}`)
  return res.json()
}

/**
 * Subscribe to a run's Server-Sent Events. Returns an unsubscribe function.
 * EventSource dispatches by event name, so every Triadr event type is bound
 * explicitly rather than relying on the default `message` channel.
 */
export function streamRun(
  runId: string,
  onEvent: (event: TriadrEvent) => void,
  onClose?: () => void,
): () => void {
  const source = new EventSource(`/api/runs/${runId}/stream`)
  const names = [
    'hello', 'run.queued', 'run.start', 'run.end', 'run.error',
    'step.start', 'step.done', 'step.failed', 'step.skipped',
    'gate.ok', 'gate.fault', 'gate.backoff', 'gate.blocked', 'gate.deduped',
    'gate.degraded', 'gate.compensate', 'gate.circuit_open', 'gate.throttled',
    'gate.drift', 'gate.drift_injected', 'saga.rollback.start', 'saga.compensated',
    'audit.entry', 'stream.close',
  ]

  const handler = (e: MessageEvent) => {
    try {
      const parsed = JSON.parse(e.data) as TriadrEvent
      onEvent({ ...parsed, event: parsed.event ?? e.type })
    } catch {
      /* keep-alive comments and malformed frames are ignored */
    }
    if (e.type === 'stream.close') {
      source.close()
      onClose?.()
    }
  }

  names.forEach((name) => source.addEventListener(name, handler as EventListener))
  source.onerror = () => {
    source.close()
    onClose?.()
  }
  return () => source.close()
}
