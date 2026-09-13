'use client'

import type { ReactNode } from 'react'

export const STATUS_STYLE: Record<
  string,
  { dot: string; text: string; border: string; bg: string; label: string }
> = {
  succeeded: { dot: 'bg-signal-ok', text: 'text-signal-ok', border: 'border-signal-ok/30', bg: 'bg-signal-ok/10', label: 'applied' },
  healed: { dot: 'bg-signal-heal', text: 'text-signal-heal', border: 'border-signal-heal/30', bg: 'bg-signal-heal/10', label: 'self-healed' },
  failed: { dot: 'bg-signal-fail', text: 'text-signal-fail', border: 'border-signal-fail/30', bg: 'bg-signal-fail/10', label: 'failed' },
  compensated: { dot: 'bg-signal-undo', text: 'text-signal-undo', border: 'border-signal-undo/30', bg: 'bg-signal-undo/10', label: 'rolled back' },
  running: { dot: 'bg-signal-live', text: 'text-signal-live', border: 'border-signal-live/30', bg: 'bg-signal-live/10', label: 'running' },
  skipped: { dot: 'bg-slate-600', text: 'text-slate-500', border: 'border-white/10', bg: 'bg-white/[0.03]', label: 'skipped' },
  pending: { dot: 'bg-slate-700', text: 'text-slate-500', border: 'border-white/10', bg: 'bg-white/[0.02]', label: 'queued' },
}

export function statusStyle(status: string) {
  return STATUS_STYLE[status] ?? STATUS_STYLE.pending
}

export function Panel({
  title,
  right,
  children,
  className = '',
}: {
  title: string
  right?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`panel min-w-0 ${className}`}>
      <header className="panel-head">
        <h2 className="panel-title">{title}</h2>
        {right}
      </header>
      {children}
    </section>
  )
}

export function Chip({
  tone = 'idle',
  children,
}: {
  tone?: 'ok' | 'heal' | 'fail' | 'undo' | 'live' | 'idle'
  children: ReactNode
}) {
  const tones: Record<string, string> = {
    ok: 'border-signal-ok/30 bg-signal-ok/10 text-signal-ok',
    heal: 'border-signal-heal/30 bg-signal-heal/10 text-signal-heal',
    fail: 'border-signal-fail/30 bg-signal-fail/10 text-signal-fail',
    undo: 'border-signal-undo/30 bg-signal-undo/10 text-signal-undo',
    live: 'border-signal-live/30 bg-signal-live/10 text-signal-live',
    idle: 'border-white/10 bg-white/[0.04] text-slate-400',
  }
  return <span className={`chip ${tones[tone]}`}>{children}</span>
}

export function Stat({
  label,
  value,
  hint,
  tone = 'text-slate-50',
}: {
  label: string
  value: ReactNode
  hint?: string
  tone?: string
}) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2.5">
      <div className={`font-mono text-xl font-semibold tabular-nums ${tone}`}>{value}</div>
      <div className="stat-label mt-0.5">{label}</div>
      {hint && <div className="mt-1 text-[10px] leading-tight text-slate-600">{hint}</div>}
    </div>
  )
}

/** Monospace hash with a middle ellipsis, so digests stay scannable at any width. */
export function Hash({ value, chars = 8 }: { value: string; chars?: number }) {
  if (!value) return <span className="font-mono text-slate-600">-</span>
  const short = value.length > chars * 2 ? `${value.slice(0, chars)}…${value.slice(-chars)}` : value
  return (
    <code title={value} className="font-mono text-[11px] text-slate-500">
      {short}
    </code>
  )
}

export const APP_META: Record<string, { label: string; role: string; accent: string }> = {
  github: { label: 'GitHub', role: 'Code audit', accent: 'text-slate-200' },
  telegram: { label: 'Telegram', role: 'Team approval', accent: 'text-signal-undo' },
  stripe: { label: 'Stripe', role: 'Escrow payout', accent: 'text-signal-live' },
}
