'use client'

import Link from 'next/link'
import { Github } from 'lucide-react'
import { TriadrMark } from '@/components/TriadrMark'

/** The primary call to action. Repeated at the top, in the hero, and at the foot. */
export function LaunchButton({
  size = 'md',
  label = 'Launch app',
}: {
  size?: 'sm' | 'md' | 'lg'
  label?: string
}) {
  const sizes = {
    sm: 'px-3.5 py-1.5 text-[12px]',
    md: 'px-4 py-2 text-[13px]',
    lg: 'px-6 py-3 text-[15px]',
  }
  return (
    <Link
      href="/dashboard"
      className={`inline-flex shrink-0 items-center justify-center rounded-lg border border-signal-live/40 bg-signal-live/10 font-medium text-signal-live transition-colors hover:border-signal-live/60 hover:bg-signal-live/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-signal-live/50 ${sizes[size]}`}
    >
      {label}
    </Link>
  )
}

const NAV = [
  { href: '#problem', label: 'Problem' },
  { href: '#apps', label: 'Apps' },
  { href: '#gate', label: 'The gate' },
  { href: '#evidence', label: 'Evidence' },
  { href: '#run', label: 'Run it' },
]

export function SiteNav() {
  return (
    <header className="sticky top-0 z-50 border-b border-white/[0.07] bg-ink-950/80 backdrop-blur-md">
      <div className="shell-wide flex h-14 items-center gap-4">
        <Link href="/" className="flex shrink-0 items-center gap-2.5">
          <TriadrMark size={28} />
          <span className="text-[15px] font-semibold tracking-tight text-slate-50">Triadr</span>
        </Link>

        <nav className="ml-auto hidden items-center gap-1 md:flex" aria-label="Sections">
          {NAV.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="rounded-md px-2.5 py-1.5 text-[12.5px] text-slate-400 transition-colors hover:bg-white/[0.05] hover:text-slate-200"
            >
              {item.label}
            </a>
          ))}
        </nav>
      </div>
    </header>
  )
}

const FOOTER_COLUMNS: { heading: string; links: { label: string; href: string; external?: boolean }[] }[] = [
  {
    heading: 'Product',
    links: [
      { label: 'Launch app', href: '/dashboard' },
      { label: 'How it works', href: '#problem' },
      { label: 'The gate', href: '#gate' },
      { label: 'Scenarios', href: '#scenarios' },
    ],
  },
  {
    heading: 'Engine',
    links: [
      { label: 'Reliability evidence', href: '#evidence' },
      { label: 'Audit log', href: '#audit' },
      { label: 'Safety', href: '#safety' },
      { label: 'MCP server', href: '#run' },
    ],
  },
  {
    heading: 'Resources',
    links: [
      { label: 'GitHub', href: 'https://github.com/mrnetwork0001', external: true },
      { label: 'Telegram bot', href: 'https://t.me/TriadrBot', external: true },
      { label: 'Reliability brief', href: '#evidence' },
      { label: 'Run it locally', href: '#run' },
    ],
  },
]

const SOCIALS = [
  {
    label: 'X',
    href: 'https://x.com/encrypt_wizard',
    icon: (
      <svg viewBox="0 0 24 24" className="h-[15px] w-[15px]" fill="currentColor" aria-hidden>
        <path d="M18.244 2H21.5l-7.5 8.57L22.82 22h-6.9l-5.4-7.06L4.34 22H1.08l8.02-9.17L.5 2h7.08l4.88 6.45L18.24 2Zm-1.21 18h1.8L7.05 3.9H5.12L17.03 20Z" />
      </svg>
    ),
  },
  {
    label: 'Telegram',
    href: 'https://t.me/TriadrBot',
    icon: (
      <svg viewBox="0 0 24 24" className="h-[15px] w-[15px]" fill="currentColor" aria-hidden>
        <path d="M21.9 4.2 18.7 19.4c-.24 1.06-.87 1.32-1.76.82l-4.87-3.59-2.35 2.26c-.26.26-.48.48-.98.48l.35-4.96 9.03-8.16c.39-.35-.09-.55-.61-.2L6.35 13.1 1.55 11.6c-1.04-.33-1.06-1.04.22-1.54L20.55 2.8c.87-.32 1.63.2 1.35 1.4Z" />
      </svg>
    ),
  },
  {
    label: 'GitHub',
    href: 'https://github.com/mrnetwork0001',
    icon: <Github className="h-[15px] w-[15px]" aria-hidden />,
  },
]

export function SiteFooter() {
  return (
    <footer className="footer-grid relative border-t border-white/[0.08]">
      <div className="shell px-4 py-14 sm:px-6 sm:py-16">
        <div className="grid gap-12 lg:grid-cols-[1.5fr_1fr_1fr_1fr] lg:gap-8">
          {/* ── Brand ─────────────────────────────────────────────── */}
          <div className="max-w-sm">
            <Link href="/" className="inline-flex items-center gap-4">
              <TriadrMark size={48} />
              <span className="h-10 w-px bg-white/15" aria-hidden />
              <span>
                <span className="block text-[15px] font-semibold uppercase tracking-[0.32em] text-slate-50">
                  Triadr
                </span>
                <span className="mt-0.5 block font-mono text-[9px] uppercase tracking-[0.28em] text-slate-500">
                  Reliability engine
                </span>
              </span>
            </Link>

            <p className="mt-7 text-[15px] leading-relaxed text-slate-400">
              A self-healing multi-step agent across GitHub, Telegram and Stripe. Every side
              effect passes a gate that retries, reroutes, deduplicates and rolls back - and
              every decision lands on a hash chain you can verify yourself.
            </p>

            <ul className="mt-7 flex items-center gap-3">
              {SOCIALS.map((social) => (
                <li key={social.label}>
                  <a
                    href={social.href}
                    target="_blank"
                    rel="noreferrer"
                    aria-label={social.label}
                    className="grid h-9 w-9 place-items-center rounded-full border border-white/12 bg-ink-900 text-slate-300 transition-colors hover:border-white/30 hover:text-slate-50"
                  >
                    {social.icon}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          {/* ── Link columns ───────────────────────────────────────── */}
          {FOOTER_COLUMNS.map((column) => (
            <nav key={column.heading} aria-label={column.heading}>
              <h3 className="font-mono text-[11px] uppercase tracking-[0.28em] text-signal-heal">
                {column.heading}
              </h3>
              <ul className="mt-6 space-y-3.5">
                {column.links.map((link) => (
                  <li key={link.label}>
                    {link.external ? (
                      <a
                        href={link.href}
                        target="_blank"
                        rel="noreferrer"
                        className="font-mono text-[15px] text-slate-300 transition-colors hover:text-slate-50"
                      >
                        {link.label}
                      </a>
                    ) : (
                      <Link
                        href={link.href}
                        className="font-mono text-[15px] text-slate-300 transition-colors hover:text-slate-50"
                      >
                        {link.label}
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

      </div>
    </footer>
  )
}

/** Consistent section wrapper: anchor target, eyebrow, heading, lede. */
export function Section({
  id,
  eyebrow,
  title,
  lede,
  children,
  className = '',
}: {
  id?: string
  eyebrow?: string
  title: string
  lede?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section id={id} className={`scroll-mt-20 px-4 py-14 sm:px-6 sm:py-16 ${className}`}>
      <div className="shell">
        <div className="max-w-3xl">
          {eyebrow && (
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-signal-live">
              {eyebrow}
            </p>
          )}
          <h2 className="text-balance text-2xl font-semibold tracking-tight text-slate-50 sm:text-[28px]">
            {title}
          </h2>
          {lede && <p className="mt-3 text-pretty text-[15px] leading-relaxed text-slate-400">{lede}</p>}
        </div>
        <div className="mt-8">{children}</div>
      </div>
    </section>
  )
}
