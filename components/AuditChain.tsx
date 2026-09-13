'use client'

import { useState } from 'react'
import { Link2, ShieldAlert, ShieldCheck } from 'lucide-react'
import type { Attestation, AuditEntry } from '@/lib/types'
import { Hash } from './primitives'

/**
 * The hash-chained evaluation log. Each row's prev_hash is the row above's
 * digest, so the "verified" badge is a recomputation, not a label.
 */
export function AuditChain({
  attestation,
  entries,
  liveCount,
}: {
  attestation: Attestation | null
  entries: AuditEntry[]
  liveCount: number
}) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded ? entries : entries.slice(-10)

  if (!attestation) {
    return (
      <div className="px-4 py-8 text-center">
        <p className="text-xs text-slate-600">
          {liveCount > 0
            ? `${liveCount} entries written - the chain is sealed when the run ends.`
            : 'Every gate decision is appended to a SHA-256 hash chain.'}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3 px-4 py-3.5">
      <div
        className={`flex items-start gap-2.5 rounded-lg border px-3 py-2.5 ${
          attestation.chain_valid
            ? 'border-signal-ok/25 bg-signal-ok/[0.06]'
            : 'border-signal-fail/25 bg-signal-fail/[0.06]'
        }`}
      >
        {attestation.chain_valid ? (
          <ShieldCheck className="mt-px h-4 w-4 shrink-0 text-signal-ok" aria-hidden />
        ) : (
          <ShieldAlert className="mt-px h-4 w-4 shrink-0 text-signal-fail" aria-hidden />
        )}
        <div className="min-w-0">
          <p className={`text-xs font-medium ${attestation.chain_valid ? 'text-signal-ok' : 'text-signal-fail'}`}>
            {attestation.chain_valid ? 'Chain verified' : 'Chain broken'} ·{' '}
            <span className="font-mono">{attestation.entry_count}</span> entries
          </p>
          <p className="mt-0.5 text-[11px] leading-relaxed text-slate-500">
            {attestation.chain_reason}. Recomputed from the entry bodies, so editing any record after
            the fact invalidates every digest that follows it.
          </p>
        </div>
      </div>

      <dl className="space-y-1 text-[11px]">
        <div className="flex items-center justify-between gap-3">
          <dt className="text-slate-500">merkle root</dt>
          <dd><Hash value={attestation.merkle_root} chars={10} /></dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt className="text-slate-500">head digest</dt>
          <dd><Hash value={attestation.head_digest} chars={10} /></dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt className="text-slate-500">signature</dt>
          <dd className="font-mono text-[11px] text-slate-500">
            {attestation.signed ? <Hash value={attestation.signature ?? ''} chars={8} /> : 'unsigned'}
          </dd>
        </div>
        <div className="flex items-center justify-between gap-3">
          <dt className="text-slate-500">outcome</dt>
          <dd
            className={`font-mono text-[11px] ${
              attestation.outcome === 'APPLIED' ? 'text-signal-ok' : 'text-signal-undo'
            }`}
          >
            {attestation.outcome ?? '-'}
          </dd>
        </div>
      </dl>

      {entries.length > 0 && (
        <div className="rounded-lg border border-white/[0.06] bg-black/25">
          <div className="flex items-center justify-between border-b border-white/[0.06] px-3 py-1.5">
            <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500">
              <Link2 className="h-3 w-3" aria-hidden /> chain
            </span>
            {entries.length > 10 && (
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="text-[10px] text-slate-500 underline-offset-2 transition-colors hover:text-slate-300 hover:underline"
              >
                {expanded ? 'show last 10' : `show all ${entries.length}`}
              </button>
            )}
          </div>
          <ul className="max-h-56 overflow-y-auto px-3 py-1.5">
            {visible.map((entry) => (
              <li key={entry.index} className="flex items-center gap-2 py-px font-mono text-[10px]">
                <span className="w-7 shrink-0 text-right text-slate-700">{entry.index}</span>
                <span className="w-[124px] shrink-0 truncate text-slate-500">{entry.kind}</span>
                <span className="w-14 shrink-0 truncate text-slate-600">{entry.app ?? ''}</span>
                <span className="min-w-0 flex-1 truncate text-slate-700" title={entry.digest}>
                  {entry.digest.slice(0, 24)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="text-[10px] leading-relaxed text-slate-600">
        Verify independently:{' '}
        <code className="font-mono text-slate-500">python3 main.py --verify .triadr/{attestation.run_id}.jsonl</code>
      </p>
    </div>
  )
}
