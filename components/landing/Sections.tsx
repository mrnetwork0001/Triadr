'use client'

import { CreditCard, Github, Send, ShieldAlert, ShieldCheck, AlertTriangle } from 'lucide-react'
import { APPS, GATE_STAGES, LIMITATIONS, SAFETY, STEPS } from '@/lib/landing-content'
import { Section } from './chrome'

const APP_ICONS = { github: Github, telegram: Send, stripe: CreditCard } as const

const EFFECT_STYLE: Record<string, string> = {
  read: 'border-white/10 bg-white/[0.04] text-slate-400',
  write: 'border-signal-live/25 bg-signal-live/10 text-signal-live',
  payment: 'border-signal-heal/25 bg-signal-heal/10 text-signal-heal',
  undo: 'border-signal-undo/25 bg-signal-undo/10 text-signal-undo',
}

const APP_TONE: Record<string, string> = {
  github: 'text-slate-200',
  telegram: 'text-signal-undo',
  stripe: 'text-signal-live',
}

export function Problem() {
  return (
    <Section
      id="problem"
      eyebrow="The problem"
      title="Linear agents fail at step 4 of 6 - and leave the first three behind"
      lede="Most multi-app agents are scripts. They work in a demo and break in production, because the failure they are least prepared for is the ordinary one: a 429, a 502, a vendor quietly renaming a field."
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <article className="min-w-0 rounded-xl border border-signal-fail/20 bg-signal-fail/[0.04] p-5">
          <h3 className="flex items-center gap-2 text-[14px] font-semibold text-signal-fail">
            <AlertTriangle className="h-4 w-4" aria-hidden />
            Without a gate
          </h3>
          <p className="mt-2.5 text-[13.5px] leading-relaxed text-slate-400">
            Stripe rate-limits the payout. The script raises and dies. But the GitHub commit
            status is already green, and the Telegram approval card is still sitting in the chat
            asking for a decision on a payment that will never happen.
          </p>
          <ul className="mt-4 space-y-2 text-[13px] text-slate-400">
            {[
              'Steps 1–3 applied, steps 4–6 never ran',
              'A stale approval request nobody will clean up',
              'Retry the whole thing and you might pay twice',
              'No record of what the agent actually did',
            ].map((item) => (
              <li key={item} className="flex gap-2.5">
                <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-signal-fail" aria-hidden />
                {item}
              </li>
            ))}
          </ul>
        </article>

        <article className="min-w-0 rounded-xl border border-signal-ok/20 bg-signal-ok/[0.04] p-5">
          <h3 className="flex items-center gap-2 text-[14px] font-semibold text-signal-ok">
            <ShieldCheck className="h-4 w-4" aria-hidden />
            With Triadr
          </h3>
          <p className="mt-2.5 text-[13.5px] leading-relaxed text-slate-400">
            The rate limit is classified, backed off and rerouted to a healthy gateway. If it
            genuinely cannot be recovered, the approval card is retracted and the commit status
            reset - in reverse order - before the run reports failure.
          </p>
          <ul className="mt-4 space-y-2 text-[13px] text-slate-400">
            {[
              'Every run ends fully applied or fully reverted',
              'A replayed payout returns the original transfer',
              'Contract drift is caught before it reaches a decision',
              'The whole run is hash-chained and independently verifiable',
            ].map((item) => (
              <li key={item} className="flex gap-2.5">
                <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-signal-ok" aria-hidden />
                {item}
              </li>
            ))}
          </ul>
        </article>
      </div>

      <p className="mt-6 max-w-3xl text-pretty text-[15px] leading-relaxed text-slate-300">
        The thesis is small and testable:{' '}
        <strong className="font-semibold text-slate-100">
          a multi-step workflow should end fully applied or fully reverted, and the record of
          which should be independently verifiable.
        </strong>{' '}
        Everything in Triadr exists to make that true.
      </p>
    </Section>
  )
}

export function Apps() {
  return (
    <Section
      id="apps"
      eyebrow="Three connected apps"
      title="14 MCP tools, each declaring how it is undone"
      lede="Every tool publishes a real JSON Schema contract. Every tool that mutates remote state names the tool that reverses it - a structural test enforces this, so the saga guarantee cannot rot as tools are added."
    >
      <div className="grid gap-4 lg:grid-cols-3">
        {APPS.map((app) => {
          const Icon = APP_ICONS[app.id]
          return (
            <article key={app.id} className="panel flex min-w-0 flex-col p-5">
              <div className="flex items-start gap-3">
                <div className="rounded-lg border border-white/10 bg-white/[0.04] p-2">
                  <Icon className={`h-4 w-4 ${APP_TONE[app.id]}`} aria-hidden />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2">
                    <h3 className="text-[15px] font-semibold text-slate-100">{app.name}</h3>
                    <span className="font-mono text-[10px] text-slate-600">App #{app.index}</span>
                  </div>
                  <p className="text-[12px] text-slate-500">{app.role}</p>
                </div>
              </div>

              <p className="mt-3.5 text-[13px] leading-relaxed text-slate-400">{app.blurb}</p>

              <ul className="mt-4 space-y-1.5 border-t border-white/[0.06] pt-3.5">
                {app.tools.map((tool) => (
                  <li key={tool.name} className="flex items-center gap-2">
                    <code className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-slate-400">
                      {app.id}.{tool.name}
                    </code>
                    <span className={`chip shrink-0 ${EFFECT_STYLE[tool.effect]}`}>{tool.effect}</span>
                  </li>
                ))}
              </ul>

              <p className="mt-4 border-t border-white/[0.06] pt-3 font-mono text-[10.5px] text-slate-600">
                {app.credential} → LIVE · unset → SIMULATED
              </p>
            </article>
          )
        })}
      </div>

      <div className="mt-5 rounded-xl border border-white/[0.07] bg-ink-900/70 p-5">
        <h3 className="text-[14px] font-semibold text-slate-100">The workflow it composes</h3>
        <p className="mt-1.5 text-[13px] text-slate-500">
          The plan shape is fixed in code. An LLM may extract parameters - repo, amount, channel -
          but can never add, remove or reorder a step. A hallucinated second{' '}
          <code className="font-mono text-slate-400">release_escrow</code> would be a financial
          incident, so the model is not given that authority.
        </p>
        <ol className="mt-4 space-y-1">
          {STEPS.map((step) => (
            <li
              key={step.n}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-white/[0.05] bg-white/[0.02] px-3 py-2"
            >
              <span className="w-4 shrink-0 font-mono text-[11px] text-slate-600">{step.n}</span>
              <span className="w-[62px] shrink-0 text-[11px] text-slate-500">{step.app}</span>
              <span className="min-w-0 flex-1 text-[13px] text-slate-300">{step.title}</span>
              <span className="shrink-0 font-mono text-[10.5px] text-slate-600">{step.note}</span>
              {step.undo ? (
                <span className="chip shrink-0 border-signal-undo/25 bg-signal-undo/10 text-signal-undo">
                  undo · {step.undo}
                </span>
              ) : (
                <span className="chip shrink-0 border-white/10 bg-white/[0.03] text-slate-600">
                  no side effect
                </span>
              )}
            </li>
          ))}
        </ol>
      </div>
    </Section>
  )
}

export function Gate() {
  return (
    <Section
      id="gate"
      eyebrow="The reliability gate"
      title="Eight checks between the agent and the outside world"
      lede="Every call to every app goes through one function. It runs in this order, and the first four all happen before a single packet leaves the process."
      className="border-y border-white/[0.06] bg-white/[0.012]"
    >
      <ol className="grid gap-3 md:grid-cols-2">
        {GATE_STAGES.map((stage) => (
          <li key={stage.n} className="flex min-w-0 gap-3.5 rounded-xl border border-white/[0.07] bg-ink-900/70 p-4">
            <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-signal-live/25 bg-signal-live/10 font-mono text-[11px] font-semibold text-signal-live">
              {stage.n}
            </span>
            <div className="min-w-0">
              <h3 className="text-[13.5px] font-semibold text-slate-100">{stage.title}</h3>
              <p className="mt-1 text-[13px] leading-relaxed text-slate-400">{stage.body}</p>
            </div>
          </li>
        ))}
      </ol>
    </Section>
  )
}

export function Safety() {
  return (
    <Section
      id="safety"
      eyebrow="Safety"
      title="The properties that matter when an agent can move money"
    >
      <div className="overflow-x-auto rounded-xl border border-white/[0.07]">
        <table className="w-full min-w-[560px] border-collapse text-left">
          <thead>
            <tr className="border-b border-white/[0.07] bg-white/[0.02]">
              <th className="px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Property
              </th>
              <th className="px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Mechanism
              </th>
            </tr>
          </thead>
          <tbody>
            {SAFETY.map((row) => (
              <tr key={row.property} className="border-b border-white/[0.05] last:border-0">
                <td className="px-4 py-2.5 align-top">
                  <span className="flex items-start gap-2 text-[13px] font-medium text-slate-200">
                    <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-signal-ok" aria-hidden />
                    {row.property}
                  </span>
                </td>
                <td className="px-4 py-2.5 align-top text-[13px] leading-relaxed text-slate-400">
                  {row.mechanism}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-5 rounded-xl border border-signal-heal/20 bg-signal-heal/[0.04] p-5">
        <h3 className="flex items-center gap-2 text-[14px] font-semibold text-signal-heal">
          <ShieldAlert className="h-4 w-4" aria-hidden />
          Honest limitations
        </h3>
        <p className="mt-2 text-[13px] text-slate-400">
          Judges will find these anyway, so they are stated up front rather than buried.
        </p>
        <ul className="mt-3.5 space-y-2.5">
          {LIMITATIONS.map((item) => (
            <li key={item} className="flex gap-2.5 text-[13px] leading-relaxed text-slate-400">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-signal-heal" aria-hidden />
              {item}
            </li>
          ))}
        </ul>
      </div>
    </Section>
  )
}
