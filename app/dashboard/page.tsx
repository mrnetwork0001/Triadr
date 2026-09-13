'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ListTree, Radio, ScrollText } from 'lucide-react'
import { AppRail } from '@/components/AppRail'
import { AuditChain } from '@/components/AuditChain'
import { EventStream } from '@/components/EventStream'
import { ExecutionTree } from '@/components/ExecutionTree'
import { ReliabilityPanel } from '@/components/ReliabilityPanel'
import { Chip, Panel } from '@/components/primitives'
import { CommandBar } from '@/components/dashboard/CommandBar'
import { KpiStrip } from '@/components/dashboard/KpiStrip'
import { DASHBOARD_SECTIONS, Sidebar, SidebarContent, type SectionId } from '@/components/dashboard/Sidebar'
import { TopBar, type RunState } from '@/components/dashboard/TopBar'
import { fetchApps, fetchAudit, fetchRun, startRun, streamRun } from '@/lib/api'
import type {
  AppStatus, AuditEntry, Compensation, RouteHealth, RunResult, Scenario, StepView, TriadrEvent,
} from '@/lib/types'

const DEFAULT_INSTRUCTION =
  'Audit PR #42 in mrnetwork/triadr, get team sign-off on Telegram, then release $2,500.00 USD from escrow to acct_1TriadrContractor'

const EMPTY_APPS: AppStatus[] = [
  { app: 'github', mode: 'SIMULATED', tools: 0, calls: 0, credentials_required: [], credentials_missing: [], connected: false },
  { app: 'telegram', mode: 'SIMULATED', tools: 0, calls: 0, credentials_required: [], credentials_missing: [], connected: false },
  { app: 'stripe', mode: 'SIMULATED', tools: 0, calls: 0, credentials_required: [], credentials_missing: [], connected: false },
]

export default function Dashboard() {
  const [apps, setApps] = useState<AppStatus[]>(EMPTY_APPS)
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [toolCount, setToolCount] = useState(0)
  const [apiUp, setApiUp] = useState<boolean | null>(null)

  const [instruction, setInstruction] = useState(DEFAULT_INSTRUCTION)
  const [scenario, setScenario] = useState('clean')
  const [starting, setStarting] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [events, setEvents] = useState<TriadrEvent[]>([])
  const [steps, setSteps] = useState<StepView[]>([])
  const [compensations, setCompensations] = useState<Compensation[]>([])
  const [result, setResult] = useState<RunResult | null>(null)
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [auditCount, setAuditCount] = useState(0)
  const [activeApp, setActiveApp] = useState<string | null>(null)
  const [activeId, setActiveId] = useState<SectionId>('console')
  const [menuOpen, setMenuOpen] = useState(false)

  // Escape closes the mobile sheet; growing past the breakpoint discards it.
  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenuOpen(false)
    const onResize = () => window.innerWidth >= 1024 && setMenuOpen(false)
    window.addEventListener('keydown', onKey)
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', onResize)
    }
  }, [menuOpen])

  const unsubscribe = useRef<(() => void) | null>(null)

  // -- app catalogue ------------------------------------------------------
  useEffect(() => {
    let cancelled = false
    fetchApps()
      .then((data) => {
        if (cancelled) return
        setApps(data.apps)
        setScenarios(data.scenarios)
        setToolCount(data.tool_count)
        setApiUp(true)
        if (data.default_instruction) {
          // Only replace the placeholder - never clobber something the user typed.
          setInstruction((current) => (current === DEFAULT_INSTRUCTION ? data.default_instruction! : current))
        }
      })
      .catch(() => !cancelled && setApiUp(false))
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => () => unsubscribe.current?.(), [])

  // -- scroll spy for the sidebar -----------------------------------------
  useEffect(() => {
    let frame = 0
    const onScroll = () => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        let current: SectionId = 'console'
        for (const { id } of DASHBOARD_SECTIONS) {
          const el = document.getElementById(id)
          if (el && el.getBoundingClientRect().top <= 160) current = id
        }
        // At the very bottom the last section may never cross the line - light it anyway.
        const atBottom = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2
        if (atBottom && window.scrollY > 0) current = DASHBOARD_SECTIONS[DASHBOARD_SECTIONS.length - 1].id
        setActiveId(current)
      })
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      cancelAnimationFrame(frame)
    }
  }, [])

  // -- live event reducer -------------------------------------------------
  const apply = useCallback((e: TriadrEvent) => {
    setEvents((prev) => (prev.length > 600 ? [...prev.slice(-500), e] : [...prev, e]))

    switch (e.event) {
      case 'run.start': {
        const plan = e.plan as { steps?: Array<Record<string, unknown>> } | undefined
        if (plan?.steps) {
          setSteps(
            plan.steps.map((s) => ({
              id: String(s.id), app: String(s.app), tool: String(s.tool), title: String(s.title),
              status: 'pending', note: '', duration_ms: 0, output: null, gate: null,
            })),
          )
        }
        break
      }
      case 'step.start':
        setActiveApp(String(e.app ?? '') || null)
        setSteps((prev) => prev.map((s) => (s.id === e.step ? { ...s, status: 'running' } : s)))
        break
      case 'step.done':
        setSteps((prev) =>
          prev.map((s) =>
            s.id === e.step
              ? { ...s, status: (e.status as StepView['status']) ?? 'succeeded', duration_ms: Number(e.duration_ms ?? 0) }
              : s,
          ),
        )
        break
      case 'step.failed':
        setSteps((prev) =>
          prev.map((s) => (s.id === e.step ? { ...s, status: 'failed', note: String(e.reason ?? '') } : s)),
        )
        break
      case 'step.skipped':
        setSteps((prev) =>
          prev.map((s) => (s.id === e.step ? { ...s, status: 'skipped', note: String(e.reason ?? '') } : s)),
        )
        break
      case 'saga.compensated':
        setSteps((prev) => prev.map((s) => (s.id === e.undid ? { ...s, status: 'compensated' } : s)))
        setCompensations((prev) => [
          ...prev,
          { undid: String(e.undid), tool: String(e.tool), ok: Boolean(e.ok),
            verdict: e.verdict as Compensation['verdict'], reason: String(e.reason ?? '') },
        ])
        break
      case 'audit.entry':
        setAuditCount((n) => n + 1)
        break
      default:
        break
    }
  }, [])

  // -- run launcher -------------------------------------------------------
  const run = useCallback(async () => {
    setStarting(true)
    setError(null)
    setEvents([])
    setSteps([])
    setCompensations([])
    setResult(null)
    setEntries([])
    setAuditCount(0)
    unsubscribe.current?.()

    try {
      const { run_id } = await startRun({ instruction, scenario })
      setRunning(true)
      setStarting(false)
      unsubscribe.current = streamRun(run_id, apply, async () => {
        setRunning(false)
        setActiveApp(null)
        try {
          const [{ result: final }, audit] = await Promise.all([fetchRun(run_id), fetchAudit(run_id)])
          if (final) {
            setResult(final)
            setSteps(final.steps)
            setCompensations(final.compensations)
          }
          setEntries(audit.entries ?? [])
        } catch {
          /* the live view already holds the run; a failed backfill is not fatal */
        }
      })
    } catch (err) {
      setStarting(false)
      setRunning(false)
      setError(err instanceof Error ? err.message : 'failed to start the run')
    }
  }, [apply, instruction, scenario])

  const stop = useCallback(() => {
    unsubscribe.current?.()
    setRunning(false)
    setActiveApp(null)
  }, [])

  // -- derived view state -------------------------------------------------
  const routes: Record<string, RouteHealth[]> = useMemo(() => result?.gate.routes ?? {}, [result])
  const liveApps = useMemo(
    () => apps.map((a) => ({ ...a, calls: steps.filter((s) => s.app === a.app && s.status !== 'pending').length || a.calls })),
    [apps, steps],
  )
  const runState: RunState = starting ? 'starting' : running ? 'streaming' : error ? 'error'
    : result ? (result.ok ? 'completed' : 'rolled_back') : 'idle'
  const telegramLive = apps.some((a) => a.app === 'telegram' && a.mode === 'LIVE')
  const awaitingHuman = steps.some((s) => s.id === 'approval' && s.status === 'running')
  const hint = telegramLive && running
    ? awaitingHuman
      ? 'The agent is waiting for a human: press Approve on the card in Telegram.'
      : 'An approval card will arrive in Telegram - press Approve when it does.'
    : null

  return (
    <div className="flex min-h-screen">
      <Sidebar apps={liveApps} apiUp={apiUp} toolCount={toolCount} activeId={activeId} running={running} />

      <div className="min-w-0 flex-1">
        <TopBar
          apiUp={apiUp}
          toolCount={toolCount}
          runState={runState}
          runId={result?.run_id ?? null}
          menuOpen={menuOpen}
          onToggleMenu={() => setMenuOpen((v) => !v)}
        />

        <AnimatePresence>
          {menuOpen && (
            <motion.div
              id="dashboard-menu"
              initial={{ opacity: 0, y: -6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.18, ease: 'easeOut' }}
              className="fixed inset-x-0 top-[72px] z-40 flex max-h-[calc(100vh-72px)] flex-col overflow-y-auto border-b border-white/[0.08] bg-ink-950/95 backdrop-blur-md lg:hidden"
            >
              <SidebarContent
                apps={liveApps}
                apiUp={apiUp}
                toolCount={toolCount}
                activeId={activeId}
                running={running}
                onNavigate={() => setMenuOpen(false)}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {apiUp === false && (
          <div className="mx-4 mt-4 rounded-xl border border-signal-fail/25 bg-signal-fail/[0.06] px-4 py-3 text-[13px] text-slate-300 sm:mx-6">
            The control plane is not reachable. Start it with{' '}
            <code className="font-mono text-signal-fail">uvicorn server:app --port 8000</code>, then reload.
          </div>
        )}

        <main className="mx-auto w-full max-w-[1320px] space-y-4 px-4 py-5 sm:px-6">
          <CommandBar
            instruction={instruction}
            onInstructionChange={setInstruction}
            scenario={scenario}
            onScenarioChange={setScenario}
            scenarios={scenarios}
            running={running}
            starting={starting}
            disabled={starting || apiUp === false}
            onRun={run}
            onStop={stop}
            hint={hint}
            error={error}
            result={result ? { ok: result.ok, summary: result.summary, run_id: result.run_id, duration_ms: result.duration_ms } : null}
          />

          <KpiStrip metrics={result?.gate.metrics ?? null} running={running} />

          <AppRail apps={liveApps} routes={routes} activeApp={activeApp} />

          <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <div id="execution" className="min-w-0 scroll-mt-24">
              <Panel
                title="Execution tree"
                right={
                  running ? (
                    <Chip tone="live">
                      <Radio className="h-2.5 w-2.5 animate-pulse-dot" aria-hidden /> streaming
                    </Chip>
                  ) : (
                    <span className="flex items-center gap-1.5 text-[10px] text-slate-600">
                      <ListTree className="h-3 w-3" aria-hidden /> {steps.length} steps
                    </span>
                  )
                }
              >
                <ExecutionTree steps={steps} compensations={compensations} />
              </Panel>
            </div>
            <div id="reliability" className="min-w-0 scroll-mt-24">
              <Panel title="Reliability">
                <ReliabilityPanel metrics={result?.gate.metrics ?? null} />
              </Panel>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <div id="events" className="min-w-0 scroll-mt-24">
              <Panel
                title="Gate event stream"
                right={
                  <span className="flex items-center gap-1.5 text-[10px] text-slate-600">
                    <ScrollText className="h-3 w-3" aria-hidden /> {events.length} events
                  </span>
                }
              >
                <EventStream events={events} />
              </Panel>
            </div>
            <div id="audit" className="min-w-0 scroll-mt-24">
              <Panel title="Cryptographic audit log">
                <AuditChain attestation={result?.attestation ?? null} entries={entries} liveCount={auditCount} />
              </Panel>
            </div>
          </div>

          <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] pt-4 text-[11px] text-slate-600">
            <span>Triadr - GitHub · Telegram · Stripe, behind one self-healing reliability gate.</span>
            <span className="font-mono">Apache 2.0</span>
          </footer>
        </main>
      </div>
    </div>
  )
}
