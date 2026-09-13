'use client'

import { useEffect, useState } from 'react'
import { Gauge, KeyRound, Link2, ShieldCheck, Timer } from 'lucide-react'
import { BENCHMARK, CAMPAIGN, SCENARIOS, type BenchRow } from '@/lib/landing-content'
import { Section } from './chrome'

const TONE: Record<string, { chip: string; dot: string }> = {
  ok: { chip: 'border-signal-ok/30 bg-signal-ok/10 text-signal-ok', dot: 'bg-signal-ok' },
  heal: { chip: 'border-signal-heal/30 bg-signal-heal/10 text-signal-heal', dot: 'bg-signal-heal' },
  undo: { chip: 'border-signal-undo/30 bg-signal-undo/10 text-signal-undo', dot: 'bg-signal-undo' },
  fail: { chip: 'border-signal-fail/30 bg-signal-fail/10 text-signal-fail', dot: 'bg-signal-fail' },
}

export function Scenarios() {
  return (
    <Section
      id="scenarios"
      eyebrow="Four scenarios"
      title="Including the two that are supposed to fail"
      lede="A reliability engine that only demonstrates its happy path has demonstrated nothing. Each scenario is one command, and the rollback path is injected at the app boundary so every layer above it behaves exactly as it would during a real outage."
    >
      <div className="grid gap-4 md:grid-cols-2">
        {SCENARIOS.map((scenario) => {
          const tone = TONE[scenario.tone]
          return (
            <article key={scenario.id} className="panel flex min-w-0 flex-col p-5">
              <div className="flex items-center gap-2.5">
                <span className={`h-2 w-2 shrink-0 rounded-full ${tone.dot}`} aria-hidden />
                <h3 className="flex-1 text-[15px] font-semibold text-slate-100">{scenario.label}</h3>
                <span className={`chip ${tone.chip}`}>{scenario.outcome}</span>
              </div>

              <p className="mt-3 flex-1 text-[13px] leading-relaxed text-slate-400">{scenario.proves}</p>

              <dl className="mt-4 grid grid-cols-3 gap-2 border-t border-white/[0.06] pt-3.5">
                {[
                  { label: 'steps', value: scenario.steps },
                  { label: 'faults', value: scenario.faults },
                  { label: 'undone', value: scenario.undone },
                ].map((cell) => (
                  <div key={cell.label}>
                    <dd className="font-mono text-[16px] font-semibold tabular-nums text-slate-200">
                      {cell.value}
                    </dd>
                    <dt className="text-[10px] uppercase tracking-[0.12em] text-slate-600">
                      {cell.label}
                    </dt>
                  </div>
                ))}
              </dl>

              <code className="mt-3.5 block truncate rounded-md border border-white/[0.06] bg-black/30 px-2.5 py-1.5 font-mono text-[11px] text-slate-500">
                python3 main.py --scenario {scenario.id}
              </code>
            </article>
          )
        })}
      </div>
    </Section>
  )
}

export function Evidence() {
  // Benchmarks are re-measured live when the control plane is reachable, so the
  // page shows this machine's numbers rather than only the recorded ones.
  const [live, setLive] = useState<BenchRow[] | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/benchmark?iterations=20000', { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error('offline'))))
      .then((data) => {
        if (cancelled) return
        const fmt = (n: number) => `${n.toFixed(2)} µs`
        setLive([
          {
            phase: 'Input schema validation',
            detail: 'Gates every side effect before it happens',
            p50: fmt(data.schema_validation.p50_us),
            p95: fmt(data.schema_validation.p95_us),
            p99: fmt(data.schema_validation.p99_us),
          },
          {
            phase: 'Full pre-flight',
            detail: 'The above plus the response drift fingerprint',
            p50: fmt(data.full_preflight.p50_us),
            p95: fmt(data.full_preflight.p95_us),
            p99: fmt(data.full_preflight.p99_us),
          },
        ])
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [])

  const rows = live ?? BENCHMARK.rows

  return (
    <Section
      id="evidence"
      eyebrow="Evidence"
      title="Measured, not asserted"
      lede="Every figure on this page is produced by a script in the repo. Re-run it and the numbers regenerate; change the engine and they change with it."
      className="border-y border-white/[0.06] bg-white/[0.012]"
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <article className="panel min-w-0 p-5">
          <h3 className="text-[14px] font-semibold text-slate-100">
            {CAMPAIGN.runs} runs under a {CAMPAIGN.faultRate} fault storm
          </h3>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-slate-500">
            Faults are injected on a seeded RNG, so the same seed replays the identical failure
            sequence and the identical recovery path.
          </p>

          <dl className="mt-4 space-y-1.5">
            {[
              { label: 'Fully applied', value: CAMPAIGN.fullyApplied, tone: 'text-signal-ok' },
              { label: 'Fully rolled back', value: CAMPAIGN.fullyRolledBack, tone: 'text-signal-undo' },
              { label: 'Left half-executed', value: CAMPAIGN.halfExecuted, tone: 'text-signal-ok', emphasis: true },
              { label: 'Duplicate payouts', value: CAMPAIGN.duplicatePayouts, tone: 'text-signal-ok', emphasis: true },
              { label: 'Faults absorbed', value: CAMPAIGN.faultsAbsorbed, tone: 'text-slate-200' },
              { label: 'Steps self-healed', value: CAMPAIGN.stepsSelfHealed, tone: 'text-slate-200' },
              { label: 'Side effects reverted', value: CAMPAIGN.sideEffectsReverted, tone: 'text-slate-200' },
              { label: 'Audit chains valid', value: `${CAMPAIGN.chainsValid}/${CAMPAIGN.runs}`, tone: 'text-signal-ok' },
            ].map((row) => (
              <div
                key={row.label}
                className={`flex items-center justify-between gap-3 rounded-lg px-3 py-2 ${
                  row.emphasis ? 'border border-signal-ok/20 bg-signal-ok/[0.06]' : 'bg-white/[0.02]'
                }`}
              >
                <dt className="text-[13px] text-slate-400">{row.label}</dt>
                <dd className={`font-mono text-[15px] font-semibold tabular-nums ${row.tone}`}>
                  {row.value}
                </dd>
              </div>
            ))}
          </dl>

          <p className="mt-4 text-[12.5px] leading-relaxed text-slate-500">
            The {CAMPAIGN.fullyRolledBack} rolled-back runs are the important column. At this fault
            rate a linear script would have left partial state in most of them - a posted approval
            card with no payout, or a payment with no record. Triadr left none.
          </p>

          <code className="mt-3.5 block truncate rounded-md border border-white/[0.06] bg-black/30 px-2.5 py-1.5 font-mono text-[11px] text-slate-500">
            {CAMPAIGN.command}
          </code>
        </article>

        <div className="min-w-0 space-y-4">
          <article className="panel min-w-0 p-5">
            <div className="flex items-center justify-between gap-3">
              <h3 className="flex items-center gap-2 text-[14px] font-semibold text-slate-100">
                <Timer className="h-4 w-4 text-signal-live" aria-hidden />
                Gate overhead
              </h3>
              {live && (
                <span className="chip border-signal-ok/30 bg-signal-ok/10 text-signal-ok">
                  measured just now
                </span>
              )}
            </div>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-slate-500">
              Both phases are reported, because quoting only the first would overstate the engine.
            </p>

            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[380px] border-collapse text-left">
                <thead>
                  <tr className="border-b border-white/[0.07]">
                    <th className="pb-2 pr-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                      Phase
                    </th>
                    {['p50', 'p95', 'p99'].map((h) => (
                      <th
                        key={h}
                        className="pb-2 pl-3 text-right text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.phase} className="border-b border-white/[0.05] last:border-0">
                      <td className="py-2.5 pr-3 align-top">
                        <span className="block text-[13px] text-slate-200">{row.phase}</span>
                        <span className="block text-[11px] leading-snug text-slate-600">{row.detail}</span>
                      </td>
                      <td className="py-2.5 pl-3 text-right align-top font-mono text-[13px] font-semibold tabular-nums text-slate-100">
                        {row.p50}
                      </td>
                      <td className="py-2.5 pl-3 text-right align-top font-mono text-[12px] tabular-nums text-slate-400">
                        {row.p95}
                      </td>
                      <td className="py-2.5 pl-3 text-right align-top font-mono text-[12px] tabular-nums text-slate-400">
                        {row.p99}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <code className="mt-3.5 block truncate rounded-md border border-white/[0.06] bg-black/30 px-2.5 py-1.5 font-mono text-[11px] text-slate-500">
              {BENCHMARK.command}
            </code>
          </article>

          <article className="panel min-w-0 p-5">
            <h3 className="flex items-center gap-2 text-[14px] font-semibold text-slate-100">
              <Gauge className="h-4 w-4 text-signal-live" aria-hidden />
              125 tests
            </h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-slate-400">
              Schema edge cases (including <code className="font-mono text-slate-300">True</code> not
              satisfying <code className="font-mono text-slate-300">integer</code>), breaker state
              transitions, backoff bounds, endpoint deprioritisation, idempotency, drift detection,
              chaos determinism, the MCP JSON-RPC surface, hash-chain tamper evidence - and an
              eight-seed property test asserting the core invariant directly.
            </p>
            <code className="mt-3.5 block truncate rounded-md border border-white/[0.06] bg-black/30 px-2.5 py-1.5 font-mono text-[11px] text-slate-500">
              python3 -m pytest tests/ -q
            </code>
          </article>
        </div>
      </div>
    </Section>
  )
}

export function AuditLog() {
  return (
    <Section
      id="audit"
      eyebrow="Cryptographic audit log"
      title="Reliability claims you can recompute yourself"
      lede="Every gate decision, injected fault, recovery and compensation becomes one entry in an append-only SHA-256 hash chain."
    >
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <article className="panel min-w-0 p-5">
          <div className="overflow-x-auto rounded-lg border border-white/[0.06] bg-black/30 px-4 py-3">
            <code className="whitespace-nowrap font-mono text-[12.5px] text-slate-300">
              digest(n) = SHA256( digest(n−1) ‖ canonical_json(entry(n)) )
            </code>
          </div>

          <ul className="mt-4 space-y-3">
            {[
              {
                icon: Link2,
                title: 'Tamper-evident by construction',
                body: 'Editing, reordering or deleting any entry breaks verification at exactly the corrupted index - demonstrated by test, not merely claimed.',
              },
              {
                icon: ShieldCheck,
                title: 'Deterministic across machines',
                body: 'Canonical serialisation fixes key order and separators, so the same entry hashes identically anywhere.',
              },
              {
                icon: KeyRound,
                title: 'Merkle root, optionally signed',
                body: 'The attestation commits to every entry, and with TRIADR_LOG_KEY set it carries an HMAC-SHA256 signature. run.end is recorded before the seal, so the commitment covers the complete log.',
              },
            ].map((item) => (
              <li key={item.title} className="flex gap-3">
                <item.icon className="mt-0.5 h-4 w-4 shrink-0 text-signal-ok" aria-hidden />
                <div>
                  <h3 className="text-[13.5px] font-semibold text-slate-100">{item.title}</h3>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-slate-400">{item.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </article>

        <article className="panel min-w-0 overflow-hidden">
          <header className="panel-head">
            <h3 className="panel-title">Verify any past run</h3>
          </header>
          <div className="space-y-3 p-5">
            <code className="block overflow-x-auto whitespace-nowrap rounded-md border border-white/[0.06] bg-black/30 px-3 py-2 font-mono text-[11.5px] text-slate-400">
              python3 main.py --verify .triadr/&lt;run_id&gt;.jsonl
            </code>
            <div className="rounded-lg border border-signal-ok/20 bg-signal-ok/[0.05] px-3.5 py-3 font-mono text-[11.5px] leading-relaxed text-slate-400">
              <div>entries      44</div>
              <div>
                chain        <span className="text-signal-ok">VALID</span>
              </div>
              <div>reason       chain intact</div>
              <div className="truncate">merkle root  3c49e353f8…addf507d2b</div>
            </div>
            <p className="text-[12.5px] leading-relaxed text-slate-500">
              This is what separates a reliability number from a marketing number. The log is
              written to disk on every run, and the verifier is a standalone command that takes
              nothing on trust from the process that produced it.
            </p>
          </div>
        </article>
      </div>
    </Section>
  )
}
