'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { FlaskConical, Radio, Terminal } from 'lucide-react'
import { fetchApps } from '@/lib/api'
import { CAMPAIGN, DEFAULT_INSTRUCTION } from '@/lib/landing-content'
import type { AppStatus } from '@/lib/types'
import { LaunchButton } from './chrome'
import { GateMarquee } from './GateMarquee'

const HEADLINE_STATS = [
  { value: CAMPAIGN.faultsAbsorbed.toString(), label: 'faults absorbed', tone: 'text-signal-heal' },
  { value: CAMPAIGN.stepsSelfHealed.toString(), label: 'steps self-healed', tone: 'text-signal-ok' },
  { value: CAMPAIGN.halfExecuted.toString(), label: 'left half-executed', tone: 'text-slate-50' },
  { value: `${CAMPAIGN.chainsValid}/${CAMPAIGN.runs}`, label: 'audit chains verify', tone: 'text-signal-live' },
]

export function Hero() {
  // The landing page must stand alone with the control plane down, so live
  // status is an enhancement: static content renders either way.
  const [apps, setApps] = useState<AppStatus[] | null>(null)
  const [instruction, setInstruction] = useState(DEFAULT_INSTRUCTION)

  useEffect(() => {
    let cancelled = false
    fetchApps()
      .then((data) => {
        if (cancelled) return
        setApps(data.apps)
        if (data.default_instruction) setInstruction(data.default_instruction)
      })
      .catch(() => undefined) // control plane down: the strip simply does not render
    return () => {
      cancelled = true
    }
  }, [])

  const liveCount = apps?.filter((a) => a.mode === 'LIVE').length ?? 0

  return (
    <section className="relative overflow-hidden px-4 pb-16 pt-12 sm:px-6 sm:pb-20 sm:pt-16">
      {/* Horizon glow, kept behind content and non-interactive. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[560px] bg-[radial-gradient(760px_340px_at_35%_-10%,rgba(56,189,248,0.16),transparent_70%)]"
      />

      <div className="shell relative">
        <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] lg:gap-12">
          {/* ── Left: the pitch ─────────────────────────────────────────── */}
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
            className="min-w-0"
          >
            <h1 className="text-balance text-[34px] font-semibold leading-[1.08] tracking-tight text-slate-50 sm:text-[44px] xl:text-[50px]">
              A multi-app agent that is never left{' '}
              <span className="text-signal-heal">half-executed</span>.
            </h1>

            <p className="mt-5 text-pretty text-[15.5px] leading-relaxed text-slate-400 sm:text-[16px]">
              Triadr runs one business workflow across three external applications - auditing a
              pull request on GitHub, collecting team sign-off in Telegram, releasing an escrow
              payout through Stripe. Every side effect passes through a gate that retries,
              reroutes, deduplicates and, when a step is genuinely unrecoverable, rolls the whole
              workflow back.
            </p>

            <div className="mt-7 flex flex-wrap items-center gap-3">
              <LaunchButton size="lg" />
              <a
                href="#problem"
                className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.03] px-5 py-3 text-[15px] text-slate-300 transition-colors hover:bg-white/[0.07]"
              >
                How it works
              </a>
            </div>

            <div className="mt-5 flex items-start gap-2 rounded-lg border border-white/[0.07] bg-black/30 px-3.5 py-2.5">
              <Terminal className="mt-0.5 h-3.5 w-3.5 shrink-0 text-slate-600" aria-hidden />
              <div className="min-w-0">
                <code className="block break-words font-mono text-[11.5px] leading-relaxed text-slate-400">
                  {instruction}
                </code>
                <p className="mt-1 text-[11px] text-slate-600">
                  One sentence in. Six gate-supervised steps out.
                </p>
              </div>
            </div>
          </motion.div>

          {/* ── Right: what the gate actually did ───────────────────────── */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.15, ease: 'easeOut' }}
            className="min-w-0"
          >
            <GateMarquee />
          </motion.div>
        </div>

        {/* ── Headline evidence ──────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.24, ease: 'easeOut' }}
          className="mt-14"
        >
          <p className="mb-3 text-[12px] text-slate-500">
            Across {CAMPAIGN.runs} runs at a {CAMPAIGN.faultRate} first-attempt failure rate:
          </p>
          <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {HEADLINE_STATS.map((stat) => (
              <div
                key={stat.label}
                className="min-w-0 rounded-xl border border-white/[0.07] bg-ink-900/70 px-4 py-3.5"
              >
                <dt className="sr-only">{stat.label}</dt>
                <dd>
                  <span className={`block font-mono text-[30px] font-semibold tabular-nums leading-none ${stat.tone}`}>
                    {stat.value}
                  </span>
                  <span className="mt-2 block text-[11px] uppercase tracking-[0.12em] text-slate-500">
                    {stat.label}
                  </span>
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 font-mono text-[11px] text-slate-600">reproduce · {CAMPAIGN.command}</p>
        </motion.div>

        {/* ── Live connection strip ──────────────────────────────────────── */}
        {apps && (
          <div className="mt-6 flex flex-wrap items-center gap-2 text-[11px]">
            <span className="text-slate-600">connected apps:</span>
            {apps.map((app) => (
              <span
                key={app.app}
                className={`chip ${
                  app.mode === 'LIVE'
                    ? 'border-signal-ok/30 bg-signal-ok/10 text-signal-ok'
                    : 'border-white/10 bg-white/[0.04] text-slate-400'
                }`}
              >
                {app.mode === 'LIVE' ? (
                  <Radio className="h-2.5 w-2.5" aria-hidden />
                ) : (
                  <FlaskConical className="h-2.5 w-2.5" aria-hidden />
                )}
                {app.app} · {app.mode.toLowerCase()}
              </span>
            ))}
            {liveCount === 0 && (
              <span className="text-slate-600">- no credentials needed to run the full demo</span>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
