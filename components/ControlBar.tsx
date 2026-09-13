'use client'

import { Loader2, Play, Square } from 'lucide-react'
import type { Scenario } from '@/lib/types'

const TONE: Record<string, string> = {
  clean: 'data-[on=true]:border-signal-ok/40 data-[on=true]:bg-signal-ok/10 data-[on=true]:text-signal-ok',
  chaos: 'data-[on=true]:border-signal-heal/40 data-[on=true]:bg-signal-heal/10 data-[on=true]:text-signal-heal',
  rollback: 'data-[on=true]:border-signal-undo/40 data-[on=true]:bg-signal-undo/10 data-[on=true]:text-signal-undo',
  rejected: 'data-[on=true]:border-signal-fail/40 data-[on=true]:bg-signal-fail/10 data-[on=true]:text-signal-fail',
}

export function ControlBar({
  instruction,
  onInstructionChange,
  scenario,
  onScenarioChange,
  scenarios,
  running,
  onRun,
  onStop,
  disabled,
}: {
  instruction: string
  onInstructionChange: (value: string) => void
  scenario: string
  onScenarioChange: (value: string) => void
  scenarios: Scenario[]
  running: boolean
  onRun: () => void
  onStop: () => void
  disabled: boolean
}) {
  const active = scenarios.find((s) => s.id === scenario)

  return (
    <div className="panel px-4 py-3.5">
      <label htmlFor="instruction" className="stat-label">
        Natural-language instruction
      </label>
      <div className="mt-2 flex flex-col gap-2.5 sm:flex-row">
        <input
          id="instruction"
          value={instruction}
          onChange={(e) => onInstructionChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !running && !disabled) onRun()
          }}
          placeholder="Audit PR #42 in owner/repo, approve in #eng-approvals, pay acct_… $2,500 USD"
          className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-[12px] text-slate-200 placeholder:text-slate-700 focus:border-signal-live/50 focus:outline-none focus:ring-1 focus:ring-signal-live/30"
        />
        {running ? (
          <button
            type="button"
            onClick={onStop}
            className="flex shrink-0 items-center justify-center gap-2 rounded-lg border border-signal-fail/30 bg-signal-fail/10 px-4 py-2 text-[13px] font-medium text-signal-fail transition-colors hover:bg-signal-fail/20"
          >
            <Square className="h-3.5 w-3.5" aria-hidden /> Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={onRun}
            disabled={disabled}
            className="flex shrink-0 items-center justify-center gap-2 rounded-lg border border-signal-live/30 bg-signal-live/10 px-4 py-2 text-[13px] font-medium text-signal-live transition-colors hover:bg-signal-live/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {disabled ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Play className="h-3.5 w-3.5" aria-hidden />}
            Run agent
          </button>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {scenarios.map((s) => (
          <button
            key={s.id}
            type="button"
            data-on={scenario === s.id}
            onClick={() => onScenarioChange(s.id)}
            disabled={running}
            title={s.description}
            className={`rounded-md border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[11px] text-slate-400 transition-colors hover:bg-white/[0.06] disabled:opacity-50 ${TONE[s.id] ?? ''}`}
          >
            {s.label}
          </button>
        ))}
      </div>
      {active && <p className="mt-2 text-[11px] leading-relaxed text-slate-500">{active.description}</p>}
    </div>
  )
}
