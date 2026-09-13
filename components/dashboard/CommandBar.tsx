'use client'

import { AnimatePresence, motion } from 'framer-motion'
import { Loader2, Play, Send, Square } from 'lucide-react'
import type { Scenario } from '@/lib/types'

const SCENARIO_TONE: Record<string, string> = {
  clean: 'bg-signal-ok',
  chaos: 'bg-signal-heal',
  rollback: 'bg-signal-undo',
  rejected: 'bg-signal-fail',
}

/**
 * The one place a run is launched from: instruction, scenario, and the button.
 * Also carries the live hint (press Approve in Telegram) and the last result.
 */
export function CommandBar({
  instruction,
  onInstructionChange,
  scenario,
  onScenarioChange,
  scenarios,
  running,
  starting,
  disabled,
  onRun,
  onStop,
  hint,
  error,
  result,
}: {
  instruction: string
  onInstructionChange: (v: string) => void
  scenario: string
  onScenarioChange: (v: string) => void
  scenarios: Scenario[]
  running: boolean
  starting: boolean
  disabled: boolean
  onRun: () => void
  onStop: () => void
  hint?: string | null
  error?: string | null
  result?: { ok: boolean; summary: string; run_id: string; duration_ms: number } | null
}) {
  const active = scenarios.find((s) => s.id === scenario)

  return (
    <section id="console" className="scroll-mt-24 rounded-2xl border border-white/[0.08] bg-ink-900/70">
      <div className="border-b border-white/[0.06] px-5 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">Instruction</h2>
          <div className="flex flex-wrap gap-1 rounded-lg border border-white/[0.08] bg-black/25 p-1" role="radiogroup" aria-label="Scenario">
            {scenarios.map((s) => {
              const on = s.id === scenario
              return (
                <button
                  key={s.id}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  disabled={running}
                  onClick={() => onScenarioChange(s.id)}
                  title={s.description}
                  className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[12px] transition-colors disabled:opacity-50 ${
                    on ? 'bg-white/[0.08] text-slate-50' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${SCENARIO_TONE[s.id] ?? 'bg-slate-500'}`} aria-hidden />
                  {s.label}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      <div className="px-5 py-4">
        <div className="flex flex-col gap-3 md:flex-row">
          <div className="relative min-w-0 flex-1">
            <Send className="pointer-events-none absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-600" aria-hidden />
            <input
              id="instruction"
              value={instruction}
              onChange={(e) => onInstructionChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !running && !disabled) onRun()
              }}
              placeholder="Audit PR #42 in owner/repo, get sign-off on Telegram, release $2,500 USD from escrow"
              className="w-full rounded-xl border border-white/10 bg-black/30 py-2.5 pl-10 pr-3 font-mono text-[12.5px] text-slate-200 placeholder:text-slate-700 focus:border-signal-live/50 focus:outline-none focus:ring-2 focus:ring-signal-live/20"
            />
          </div>
          {running ? (
            <button
              type="button"
              onClick={onStop}
              className="flex shrink-0 items-center justify-center gap-2 rounded-xl border border-signal-fail/30 bg-signal-fail/10 px-5 py-2.5 text-[13px] font-medium text-signal-fail transition-colors hover:bg-signal-fail/20"
            >
              <Square className="h-3.5 w-3.5" aria-hidden /> Stop
            </button>
          ) : (
            <button
              type="button"
              onClick={onRun}
              disabled={disabled}
              className="flex shrink-0 items-center justify-center gap-2 rounded-xl bg-signal-live px-5 py-2.5 text-[13px] font-semibold text-ink-950 transition-colors hover:bg-sky-300 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {starting ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Play className="h-3.5 w-3.5" aria-hidden />}
              Run agent
            </button>
          )}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-slate-500">
          {active && <span>{active.description}</span>}
        </div>

        <AnimatePresence initial={false}>
          {hint && running && (
            <motion.p
              key="hint"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              className="mt-3 flex items-center gap-2 rounded-lg border border-signal-heal/25 bg-signal-heal/[0.07] px-3 py-2 text-[12.5px] text-signal-heal"
            >
              <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-signal-heal" aria-hidden />
              {hint}
            </motion.p>
          )}
          {error && (
            <motion.p
              key="error"
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="mt-3 rounded-lg border border-signal-fail/25 bg-signal-fail/[0.06] px-3 py-2 text-[12.5px] text-signal-fail"
            >
              {error}
            </motion.p>
          )}
          {result && !running && (
            <motion.div
              key={result.run_id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4 }}
              className={`mt-3 rounded-lg border px-3.5 py-2.5 ${
                result.ok ? 'border-signal-ok/25 bg-signal-ok/[0.06]' : 'border-signal-undo/25 bg-signal-undo/[0.06]'
              }`}
            >
              <p className="text-[13px] leading-relaxed text-slate-200">{result.summary}</p>
              <p className="mt-1 font-mono text-[11px] text-slate-500">
                {result.run_id} · {result.duration_ms.toFixed(0)}ms wall clock
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  )
}
