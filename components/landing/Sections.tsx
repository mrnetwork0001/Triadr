'use client'

import { motion } from 'framer-motion'
import { AlertTriangle, ShieldAlert, ShieldCheck } from 'lucide-react'
import { BrandLogo } from '@/components/BrandLogo'
import { APPS, GATE_STAGES, LIMITATIONS, SAFETY, STEPS } from '@/lib/landing-content'
import { Section } from './chrome'
import { Reveal, Stagger, itemVariants } from './motion'

const EFFECT_STYLE: Record<string, string> = {
  read: 'border-white/10 bg-white/[0.04] text-slate-400',
  write: 'border-signal-live/25 bg-signal-live/10 text-signal-live',
  payment: 'border-signal-heal/25 bg-signal-heal/10 text-signal-heal',
  undo: 'border-signal-undo/25 bg-signal-undo/10 text-signal-undo',
}

/* ── 01 · Problem ─────────────────────────────────────────────────────────── */

export function Problem() {
  return (
    <Section
      id="problem"
      index="01"
      eyebrow="The problem"
      title="Linear agents fail at step 4 of 6 - and leave the first three behind"
      lede="Most multi-app agents are scripts. They work in a demo and break in production, because the failure they are least prepared for is the ordinary one: a 429, a 502, a vendor quietly renaming a field."
    >
      <Stagger className="grid gap-4 lg:grid-cols-2" gap={0.12}>
        <motion.article
          variants={itemVariants}
              whileHover={{ y: -3 }}
          className="card-lift min-w-0 rounded-2xl border border-signal-fail/20 bg-signal-fail/[0.04] p-6"
        >
          <h3 className="flex items-center gap-2 text-[14px] font-semibold text-signal-fail">
            <AlertTriangle className="h-4 w-4" aria-hidden />
            Without a gate
          </h3>
          <p className="mt-3 text-[14px] leading-relaxed text-slate-400">
            Stripe rate-limits the payout. The script raises and dies. But the GitHub commit
            status is already green, and the Telegram approval card is still sitting in the chat
            asking for a decision on a payment that will never happen.
          </p>
          <ul className="mt-5 space-y-2.5 text-[13.5px] text-slate-400">
            {[
              'Steps 1-3 applied, steps 4-6 never ran',
              'A stale approval request nobody will clean up',
              'Retry the whole thing and you might pay twice',
              'No record of what the agent actually did',
            ].map((item) => (
              <li key={item} className="flex gap-3">
                <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-signal-fail" aria-hidden />
                {item}
              </li>
            ))}
          </ul>
        </motion.article>

        <motion.article
          variants={itemVariants}
              whileHover={{ y: -3 }}
          className="card-lift min-w-0 rounded-2xl border border-signal-ok/20 bg-signal-ok/[0.04] p-6"
        >
          <h3 className="flex items-center gap-2 text-[14px] font-semibold text-signal-ok">
            <ShieldCheck className="h-4 w-4" aria-hidden />
            With Triadr
          </h3>
          <p className="mt-3 text-[14px] leading-relaxed text-slate-400">
            The rate limit is classified, backed off and rerouted to a healthy gateway. If it
            genuinely cannot be recovered, the approval card is retracted and the commit status
            reset - in reverse order - before the run reports failure.
          </p>
          <ul className="mt-5 space-y-2.5 text-[13.5px] text-slate-400">
            {[
              'Every run ends fully applied or fully reverted',
              'A replayed payout returns the original transfer',
              'Contract drift is caught before it reaches a decision',
              'The whole run is hash-chained and independently verifiable',
            ].map((item) => (
              <li key={item} className="flex gap-3">
                <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-signal-ok" aria-hidden />
                {item}
              </li>
            ))}
          </ul>
        </motion.article>
      </Stagger>

      <Reveal delay={0.1}>
        <p className="mt-8 max-w-3xl text-pretty text-[15.5px] leading-relaxed text-slate-300">
          The thesis is small and testable:{' '}
          <strong className="font-semibold text-slate-100">
            a multi-step workflow should end fully applied or fully reverted, and the record of
            which should be independently verifiable.
          </strong>{' '}
          Everything in Triadr exists to make that true.
        </p>
      </Reveal>
    </Section>
  )
}

/* ── 02 · Apps ────────────────────────────────────────────────────────────── */

export function Apps() {
  return (
    <Section
      id="apps"
      index="02"
      eyebrow="Three connected apps"
      title="14 MCP tools, each declaring how it is undone"
      lede="Every tool publishes a real JSON Schema contract. Every tool that mutates remote state names the tool that reverses it - a structural test enforces this, so the saga guarantee cannot rot as tools are added."
    >
      <Stagger className="grid gap-4 lg:grid-cols-3" gap={0.12}>
        {APPS.map((app) => {
          return (
            <motion.article
              key={app.id}
              variants={itemVariants}
              whileHover={{ y: -3 }}
              className="card-lift panel flex min-w-0 flex-col rounded-2xl p-6"
            >
              <div className="flex items-start gap-3">
                <BrandLogo app={app.id} size={40} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2">
                    <h3 className="text-[16px] font-semibold text-slate-100">{app.name}</h3>
                    <span className="font-mono text-[10px] text-slate-600">App #{app.index}</span>
                  </div>
                  <p className="text-[12px] text-slate-500">{app.role}</p>
                </div>
              </div>

              <p className="mt-4 text-[13.5px] leading-relaxed text-slate-400">{app.blurb}</p>

              <ul className="mt-5 space-y-2 border-t border-white/[0.06] pt-4">
                {app.tools.map((tool) => (
                  <li key={tool.name} className="flex items-center gap-2">
                    <code className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-slate-400">
                      {app.id}.{tool.name}
                    </code>
                    <span className={`chip shrink-0 ${EFFECT_STYLE[tool.effect]}`}>{tool.effect}</span>
                  </li>
                ))}
              </ul>

              <p className="mt-5 border-t border-white/[0.06] pt-3 text-[12px] leading-relaxed text-slate-500">
                Runs against the real {app.name} API once{' '}
                <code className="font-mono text-[11px] text-slate-400">{app.credential}</code> is set;
                simulated until then, and it says which.
              </p>
            </motion.article>
          )
        })}
      </Stagger>

      <Reveal delay={0.1} className="mt-6">
        <div className="rounded-2xl border border-white/[0.07] bg-ink-900/70 p-6">
          <h3 className="text-[15px] font-semibold text-slate-100">The workflow it composes</h3>
          <p className="mt-2 max-w-3xl text-[13.5px] leading-relaxed text-slate-500">
            The plan shape is fixed in code. An LLM may extract parameters - repo, amount, chat -
            but can never add, remove or reorder a step. A hallucinated second{' '}
            <code className="font-mono text-slate-400">release_escrow</code> would be a financial
            incident, so the model is not given that authority.
          </p>
          <Stagger as="ol" className="mt-5 space-y-1.5" gap={0.06}>
            {STEPS.map((step) => (
              <motion.li
                key={step.n}
                variants={itemVariants}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-white/[0.05] bg-white/[0.02] px-3.5 py-2.5 transition-colors hover:bg-white/[0.04]"
              >
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md border border-white/10 font-mono text-[11px] text-slate-400">
                  {step.n}
                </span>
                <span className="w-[68px] shrink-0 text-[11px] uppercase tracking-wider text-slate-500">{step.app}</span>
                <span className="min-w-0 flex-1 text-[13.5px] text-slate-300">{step.title}</span>
                <span className="shrink-0 font-mono text-[10.5px] text-slate-600">{step.note}</span>
                {step.undo ? (
                  <span className="chip shrink-0 border-signal-undo/25 bg-signal-undo/10 text-signal-undo">
                    undo · {step.undo}
                  </span>
                ) : (
                  <span className="chip shrink-0 border-white/10 bg-white/[0.03] text-slate-600">no side effect</span>
                )}
              </motion.li>
            ))}
          </Stagger>
        </div>
      </Reveal>
    </Section>
  )
}

/* ── 03 · The gate, as a pipeline ─────────────────────────────────────────── */

export function Gate() {
  const half = Math.ceil(GATE_STAGES.length / 2)
  const columns = [GATE_STAGES.slice(0, half), GATE_STAGES.slice(half)]
  return (
    <Section
      id="gate"
      index="03"
      eyebrow="The reliability gate"
      title="Eight checks between the agent and the outside world"
      lede="Every call to every app goes through one function. It runs in this order, and the first four all happen before a single packet leaves the process."
      className="bg-white/[0.012]"
    >
      <div className="grid gap-x-10 gap-y-2 lg:grid-cols-2">
        {columns.map((stages, c) => (
          <Stagger key={c} as="ol" className="relative" gap={0.14} delay={c * 0.2}>
            {/* rail */}
            <span
              aria-hidden
              className="absolute bottom-6 left-[15px] top-6 w-px bg-gradient-to-b from-signal-live/60 via-white/15 to-transparent"
            />
            {stages.map((stage) => (
              <motion.li key={stage.n} variants={itemVariants} className="relative flex gap-5 py-3 pl-0">
                <span className="relative z-10 mt-4 grid h-8 w-8 shrink-0 place-items-center rounded-full border border-signal-live/40 bg-ink-950 font-mono text-[11px] font-semibold text-signal-live shadow-[0_0_0_4px_rgba(56,189,248,0.08)]">
                  {stage.n}
                </span>
                <div className="card-lift min-w-0 flex-1 rounded-2xl border border-white/[0.07] bg-ink-900/70 p-5">
                  <h3 className="text-[14px] font-semibold text-slate-100">{stage.title}</h3>
                  <p className="mt-1.5 text-[13.5px] leading-relaxed text-slate-400">{stage.body}</p>
                </div>
              </motion.li>
            ))}
          </Stagger>
        ))}
      </div>
    </Section>
  )
}

/* ── 08 · Safety ──────────────────────────────────────────────────────────── */

export function Safety() {
  return (
    <Section id="safety" index="07" eyebrow="Safety" title="The properties that matter when an agent can move money">
      <Reveal>
        <div className="overflow-x-auto rounded-2xl border border-white/[0.07]">
          <table className="w-full min-w-[560px] border-collapse text-left">
            <thead>
              <tr className="border-b border-white/[0.07] bg-white/[0.02]">
                <th className="px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Property</th>
                <th className="px-5 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Mechanism</th>
              </tr>
            </thead>
            <tbody>
              {SAFETY.map((row) => (
                <tr key={row.property} className="border-b border-white/[0.05] transition-colors last:border-0 hover:bg-white/[0.02]">
                  <td className="px-5 py-3 align-top">
                    <span className="flex items-start gap-2 text-[13.5px] font-medium text-slate-200">
                      <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-signal-ok" aria-hidden />
                      {row.property}
                    </span>
                  </td>
                  <td className="px-5 py-3 align-top text-[13.5px] leading-relaxed text-slate-400">{row.mechanism}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Reveal>

      <Reveal delay={0.1} className="mt-5">
        <div className="rounded-2xl border border-signal-heal/20 bg-signal-heal/[0.04] p-6">
          <h3 className="flex items-center gap-2 text-[14px] font-semibold text-signal-heal">
            <ShieldAlert className="h-4 w-4" aria-hidden />
            Honest limitations
          </h3>
          <p className="mt-2 text-[13.5px] text-slate-400">
            Judges will find these anyway, so they are stated up front rather than buried.
          </p>
          <ul className="mt-4 space-y-3">
            {LIMITATIONS.map((item) => (
              <li key={item} className="flex gap-3 text-[13.5px] leading-relaxed text-slate-400">
                <span className="mt-[8px] h-1.5 w-1.5 shrink-0 rounded-full bg-signal-heal" aria-hidden />
                {item}
              </li>
            ))}
          </ul>
        </div>
      </Reveal>
    </Section>
  )
}
