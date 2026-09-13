'use client'

import { Activity, Gauge, ShieldCheck, Timer } from 'lucide-react'
import type { Metrics } from '@/lib/types'
import { Stat } from './primitives'

function ScoreRing({ score, ok }: { score: number; ok: boolean }) {
  const radius = 34
  const circumference = 2 * Math.PI * radius
  const pct = Math.max(0, Math.min(1, score))
  const stroke = ok ? '#34d399' : '#fbbf24'

  return (
    <div className="relative grid h-[92px] w-[92px] shrink-0 place-items-center">
      <svg viewBox="0 0 80 80" className="h-full w-full -rotate-90">
        <circle cx="40" cy="40" r={radius} fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="7" />
        <circle
          cx="40"
          cy="40"
          r={radius}
          fill="none"
          stroke={stroke}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - pct)}
          style={{ transition: 'stroke-dashoffset 700ms ease-out' }}
        />
      </svg>
      <div className="absolute text-center">
        <div className="font-mono text-lg font-semibold tabular-nums text-slate-50">
          {(pct * 100).toFixed(0)}
          <span className="text-xs text-slate-500">%</span>
        </div>
        <div className="text-[9px] uppercase tracking-wider text-slate-600">reliable</div>
      </div>
    </div>
  )
}

/**
 * Every number here is measured by the gate at runtime, including the latency
 * percentiles - nothing on this panel is a hardcoded claim.
 */
export function ReliabilityPanel({ metrics }: { metrics: Metrics | null }) {
  const m: Metrics = metrics ?? {
    total_calls: 0, clean_calls: 0, self_healed: 0, deduped: 0, degraded: 0, blocked: 0,
    compensated: 0, total_attempts: 0, faults_absorbed: 0, faults_by_type: {}, drift_events: 0,
    reliability_score: 1, gate_latency: { p50_us: 0, p95_us: 0, p99_us: 0, max_us: 0, mean_us: 0 },
  }
  const faults = Object.entries(m.faults_by_type).sort((a, b) => b[1] - a[1])
  const maxFault = Math.max(...faults.map(([, n]) => n), 1)

  return (
    <div className="space-y-3 px-4 py-3.5">
      <div className="flex items-center gap-4">
        <ScoreRing score={m.reliability_score} ok={m.compensated === 0} />
        <div className="min-w-0 flex-1 space-y-1.5">
          <p className="text-[11px] leading-relaxed text-slate-400">
            <span className="font-mono text-slate-200">{m.total_calls}</span> guarded calls over{' '}
            <span className="font-mono text-slate-200">{m.total_attempts}</span> physical attempts.
          </p>
          <p className="text-[11px] leading-relaxed text-slate-500">
            <span className="font-mono text-signal-heal">{m.self_healed}</span> self-healed ·{' '}
            <span className="font-mono text-signal-ok">{m.deduped}</span> deduped ·{' '}
            <span className="font-mono text-signal-fail">{m.compensated}</span> unrecoverable
          </p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Stat
          label="faults absorbed"
          value={m.faults_absorbed}
          tone={m.faults_absorbed > 0 ? 'text-signal-heal' : 'text-slate-50'}
        />
        <Stat label="gate p50" value={`${m.gate_latency.p50_us.toFixed(1)}µs`} />
        <Stat label="gate p99" value={`${m.gate_latency.p99_us.toFixed(1)}µs`} />
      </div>

      {faults.length > 0 && (
        <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
          <p className="mb-2 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500">
            <Activity className="h-3 w-3" aria-hidden /> faults absorbed by type
          </p>
          <ul className="space-y-1.5">
            {faults.map(([name, count]) => (
              <li key={name} className="flex items-center gap-2">
                <code className="w-[136px] shrink-0 font-mono text-[10px] text-slate-500">{name}</code>
                <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-white/[0.05]">
                  <div
                    className="h-full rounded-full bg-signal-heal/60 transition-all duration-500"
                    style={{ width: `${(count / maxFault) * 100}%` }}
                  />
                </div>
                <span className="w-5 shrink-0 text-right font-mono text-[10px] tabular-nums text-slate-400">
                  {count}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <dl className="space-y-1 rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5 text-[11px]">
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-slate-500">
            <ShieldCheck className="h-3 w-3" aria-hidden /> blocked pre-flight
          </dt>
          <dd className="font-mono tabular-nums text-slate-300">{m.blocked}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-slate-500">
            <Gauge className="h-3 w-3" aria-hidden /> contract drift caught
          </dt>
          <dd className="font-mono tabular-nums text-slate-300">{m.drift_events}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-slate-500">
            <Timer className="h-3 w-3" aria-hidden /> degraded fallbacks
          </dt>
          <dd className="font-mono tabular-nums text-slate-300">{m.degraded}</dd>
        </div>
      </dl>
    </div>
  )
}
