/**
 * The Triadr mark: a ring (the gate), a three-node waypoint path (the three
 * apps a side effect passes through), and a status dot. Used everywhere the
 * product needs a logo so nav, dashboard and footer read as one thing.
 */
export function TriadrMark({
  size = 40,
  status = true,
  className = '',
}: {
  size?: number
  /** Show the live-status dot at the ring's edge. */
  status?: boolean
  className?: string
}) {
  const dot = Math.max(5, Math.round(size * 0.22))
  return (
    <span
      className={`relative inline-grid shrink-0 place-items-center rounded-full border border-white/20 bg-ink-900 ${className}`}
      style={{ width: size, height: size }}
      aria-hidden
    >
      <svg viewBox="0 0 24 24" width={size * 0.5} height={size * 0.5} fill="none" stroke="currentColor"
           strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" className="text-slate-100">
        {/* three nodes joined by the path a side effect takes through the gate */}
        <circle cx="5" cy="17" r="2.2" />
        <circle cx="12" cy="7" r="2.2" />
        <circle cx="19" cy="17" r="2.2" />
        <path d="M6.6 15.2 10.4 9.1M13.6 9.1l3.8 6.1M7.2 17h9.6" />
      </svg>
      {status && (
        <span
          className="absolute rounded-full bg-signal-ok ring-2 ring-ink-950"
          style={{ width: dot, height: dot, right: Math.round(size * 0.02), bottom: Math.round(size * 0.02) }}
        />
      )}
    </span>
  )
}
