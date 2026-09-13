'use client'

import { Activity, Gauge, ShieldCheck, Timer } from 'lucide-react'
import { CountUp } from '@/components/landing/motion'
import type { Metrics } from '@/lib/types'

/** Four headline numbers from the most recent run, measured by the gate. */
export function KpiStrip({ metrics, running }: { metrics: Metrics | null; running: boolean }) {
  const tiles = [
    {
      label: 'Reliability score',
      icon: ShieldCheck,
      value: metrics ? Math.round(metrics.reliability_score * 100) : null,
      suffix: '%',
      tone: metrics && metrics.compensated > 0 ? 'text-signal-heal' : 'text-signal-ok',
      hint: metrics ? `${metrics.total_calls} guarded calls · ${metrics.total_attempts} attempts` : 'run the agent to measure',
    },
    {
      label: 'Faults absorbed',
      icon: Activity,
      value: metrics ? metrics.faults_absorbed : null,
      suffix: '',
      tone: 'text-signal-heal',
      hint: metrics ? Object.entries(metrics.faults_by_type).map(([k, v]) => `${k.toLowerCase()} ×${v}`).slice(0, 2).join(' · ') || 'none injected' : '',
    },
    {
      label: 'Steps self-healed',
      icon: Gauge,
      value: metrics ? metrics.self_healed : null,
      suffix: '',
      tone: 'text-slate-50',
      hint: metrics ? `${metrics.deduped} deduped · ${metrics.compensated} unrecoverable` : '',
    },
    {
      label: 'Gate overhead p50',
      icon: Timer,
      value: metrics ? Number(metrics.gate_latency.p50_us.toFixed(1)) : null,
      suffix: ' µs',
      tone: 'text-signal-live',
      hint: metrics ? `p99 ${metrics.gate_latency.p99_us.toFixed(1)} µs · measured, not asserted` : '',
    },
  ]

  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
      {tiles.map((t) => (
        <div
          key={t.label}
          className={`card-lift min-w-0 rounded-2xl border border-white/[0.07] bg-ink-900/70 px-5 py-4 ${
            running && !metrics ? 'animate-pulse-dot' : ''
          }`}
        >
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-slate-500">
            <t.icon className="h-3.5 w-3.5" aria-hidden />
            {t.label}
          </div>
          <div className={`mt-2 font-mono text-[28px] font-semibold tabular-nums leading-none ${t.value === null ? 'text-slate-700' : t.tone}`}>
            {t.value === null ? '—' : t.suffix === ' µs' ? `${t.value}${t.suffix}` : <CountUp value={t.value} suffix={t.suffix} duration={1} />}
          </div>
          <div className="mt-2 truncate text-[11px] text-slate-600">{t.hint}</div>
        </div>
      ))}
    </div>
  )
}
