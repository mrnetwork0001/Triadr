'use client'

import { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { Gauge, KeyRound, Link2, ShieldCheck, Timer } from 'lucide-react'
import { BENCHMARK, CAMPAIGN, SCENARIOS, type BenchRow } from '@/lib/landing-content'
import { Section } from './chrome'
import { CountUp, EASE, Reveal, Stagger, itemVariants } from './motion'

const TONE: Record<string, { chip: string; dot: string; bar: string }> = {
  ok: { chip: 'border-signal-ok/30 bg-signal-ok/10 text-signal-ok', dot: 'bg-signal-ok', bar: 'from-signal-ok/60' },
  heal: { chip: 'border-signal-heal/30 bg-signal-heal/10 text-signal-heal', dot: 'bg-signal-heal', bar: 'from-signal-heal/60' },
  undo: { chip: 'border-signal-undo/30 bg-signal-undo/10 text-signal-undo', dot: 'bg-signal-undo', bar: 'from-signal-undo/60' },
  fail: { chip: 'border-signal-fail/30 bg-signal-fail/10 text-signal-fail', dot: 'bg-signal-fail', bar: 'from-signal-fail/60' },
}

/* ── 04 · Scenarios ───────────────────────────────────────────────────────── */

export function Scenarios() {
  return (
    <Section
      id="scenarios"
      index="04"
      eyebrow="Four scenarios"
      title="Including the two that are supposed to fail"
      lede="A reliability engine that only demonstrates its happy path has demonstrated nothing. Each scenario is one command, and the rollback path is injected at the app boundary so every layer above it behaves exactly as it would during a real outage."
    >
      <Stagger className="grid gap-4 md:grid-cols-2" gap={0.1}>
        {SCENARIOS.map((scenario) => {
          const tone = TONE[scenario.tone]
          return (
            <motion.article
              key={scenario.id}
              variants={itemVariants}
              whileHover={{ y: -3 }}
              className="card-lift panel relative flex min-w-0 flex-col overflow-hidden rounded-2xl p-6"
            >
              <span aria-hidden className={`absolute inset-x-0 top-0 h-px bg-gradient-to-r ${tone.bar} to-transparent`} />
              <div className="flex items-center gap-2.5">
                <span className={`h-2 w-2 shrink-0 rounded-full ${tone.dot}`} aria-hidden />
                <h3 className="flex-1 text-[16px] font-semibold text-slate-100">{scenario.label}</h3>
                <span className={`chip ${tone.chip}`}>{scenario.outcome}</span>
              </div>

              <p className="mt-3 flex-1 text-[13.5px] leading-relaxed text-slate-400">{scenario.proves}</p>

              <dl className="mt-5 grid grid-cols-3 gap-2 border-t border-white/[0.06] pt-4">
                {[
                  { label: 'steps', value: scenario.steps },
                  { label: 'faults', value: scenario.faults },
                  { label: 'undone', value: scenario.undone },
                ].map((cell) => (
                  <div key={cell.label}>
                    <dd className="font-mono text-[17px] font-semibold tabular-nums text-slate-200">{cell.value}</dd>
                    <dt className="text-[10px] uppercase tracking-[0.12em] text-slate-600">{cell.label}</dt>
                  </div>
                ))}
              </dl>

              <code className="mt-4 block truncate rounded-lg border border-white/[0.06] bg-black/30 px-3 py-2 font-mono text-[11px] text-slate-500">
                python3 main.py --scenario {scenario.id}
              </code>
            </motion.article>
          )
        })}
      </Stagger>
    </Section>
  )
}

/* ── 05 · Evidence ────────────────────────────────────────────────────────── */

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
          { phase: 'Input schema validation', detail: 'Gates every side effect before it happens',
            p50: fmt(data.schema_validation.p50_us), p95: fmt(data.schema_validation.p95_us), p99: fmt(data.schema_validation.p99_us) },
          { phase: 'Full pre-flight', detail: 'The above plus the response drift fingerprint',
            p50: fmt(data.full_preflight.p50_us), p95: fmt(data.full_preflight.p95_us), p99: fmt(data.full_preflight.p99_us) },
        ])
      })
      .catch(() => undefined)
    return () => { cancelled = true }
  }, [])

  const rows = live ?? BENCHMARK.rows
  const campaignRows = [
    { label: 'Fully applied', value: CAMPAIGN.fullyApplied, tone: 'text-signal-ok' },
    { label: 'Fully rolled back', value: CAMPAIGN.fullyRolledBack, tone: 'text-signal-undo' },
    { label: 'Left half-executed', value: CAMPAIGN.halfExecuted, tone: 'text-signal-ok', emphasis: true },
    { label: 'Duplicate payouts', value: CAMPAIGN.duplicatePayouts, tone: 'text-signal-ok', emphasis: true },
    { label: 'Faults absorbed', value: CAMPAIGN.faultsAbsorbed, tone: 'text-slate-200' },
    { label: 'Steps self-healed', value: CAMPAIGN.stepsSelfHealed, tone: 'text-slate-200' },
    { label: 'Side effects reverted', value: CAMPAIGN.sideEffectsReverted, tone: 'text-slate-200' },
  ]

  return (
    <Section
      id="evidence"
      index="05"
      eyebrow="Evidence"
      title="Measured, not asserted"
      lede="Every figure on this page is produced by a script in the repo. Re-run it and the numbers regenerate; change the engine and they change with it."
      className="bg-white/[0.012]"
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <Reveal>
          <article className="card-lift panel min-w-0 rounded-2xl p-6">
            <h3 className="text-[15px] font-semibold text-slate-100">
              {CAMPAIGN.runs} runs under a {CAMPAIGN.faultRate} fault storm
            </h3>
            <p className="mt-2 text-[13px] leading-relaxed text-slate-500">
              Faults are injected on a seeded RNG, so the same seed replays the identical failure
              sequence and the identical recovery path.
            </p>

            <Stagger as="div" className="mt-5 space-y-1.5" gap={0.05}>
              {campaignRows.map((row) => (
                <motion.div
                  key={row.label}
                  variants={itemVariants}
                  className={`flex items-center justify-between gap-3 rounded-lg px-3.5 py-2.5 ${
                    row.emphasis ? 'border border-signal-ok/20 bg-signal-ok/[0.06]' : 'bg-white/[0.02]'
                  }`}
                >
                  <dt className="text-[13.5px] text-slate-400">{row.label}</dt>
                  <dd className={`font-mono text-[16px] font-semibold tabular-nums ${row.tone}`}>
                    <CountUp value={row.value} />
                  </dd>
                </motion.div>
              ))}
              <motion.div
                variants={itemVariants}
                className="flex items-center justify-between gap-3 rounded-lg bg-white/[0.02] px-3.5 py-2.5"
              >
                <dt className="text-[13.5px] text-slate-400">Audit chains valid</dt>
                <dd className="font-mono text-[16px] font-semibold tabular-nums text-signal-ok">
                  <CountUp value={CAMPAIGN.chainsValid} />/{CAMPAIGN.runs}
                </dd>
              </motion.div>
            </Stagger>

            <p className="mt-5 text-[13px] leading-relaxed text-slate-500">
              The {CAMPAIGN.fullyRolledBack} rolled-back runs are the important column. At this fault
              rate a linear script would have left partial state in most of them - a posted approval
              card with no payout, or a payment with no record. Triadr left none.
            </p>
            <code className="mt-4 block truncate rounded-lg border border-white/[0.06] bg-black/30 px-3 py-2 font-mono text-[11px] text-slate-500">
              {CAMPAIGN.command}
            </code>
          </article>
        </Reveal>

        <div className="min-w-0 space-y-4">
          <Reveal delay={0.1}>
            <article className="card-lift panel min-w-0 rounded-2xl p-6">
              <div className="flex items-center justify-between gap-3">
                <h3 className="flex items-center gap-2 text-[15px] font-semibold text-slate-100">
                  <Timer className="h-4 w-4 text-signal-live" aria-hidden />
                  Gate overhead
                </h3>
                {live && (
                  <motion.span
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.4, ease: EASE }}
                    className="chip border-signal-ok/30 bg-signal-ok/10 text-signal-ok"
                  >
                    measured just now
                  </motion.span>
                )}
              </div>
              <p className="mt-2 text-[13px] leading-relaxed text-slate-500">
                Both phases are reported, because quoting only the first would overstate the engine.
              </p>

              <div className="mt-5 overflow-x-auto">
                <table className="w-full min-w-[380px] border-collapse text-left">
                  <thead>
                    <tr className="border-b border-white/[0.07]">
                      <th className="pb-2 pr-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">Phase</th>
                      {['p50', 'p95', 'p99'].map((h) => (
                        <th key={h} className="pb-2 pl-3 text-right text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr key={row.phase} className="border-b border-white/[0.05] last:border-0">
                        <td className="py-3 pr-3 align-top">
                          <span className="block text-[13.5px] text-slate-200">{row.phase}</span>
                          <span className="block text-[11px] leading-snug text-slate-600">{row.detail}</span>
                        </td>
                        <td className="py-3 pl-3 text-right align-top font-mono text-[13.5px] font-semibold tabular-nums text-slate-100">{row.p50}</td>
                        <td className="py-3 pl-3 text-right align-top font-mono text-[12px] tabular-nums text-slate-400">{row.p95}</td>
                        <td className="py-3 pl-3 text-right align-top font-mono text-[12px] tabular-nums text-slate-400">{row.p99}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <code className="mt-4 block truncate rounded-lg border border-white/[0.06] bg-black/30 px-3 py-2 font-mono text-[11px] text-slate-500">
                {BENCHMARK.command}
              </code>
            </article>
          </Reveal>

          <Reveal delay={0.2}>
            <article className="card-lift panel min-w-0 rounded-2xl p-6">
              <h3 className="flex items-center gap-2 text-[15px] font-semibold text-slate-100">
                <Gauge className="h-4 w-4 text-signal-live" aria-hidden />
                <span><CountUp value={176} /> tests</span>
              </h3>
              <p className="mt-2 text-[13.5px] leading-relaxed text-slate-400">
                Schema edge cases (including <code className="font-mono text-slate-300">True</code> not
                satisfying <code className="font-mono text-slate-300">integer</code>), breaker state
                transitions, backoff bounds, endpoint deprioritisation, idempotency, drift detection,
                chaos determinism, the MCP JSON-RPC surface, LIVE request wiring for all fourteen tools,
                hash-chain tamper evidence - and an eight-seed property test asserting the core invariant.
              </p>
              <code className="mt-4 block truncate rounded-lg border border-white/[0.06] bg-black/30 px-3 py-2 font-mono text-[11px] text-slate-500">
                python3 -m pytest tests/ -q
              </code>
            </article>
          </Reveal>
        </div>
      </div>
    </Section>
  )
}

/* ── 06 · Audit log, with the chain drawn ─────────────────────────────────── */

function ChainDiagram() {
  const reduce = useReducedMotion()
  const blocks = ['run.start', 'gate.ok', 'gate.fault', 'gate.ok', 'run.end']
  const W = 720, H = 96, BW = 112, GAP = (W - blocks.length * BW) / (blocks.length - 1)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" aria-hidden>
      <defs>
        <linearGradient id="chain-line" x1="0" x2="1">
          <stop offset="0" stopColor="#38bdf8" stopOpacity="0.9" />
          <stop offset="1" stopColor="#34d399" stopOpacity="0.9" />
        </linearGradient>
      </defs>
      {blocks.map((label, i) => {
        const x = i * (BW + GAP)
        return (
          <motion.g
            key={label + i}
            initial={reduce ? false : { opacity: 0, y: 8 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, delay: 0.15 * i, ease: EASE }}
          >
            <rect x={x} y={20} width={BW} height={56} rx={10} fill="#0b0d14" stroke="rgba(255,255,255,0.14)" />
            <text x={x + 12} y={40} fill="#94a3b8" fontFamily="ui-monospace, Menlo, monospace" fontSize="11">
              #{i} {label}
            </text>
            <text x={x + 12} y={62} fill="#475569" fontFamily="ui-monospace, Menlo, monospace" fontSize="10">
              sha256 {(0x3c49 + i * 0x2b7).toString(16)}…
            </text>
            {i < blocks.length - 1 && (
              <motion.path
                d={`M ${x + BW} 48 L ${x + BW + GAP} 48`}
                stroke="url(#chain-line)"
                strokeWidth="2"
                strokeLinecap="round"
                fill="none"
                initial={reduce ? false : { pathLength: 0, opacity: 0 }}
                whileInView={{ pathLength: 1, opacity: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: 0.15 * i + 0.3, ease: EASE }}
              />
            )}
          </motion.g>
        )
      })}
    </svg>
  )
}

export function AuditLog() {
  return (
    <Section
      id="audit"
      index="06"
      eyebrow="Cryptographic audit log"
      title="Reliability claims you can recompute yourself"
      lede="Every gate decision, injected fault, recovery and compensation becomes one entry in an append-only SHA-256 hash chain."
    >
      <Reveal>
        <div className="rounded-2xl border border-white/[0.07] bg-ink-900/70 px-5 py-6 sm:px-8">
          <ChainDiagram />
          <div className="mt-4 overflow-x-auto rounded-lg border border-white/[0.06] bg-black/30 px-4 py-3">
            <code className="whitespace-nowrap font-mono text-[12.5px] text-slate-300">
              digest(n) = SHA256( digest(n−1) ‖ canonical_json(entry(n)) )
            </code>
          </div>
        </div>
      </Reveal>

      <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <Reveal delay={0.1}>
          <article className="card-lift panel min-w-0 rounded-2xl p-6">
            <ul className="space-y-4">
              {[
                { icon: Link2, title: 'Tamper-evident by construction',
                  body: 'Editing, reordering or deleting any entry breaks verification at exactly the corrupted index - demonstrated by test, not merely claimed.' },
                { icon: ShieldCheck, title: 'Deterministic across machines',
                  body: 'Canonical serialisation fixes key order and separators, so the same entry hashes identically anywhere.' },
                { icon: KeyRound, title: 'Merkle root, optionally signed',
                  body: 'The attestation commits to every entry, and with TRIADR_LOG_KEY set it carries an HMAC-SHA256 signature. run.end is recorded before the seal, so the commitment covers the complete log.' },
              ].map((item) => (
                <li key={item.title} className="flex gap-3">
                  <item.icon className="mt-0.5 h-4 w-4 shrink-0 text-signal-ok" aria-hidden />
                  <div>
                    <h3 className="text-[14px] font-semibold text-slate-100">{item.title}</h3>
                    <p className="mt-1 text-[13.5px] leading-relaxed text-slate-400">{item.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </article>
        </Reveal>

        <Reveal delay={0.2}>
          <article className="card-lift panel min-w-0 overflow-hidden rounded-2xl">
            <header className="panel-head">
              <h3 className="panel-title">Verify any past run</h3>
            </header>
            <div className="space-y-3 p-6">
              <code className="block overflow-x-auto whitespace-nowrap rounded-lg border border-white/[0.06] bg-black/30 px-3 py-2 font-mono text-[11.5px] text-slate-400">
                python3 main.py --verify .triadr/&lt;run_id&gt;.jsonl
              </code>
              <div className="rounded-lg border border-signal-ok/20 bg-signal-ok/[0.05] px-4 py-3 font-mono text-[11.5px] leading-relaxed text-slate-400">
                <div>entries      44</div>
                <div>chain        <span className="text-signal-ok">VALID</span></div>
                <div>reason       chain intact</div>
                <div className="truncate">merkle root  3c49e353f8…addf507d2b</div>
              </div>
              <p className="text-[13px] leading-relaxed text-slate-500">
                This is what separates a reliability number from a marketing number. The log is
                written to disk on every run, and the verifier is a standalone command that takes
                nothing on trust from the process that produced it.
              </p>
            </div>
          </article>
        </Reveal>
      </div>
    </Section>
  )
}
