'use client'

import { useEffect, useRef } from 'react'
import type { TriadrEvent } from '@/lib/types'

const TONE: Record<string, string> = {
  'gate.fault': 'text-signal-fail',
  'gate.circuit_open': 'text-signal-fail',
  'gate.drift': 'text-signal-fail',
  'gate.backoff': 'text-signal-heal',
  'gate.throttled': 'text-signal-heal',
  'gate.drift_injected': 'text-signal-heal',
  'gate.ok': 'text-signal-ok',
  'gate.deduped': 'text-signal-ok',
  'step.done': 'text-signal-ok',
  'gate.compensate': 'text-signal-undo',
  'saga.compensated': 'text-signal-undo',
  'saga.rollback.start': 'text-signal-undo',
  'step.failed': 'text-signal-fail',
  'step.start': 'text-signal-live',
  'run.start': 'text-signal-live',
  'run.end': 'text-slate-300',
}

/** One-line human summary per event - the ticker should read, not just scroll. */
function describe(e: TriadrEvent): string {
  const s = (k: string) => (e[k] === undefined || e[k] === null ? '' : String(e[k]))
  switch (e.event) {
    case 'run.start': return `run started - ${s('instruction').slice(0, 72)}`
    case 'run.end': return `run finished - ${s('summary').slice(0, 90)}`
    case 'step.start': return `${s('tool')} → ${s('title')}`
    case 'step.done': return `${s('step')} ${s('status')} in ${Number(e.duration_ms ?? 0).toFixed(0)}ms`
    case 'step.failed': return `${s('step')} failed - ${s('fault') || s('verdict')}`
    case 'step.skipped': return `${s('step')} skipped - ${s('reason')}`
    case 'gate.fault': return `${s('fault')} on ${s('endpoint')} (attempt ${s('attempt')})${e.injected ? ' [injected]' : ''}`
    case 'gate.backoff': return `backing off ${Number(e.delay_ms ?? 0).toFixed(0)}ms before attempt ${Number(e.attempt ?? 0) + 1}`
    case 'gate.ok': return `${s('tool')} succeeded via ${s('endpoint')} after ${s('attempts')} attempt(s)`
    case 'gate.circuit_open': return `circuit open - skipped ${s('endpoint')} with no round trip`
    case 'gate.deduped': return `idempotency hit on ${s('key')} - no duplicate side effect`
    case 'gate.blocked': return `blocked pre-flight - ${s('violations')}`
    case 'gate.throttled': return `token bucket shaped the call, waited ${s('wait_ms')}ms`
    case 'gate.drift': return `response contract drifted on ${s('tool')} - rerouting`
    case 'gate.drift_injected': return `chaos mutated the ${s('tool')} response shape`
    case 'gate.compensate': return `${s('tool')} unrecoverable - requesting saga rollback`
    case 'saga.rollback.start': return `rolling back: ${(e.steps as string[] | undefined)?.join(', ') ?? ''}`
    case 'saga.compensated': return `undid ${s('undid')} via ${s('tool')}`
    case 'audit.entry': return `#${s('index')} ${s('kind')} → ${s('digest')}`
    default: return e.event
  }
}

export function EventStream({ events }: { events: TriadrEvent[] }) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'nearest' })
  }, [events.length])

  if (events.length === 0) {
    return (
      <p className="px-4 py-8 text-center text-xs text-slate-600">
        Gate decisions stream here in real time as the agent runs.
      </p>
    )
  }

  return (
    <div className="h-[264px] overflow-auto px-3 py-2 font-mono text-[11px] leading-relaxed">
      {events.map((e, i) => (
        <div key={i} className="flex gap-2 py-px">
          <span className="w-14 shrink-0 text-slate-700">
            {e.ts ? new Date(Number(e.ts) * 1000).toLocaleTimeString('en-GB', { hour12: false }) : '-'}
          </span>
          <span className={`w-[132px] shrink-0 truncate ${TONE[e.event] ?? 'text-slate-500'}`}>{e.event}</span>
          <span className="min-w-0 flex-1 truncate text-slate-500" title={describe(e)}>
            {describe(e)}
          </span>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  )
}
