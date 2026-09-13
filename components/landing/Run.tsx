'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import { Check, Copy, Plug, Terminal } from 'lucide-react'
import { Section, LaunchButton } from './chrome'
import { Reveal, Stagger, itemVariants } from './motion'

function CodeBlock({ label, lines }: { label: string; lines: string[] }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(lines.filter((l) => !l.startsWith('#') && l.trim()).join('\n'))
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      /* clipboard can be blocked; the text is selectable either way */
    }
  }

  return (
    <div className="card-lift overflow-hidden rounded-2xl border border-white/[0.07] bg-black/35">
      <div className="flex items-center justify-between gap-3 border-b border-white/[0.06] px-4 py-2.5">
        <span className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.12em] text-slate-500">
          <Terminal className="h-3 w-3" aria-hidden />
          {label}
        </span>
        <button
          type="button"
          onClick={copy}
          className="flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] text-slate-500 transition-colors hover:bg-white/[0.06] hover:text-slate-300"
        >
          {copied ? <Check className="h-3 w-3 text-signal-ok" aria-hidden /> : <Copy className="h-3 w-3" aria-hidden />}
          {copied ? 'copied' : 'copy'}
        </button>
      </div>
      <pre className="overflow-x-auto px-4 py-3.5">
        <code className="font-mono text-[12px] leading-relaxed">
          {lines.map((line, i) => (
            <span key={i} className={`block ${line.startsWith('#') ? 'text-slate-600' : 'text-slate-300'}`}>
              {line || ' '}
            </span>
          ))}
        </code>
      </pre>
    </div>
  )
}

/* ── 08 · Run it ──────────────────────────────────────────────────────────── */

export function RunIt() {
  return (
    <Section
      id="run"
      index="08"
      eyebrow="Run it"
      title="No credentials required"
      lede="Every app falls back to a deterministic simulator and says so, so the full demo runs offline. Adding a token switches that app to LIVE with no code change."
    >
      <Stagger className="grid gap-4 lg:grid-cols-2" gap={0.1}>
        <motion.div variants={itemVariants} className="min-w-0 space-y-4">
          <CodeBlock
            label="The agent, end to end"
            lines={[
              '# stdlib only - no pip install needed',
              'python3 main.py --scenario all',
              '',
              '# the test suite and the reliability campaign',
              'python3 -m pytest tests/ -q',
              'python3 scripts/campaign.py --runs 40',
            ]}
          />
          <CodeBlock
            label="The live visualiser"
            lines={[
              'python3 -m venv .venv',
              '.venv/bin/pip install -r requirements.txt',
              '',
              '# terminal 1 - control plane',
              '.venv/bin/uvicorn server:app --port 8000',
              '',
              '# terminal 2 - dashboard',
              'npm install && npm run dev',
            ]}
          />
        </motion.div>

        <motion.div variants={itemVariants} className="min-w-0 space-y-4">
          <article className="card-lift panel rounded-2xl p-6">
            <h3 className="flex items-center gap-2 text-[15px] font-semibold text-slate-100">
              <Plug className="h-4 w-4 text-signal-live" aria-hidden />
              Use Triadr as an MCP server
            </h3>
            <p className="mt-2 text-[13.5px] leading-relaxed text-slate-400">
              All 14 tools are exposed over the standard MCP stdio transport, dependency-free. Every
              call an MCP host makes is gate-supervised, so the host inherits retry, rerouting,
              idempotency and rollback for free.
            </p>
            <div className="mt-4 overflow-x-auto rounded-lg border border-white/[0.06] bg-black/30 px-3 py-2">
              <code className="whitespace-nowrap font-mono text-[11.5px] text-slate-400">
                claude mcp add triadr -- python3 /path/to/Triadr/mcp_servers/stdio_server.py
              </code>
            </div>
          </article>

          <article className="card-lift panel flex min-w-0 flex-col justify-between gap-4 rounded-2xl p-6 sm:flex-row sm:items-center">
            <div>
              <h3 className="text-[15px] font-semibold text-slate-100">Or just watch it run</h3>
              <p className="mt-2 max-w-sm text-[13.5px] leading-relaxed text-slate-400">
                The dashboard streams every gate decision live - retries, reroutes, circuit
                breakers, rollbacks and the hash chain sealing itself as the run completes.
              </p>
            </div>
            <LaunchButton size="lg" />
          </article>
        </motion.div>
      </Stagger>
    </Section>
  )
}

export function ClosingCta() {
  return (
    <section className="px-4 pb-20 pt-6 sm:px-6">
      <div className="shell">
        <Reveal>
          <div className="relative overflow-hidden rounded-3xl border border-white/[0.08] bg-ink-900/70 px-6 py-14 text-center sm:px-10 sm:py-20">
            <motion.div
              aria-hidden
              className="pointer-events-none absolute inset-0 bg-[radial-gradient(640px_260px_at_50%_0%,rgba(56,189,248,0.16),transparent_70%)]"
              animate={{ opacity: [0.7, 1, 0.7] }}
              transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
            />
            <div className="relative">
              <h2 className="text-balance text-[28px] font-semibold tracking-tight text-slate-50 sm:text-[36px]">
                Watch it heal a workflow in real time
              </h2>
              <p className="mx-auto mt-4 max-w-xl text-pretty text-[15.5px] leading-relaxed text-slate-400">
                Pick a scenario, run the agent, and follow every retry, reroute and rollback as it
                streams - then verify the hash chain yourself.
              </p>
              <div className="mt-8 flex justify-center">
                <LaunchButton size="lg" label="Launch app" />
              </div>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  )
}
