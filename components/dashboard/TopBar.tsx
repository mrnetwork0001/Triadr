'use client'

import Link from 'next/link'
import { CircleDot, GitBranch, Menu, Radio, X } from 'lucide-react'
import { BrandHeader } from '@/components/BrandHeader'
import { Chip } from '@/components/primitives'

export type RunState = 'idle' | 'starting' | 'streaming' | 'completed' | 'rolled_back' | 'error'

const RUN_STATE: Record<RunState, { label: string; tone: 'idle' | 'live' | 'ok' | 'undo' | 'fail' }> = {
  idle: { label: 'idle', tone: 'idle' },
  starting: { label: 'starting', tone: 'live' },
  streaming: { label: 'streaming', tone: 'live' },
  completed: { label: 'applied', tone: 'ok' },
  rolled_back: { label: 'rolled back', tone: 'undo' },
  error: { label: 'error', tone: 'fail' },
}

/** Page header: title on the left, live status on the right. Shows the brand on small screens where the sidebar is hidden. */
export function TopBar({
  apiUp,
  toolCount,
  runState,
  runId,
  menuOpen = false,
  onToggleMenu,
}: {
  apiUp: boolean | null
  toolCount: number
  runState: RunState
  runId?: string | null
  menuOpen?: boolean
  onToggleMenu?: () => void
}) {
  const state = RUN_STATE[runState]
  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.07] bg-ink-950/80 backdrop-blur-md">
      <div className="flex h-[72px] items-center gap-4 px-4 sm:px-6">
        <Link href="/" aria-label="Triadr home" className="flex items-center lg:hidden">
          <BrandHeader height={36} />
        </Link>
        <div className="hidden min-w-0 lg:block">
          <h1 className="text-[15px] font-semibold tracking-tight text-slate-50">Run console</h1>
          <p className="text-[12px] text-slate-500">One instruction, six gate-supervised steps across three apps.</p>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Chip tone={state.tone}>
            {runState === 'streaming' ? <Radio className="h-2.5 w-2.5 animate-pulse-dot" aria-hidden /> : <CircleDot className="h-2.5 w-2.5" aria-hidden />}
            {state.label}
          </Chip>
          {runId && <span className="hidden font-mono text-[11px] text-slate-600 md:inline">{runId}</span>}
          <span className="hidden sm:contents">
            <Chip tone={apiUp === false ? 'fail' : apiUp ? 'ok' : 'idle'}>
              <CircleDot className="h-2.5 w-2.5" aria-hidden />
              {apiUp === false ? 'api offline' : apiUp ? 'api online' : 'connecting'}
            </Chip>
            <Chip tone="idle">
              <GitBranch className="h-2.5 w-2.5" aria-hidden />
              {toolCount} tools
            </Chip>
          </span>
          {onToggleMenu && (
            <button
              type="button"
              onClick={onToggleMenu}
              aria-expanded={menuOpen}
              aria-controls="dashboard-menu"
              aria-label={menuOpen ? 'Close menu' : 'Open menu'}
              className="grid h-10 w-10 place-items-center rounded-lg border border-white/10 bg-white/[0.03] text-slate-200 transition-colors hover:bg-white/[0.07] lg:hidden"
            >
              {menuOpen ? <X className="h-4 w-4" aria-hidden /> : <Menu className="h-5 w-5" aria-hidden />}
            </button>
          )}
        </div>
      </div>
    </header>
  )
}
