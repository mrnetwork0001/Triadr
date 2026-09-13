'use client'

import Link from 'next/link'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, CircleDot, GitBranch, ListTree, Radio, ScrollText } from 'lucide-react'
import { TriadrMark } from '@/components/TriadrMark'
import { AppRail } from '@/components/AppRail'
import { AuditChain } from '@/components/AuditChain'
import { ControlBar } from '@/components/ControlBar'
import { EventStream } from '@/components/EventStream'
import { ExecutionTree } from '@/components/ExecutionTree'
import { ReliabilityPanel } from '@/components/ReliabilityPanel'
import { Chip, Panel } from '@/components/primitives'
import { fetchApps, fetchAudit, fetchRun, startRun, streamRun } from '@/lib/api'
import type {
  AppStatus, AuditEntry, Compensation, RouteHealth, RunResult, Scenario, StepView, TriadrEvent,
} from '@/lib/types'

const DEFAULT_INSTRUCTION =
  'Audit PR #42 in mrnetwork/triadr, get team sign-off in #eng-approvals, then release $2,500.00 USD from escrow to acct_1TriadrContractor'

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

  const routes: Record<string, RouteHealth[]> = useMemo(() => result?.gate.routes ?? {}, [result])
  const liveApps = useMemo(
    () => apps.map((a) => ({ ...a, calls: steps.filter((s) => s.app === a.app && s.status !== 'pending').length || a.calls })),
    [apps, steps],
  )

  return (
    <main className="mx-auto min-h-screen w-full max-w-[1400px] px-4 py-6 sm:px-6">
      <header className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <Link
              href="/"
              className="flex items-center gap-2.5 rounded-md transition-opacity hover:opacity-80 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-live/50"
            >
              <TriadrMark size={32} />
              <h1 className="text-xl font-semibold tracking-tight text-slate-50">Triadr</h1>
            </Link>
            <Chip tone="live">reliability engine</Chip>
          </div>
          <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-slate-500">
            One multi-step agent across three external apps, behind a gate that retries, reroutes,
            deduplicates and rolls back - so a workflow is never left half-executed.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/"
            className="flex items-center gap-1.5 rounded-md border border-white/10 bg-white/[0.03] px-2.5 py-1 text-[11px] text-slate-400 transition-colors hover:bg-white/[0.07] hover:text-slate-200"
          >
            <ArrowLeft className="h-3 w-3" aria-hidden />
            Overview
          </Link>
          <Chip tone={apiUp === false ? 'fail' : apiUp ? 'ok' : 'idle'}>
            <CircleDot className="h-2.5 w-2.5" aria-hidden />
            {apiUp === false ? 'api offline' : apiUp ? 'api connected' : 'connecting'}
          </Chip>
          <Chip tone="idle">
            <GitBranch className="h-2.5 w-2.5" aria-hidden />
            {toolCount} mcp tools
          </Chip>
        </div>
      </header>

      {apiUp === false && (
        <div className="mb-4 rounded-lg border border-signal-fail/25 bg-signal-fail/[0.06] px-4 py-3 text-[13px] text-slate-300">
          The control plane is not reachable. Start it with{' '}
          <code className="font-mono text-signal-fail">uvicorn server:app --port 8000</code>, then reload.
        </div>
      )}

      <div className="space-y-4">
        <AppRail apps={liveApps} routes={routes} activeApp={activeApp} />

        <ControlBar
          instruction={instruction}
          onInstructionChange={setInstruction}
          scenario={scenario}
          onScenarioChange={setScenario}
          scenarios={scenarios}
          running={running}
          onRun={run}
          onStop={stop}
          disabled={starting || apiUp === false}
        />

        {error && (
          <p className="rounded-lg border border-signal-fail/25 bg-signal-fail/[0.06] px-4 py-2.5 text-[13px] text-signal-fail">
            {error}
          </p>
        )}

        {result && (
          <div
            className={`rounded-xl border px-4 py-3 ${
              result.ok ? 'border-signal-ok/25 bg-signal-ok/[0.06]' : 'border-signal-undo/25 bg-signal-undo/[0.06]'
            }`}
          >
            <p className="text-[13px] leading-relaxed text-slate-200">{result.summary}</p>
            <p className="mt-1 font-mono text-[11px] text-slate-500">
              {result.run_id} · {result.duration_ms.toFixed(0)}ms wall clock
            </p>
          </div>
        )}

        <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
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

          <Panel title="Reliability">
            <ReliabilityPanel metrics={result?.gate.metrics ?? null} />
          </Panel>
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
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

          <Panel title="Cryptographic audit log">
            <AuditChain attestation={result?.attestation ?? null} entries={entries} liveCount={auditCount} />
          </Panel>
        </div>
      </div>

      <footer className="mt-6 flex flex-wrap items-center justify-between gap-2 border-t border-white/[0.06] pt-4 text-[11px] text-slate-600">
        <span>Triadr - GitHub · Telegram · Stripe, behind one self-healing reliability gate.</span>
        <span className="font-mono">Apache 2.0</span>
      </footer>
    </main>
  )
}
