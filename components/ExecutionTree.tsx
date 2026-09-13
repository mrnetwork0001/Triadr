'use client'

import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ChevronRight, CornerDownRight, RotateCcw, ShieldCheck, Zap } from 'lucide-react'
import type { Compensation, GateAttempt, StepView } from '@/lib/types'
import { APP_META, statusStyle } from './primitives'

function AttemptRow({ attempt, widest }: { attempt: GateAttempt; widest: number }) {
  const width = Math.max(3, (attempt.duration_ms / Math.max(widest, 1)) * 100)
  return (
    <li className="flex min-w-[340px] items-center gap-2.5 py-1">
      <span className="w-4 shrink-0 text-right font-mono text-[10px] text-slate-600">{attempt.index}</span>
      <span
        className={`h-1.5 w-1.5 shrink-0 rounded-full ${attempt.ok ? 'bg-signal-ok' : 'bg-signal-fail'}`}
      />
      <code className="w-40 shrink-0 truncate font-mono text-[10px] text-slate-500">
        {attempt.endpoint.replace(/^(https?|mcp):\/\//, '')}
      </code>
      <div className="h-1 min-w-0 flex-1 overflow-hidden rounded-full bg-white/[0.05]">
        <div
          className={`h-full rounded-full ${attempt.ok ? 'bg-signal-ok/70' : 'bg-signal-fail/60'}`}
          style={{ width: `${width}%` }}
        />
      </div>
      {attempt.fault && (
        <span className="shrink-0 rounded border border-signal-fail/25 bg-signal-fail/10 px-1.5 py-px font-mono text-[9px] uppercase text-signal-fail">
          {attempt.fault}
        </span>
      )}
      {attempt.backoff_ms > 0 && (
        <span className="shrink-0 font-mono text-[9px] text-slate-600" title="backoff before the next attempt">
          +{attempt.backoff_ms.toFixed(0)}ms
        </span>
      )}
      <span className="w-12 shrink-0 text-right font-mono text-[10px] tabular-nums text-slate-500">
        {attempt.duration_ms.toFixed(0)}ms
      </span>
    </li>
  )
}

function StepRow({
  step,
  index,
  slowest,
  compensation,
}: {
  step: StepView
  index: number
  slowest: number
  compensation?: Compensation
}) {
  const [open, setOpen] = useState(false)
  const style = statusStyle(step.status)
  const meta = APP_META[step.app] ?? { label: step.app, role: '', accent: '' }
  const attempts = step.gate?.attempts ?? []
  const widest = Math.max(...attempts.map((a) => a.duration_ms), 1)
  const retried = attempts.length > 1
  const bar = Math.max(2, (step.duration_ms / Math.max(slowest, 1)) * 100)

  return (
    <li className="relative pl-6">
      {/* connector spine */}
      <span className="absolute left-[7px] top-0 h-full w-px bg-white/[0.07]" aria-hidden />
      <span
        className={`absolute left-1 top-[15px] h-2.5 w-2.5 rounded-full ring-4 ring-ink-900 ${style.dot} ${
          step.status === 'running' ? 'animate-pulse-dot' : ''
        }`}
        aria-hidden
      />

      <div className="py-1.5">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          disabled={attempts.length === 0}
          className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-white/[0.03] disabled:cursor-default disabled:hover:bg-transparent"
          aria-expanded={open}
        >
          <ChevronRight
            className={`h-3 w-3 shrink-0 text-slate-600 transition-transform ${open ? 'rotate-90' : ''} ${
              attempts.length === 0 ? 'opacity-0' : ''
            }`}
            aria-hidden
          />
          <span className="w-4 shrink-0 font-mono text-[10px] text-slate-600">{index + 1}</span>
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-2">
              <span className="truncate text-[13px] font-medium text-slate-200">{step.title}</span>
              {retried && (
                <span className="shrink-0 rounded border border-signal-heal/25 bg-signal-heal/10 px-1.5 py-px font-mono text-[9px] text-signal-heal">
                  {attempts.length}×
                </span>
              )}
            </span>
            <span className="mt-0.5 flex items-center gap-2 font-mono text-[10px] text-slate-600">
              <span className={meta.accent}>{meta.label}</span>
              <span className="truncate">{step.tool}</span>
            </span>
          </span>
          <span className={`chip shrink-0 ${style.border} ${style.bg} ${style.text}`}>{style.label}</span>
          <span className="w-14 shrink-0 text-right font-mono text-[11px] tabular-nums text-slate-500">
            {step.duration_ms > 0 ? `${step.duration_ms.toFixed(0)}ms` : '-'}
          </span>
        </button>

        {/* duration waterfall */}
        <div className="ml-[26px] mr-2 h-0.5 overflow-hidden rounded-full bg-white/[0.04]">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${bar}%` }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
            className={`h-full rounded-full ${style.dot} opacity-50`}
          />
        </div>

        <AnimatePresence initial={false}>
          {open && attempts.length > 0 && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="ml-[26px] mt-2 overflow-x-auto rounded-lg border border-white/[0.06] bg-black/25 px-3 py-2">
                <p className="mb-1.5 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500">
                  <Zap className="h-3 w-3" aria-hidden /> gate attempts
                </p>
                <ul>
                  {attempts.map((attempt) => (
                    <AttemptRow key={attempt.index} attempt={attempt} widest={widest} />
                  ))}
                </ul>
                {step.gate && (
                  <p className="mt-2 border-t border-white/[0.06] pt-2 text-[11px] leading-relaxed text-slate-500">
                    {step.gate.reason}
                  </p>
                )}
                {step.gate?.idempotency_key && (
                  <p className="mt-1.5 flex items-center gap-1.5 font-mono text-[10px] text-slate-600">
                    <ShieldCheck className="h-3 w-3 text-signal-ok" aria-hidden />
                    idempotency-key {step.gate.idempotency_key}
                  </p>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {compensation && (
          <div className="ml-[26px] mt-1.5 flex items-center gap-2 rounded-lg border border-signal-undo/20 bg-signal-undo/[0.06] px-2.5 py-1.5">
            <RotateCcw className="h-3 w-3 shrink-0 text-signal-undo" aria-hidden />
            <span className="text-[11px] text-slate-400">
              rolled back via <code className="font-mono text-signal-undo">{compensation.tool}</code>
            </span>
          </div>
        )}
      </div>
    </li>
  )
}

export function ExecutionTree({
  steps,
  compensations,
}: {
  steps: StepView[]
  compensations: Compensation[]
}) {
  const slowest = Math.max(...steps.map((s) => s.duration_ms), 1)
  const byStep = new Map(compensations.map((c) => [c.undid, c]))

  if (steps.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
        <CornerDownRight className="h-5 w-5 text-slate-700" aria-hidden />
        <p className="text-sm text-slate-500">No run yet.</p>
        <p className="max-w-sm text-xs leading-relaxed text-slate-600">
          Pick a scenario and run the agent. Each step appears here as it executes, with every retry,
          reroute and rollback the gate performed.
        </p>
      </div>
    )
  }

  return (
    <ol className="px-3 py-2">
      {steps.map((step, i) => (
        <StepRow key={step.id} step={step} index={i} slowest={slowest} compensation={byStep.get(step.id)} />
      ))}
    </ol>
  )
}
