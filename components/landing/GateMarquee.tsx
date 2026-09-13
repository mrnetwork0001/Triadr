'use client'

import { BrandLogo } from '@/components/BrandLogo'
import { GATE_FEED, type GateCard } from '@/lib/landing-content'

/** Verdicts read at a glance: green applied, amber healed/faulted, purple undone. */
const VERDICT_STYLE: Record<string, { chip: string; dot: string; label: string }> = {
  ALLOW: { chip: 'border-signal-ok/25 bg-signal-ok/10 text-signal-ok', dot: 'bg-signal-ok', label: 'applied' },
  SELF_HEALED: { chip: 'border-signal-heal/25 bg-signal-heal/10 text-signal-heal', dot: 'bg-signal-heal', label: 'self-healed' },
  DEDUPED: { chip: 'border-signal-ok/25 bg-signal-ok/10 text-signal-ok', dot: 'bg-signal-ok', label: 'deduped' },
  BLOCKED: { chip: 'border-signal-live/25 bg-signal-live/10 text-signal-live', dot: 'bg-signal-live', label: 'blocked' },
  ROLLED_BACK: { chip: 'border-signal-undo/25 bg-signal-undo/10 text-signal-undo', dot: 'bg-signal-undo', label: 'rolled back' },
}

const FAULT_STYLE = {
  chip: 'border-signal-fail/25 bg-signal-fail/10 text-signal-fail',
  dot: 'bg-signal-fail',
}

function styleFor(verdict: string) {
  return (
    VERDICT_STYLE[verdict] ?? {
      ...FAULT_STYLE,
      label: verdict.toLowerCase().replace(/_/g, ' '),
    }
  )
}

function Card({ card }: { card: GateCard }) {
  const style = styleFor(card.verdict)
  const isFault = !VERDICT_STYLE[card.verdict]

  return (
    <article className="rounded-lg border border-white/[0.07] bg-ink-900/80 px-3 py-2.5 backdrop-blur-sm">
      <div className="flex items-center gap-2">
        <BrandLogo app={card.app} size={14} className="rounded-[30%]" />
        <code className="min-w-0 flex-1 truncate font-mono text-[11px] text-slate-300">{card.tool}</code>
        <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${style.dot}`} aria-hidden />
      </div>
      <div className="mt-1.5 flex items-end justify-between gap-2">
        <p
          className={`min-w-0 flex-1 truncate text-[10.5px] ${
            isFault ? 'font-mono text-slate-500' : 'text-slate-500'
          }`}
          title={card.detail}
        >
          {card.detail}
        </p>
        <span className="shrink-0 font-mono text-[10px] tabular-nums text-slate-600">{card.metric}</span>
      </div>
      <div className="mt-2">
        <span className={`chip ${style.chip}`}>{style.label}</span>
      </div>
    </article>
  )
}

/**
 * One vertical marquee column. The track holds the list twice, so animating it
 * by exactly half its height loops seamlessly.
 */
function Column({ cards, direction }: { cards: GateCard[]; direction: 'up' | 'down' }) {
  return (
    <div className="marquee-col relative h-full overflow-hidden">
      <div
        className={`marquee-track flex flex-col gap-2.5 ${
          direction === 'up' ? 'marquee-up' : 'marquee-down'
        }`}
      >
        {[...cards, ...cards].map((card, i) => (
          <Card key={`${card.tool}-${card.verdict}-${i}`} card={card} />
        ))}
      </div>
    </div>
  )
}

export function GateMarquee() {
  // Split so the two columns never show the same card side by side.
  const mid = Math.ceil(GATE_FEED.length / 2)
  const left = GATE_FEED.slice(0, mid)
  const right = GATE_FEED.slice(mid)

  return (
    <div>
      {/* The fades are scoped to this wrapper so they never wash out the caption. */}
      <div className="relative">
        <div
          className="grid h-[380px] grid-cols-2 gap-2.5 sm:h-[440px]"
          // Decorative repetition of what the copy already states; a screen reader
          // should not have to wade through 48 looping cards.
          aria-hidden
        >
          <Column cards={left} direction="up" />
          <Column cards={right} direction="down" />
        </div>

        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-20 bg-gradient-to-b from-ink-950 via-ink-950/70 to-transparent"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-ink-950 via-ink-950/70 to-transparent"
        />
      </div>

      <p className="mt-3.5 text-center text-[11px] text-slate-600">
        Real decisions from a chaos run and a rollback run · hover to pause
      </p>
    </div>
  )
}
