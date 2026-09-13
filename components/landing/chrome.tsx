'use client'

import Link from 'next/link'
import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Github, Menu, X } from 'lucide-react'
import { BrandHeader } from '@/components/BrandHeader'
import { SectionGlow, type GlowTone } from './Backdrop'
import { DrawLine, Reveal } from './motion'

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
  const [open, setOpen] = useState(false)

  // Escape closes the sheet; a resize past the breakpoint discards it.
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    const onResize = () => window.innerWidth >= 768 && setOpen(false)
    window.addEventListener('keydown', onKey)
    window.addEventListener('resize', onResize)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', onResize)
    }
  }, [open])

  return (
    <header className="sticky top-0 z-50 border-b border-white/[0.07] bg-ink-950/80 backdrop-blur-md">
      <div className="shell-wide relative flex h-16 items-center gap-4">
        <Link href="/" className="flex shrink-0 items-center" aria-label="Triadr home" onClick={() => setOpen(false)}>
          <BrandHeader height={45} />
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

        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label={open ? 'Close menu' : 'Open menu'}
          className="ml-auto grid h-10 w-10 place-items-center rounded-lg border border-white/10 bg-white/[0.03] text-slate-200 transition-colors hover:bg-white/[0.07] md:hidden"
        >
          {open ? <X className="h-4.5 w-4.5" aria-hidden /> : <Menu className="h-5 w-5" aria-hidden />}
        </button>
      </div>

      <AnimatePresence>
        {open && (
          <motion.nav
            id="mobile-nav"
            aria-label="Sections"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className="absolute inset-x-0 top-full border-b border-white/[0.08] bg-ink-950/95 backdrop-blur-md md:hidden"
          >
            <ul className="px-4 py-3">
              {NAV.map((item) => (
                <li key={item.href}>
                  <a
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className="block rounded-lg px-3 py-3 text-[15px] text-slate-200 transition-colors hover:bg-white/[0.05]"
                  >
                    {item.label}
                  </a>
                </li>
              ))}
              <li className="mt-2 border-t border-white/[0.07] px-3 pt-4 pb-1">
                <span onClick={() => setOpen(false)}>
                  <LaunchButton size="md" />
                </span>
              </li>
            </ul>
          </motion.nav>
        )}
      </AnimatePresence>
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
    <footer className="relative border-t border-white/[0.08] bg-ink-950">
      <div className="shell px-4 py-14 sm:px-6 sm:py-16">
        <div className="grid gap-12 lg:grid-cols-[1.5fr_1fr_1fr_1fr] lg:gap-8">
          {/* ── Brand ─────────────────────────────────────────────── */}
          <div className="max-w-sm">
            <Link href="/" className="inline-flex items-center" aria-label="Triadr home">
              <BrandHeader height={66} />
            </Link>

            <p className="mt-6 text-[14px] leading-relaxed text-slate-400">
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
              <h3 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-signal-live">
                {column.heading}
              </h3>
              <ul className="mt-3 space-y-1">
                {column.links.map((link) => (
                  <li key={link.label}>
                    {link.external ? (
                      <a
                        href={link.href}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[13.5px] text-slate-400 transition-colors hover:text-slate-100"
                      >
                        {link.label}
                      </a>
                    ) : (
                      <Link
                        href={link.href}
                        className="text-[13.5px] text-slate-400 transition-colors hover:text-slate-100"
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

/** Consistent section wrapper: numbered anchor target, eyebrow, heading, lede - all revealed on scroll. */
const TONES: GlowTone[] = ['purple', 'sky', 'green', 'amber', 'sky', 'purple', 'amber', 'green']

export function Section({
  id,
  index,
  eyebrow,
  title,
  lede,
  children,
  className = '',
  glow,
}: {
  id?: string
  index?: string
  eyebrow?: string
  title: string
  lede?: string
  children: React.ReactNode
  className?: string
  glow?: GlowTone
}) {
  const n = Number.parseInt(index ?? '1', 10) || 1
  const tone = glow ?? TONES[(n - 1) % TONES.length]
  const side = n % 2 === 0 ? 'right' : 'left'
  return (
    <section id={id} className={`relative scroll-mt-24 overflow-hidden px-4 py-16 sm:px-6 sm:py-24 ${className}`}>
      <span className="signal-rule" aria-hidden style={{ animationDelay: `${-(n * 2.3)}s` }} />
      <SectionGlow tone={tone} side={side} />
      <div className="shell relative">
        <Reveal className="max-w-3xl">
          <div className="flex items-center gap-3">
            {index && <span className="font-mono text-[11px] tabular-nums text-slate-600">{index}</span>}
            {eyebrow && (
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-signal-live">{eyebrow}</p>
            )}
          </div>
          <DrawLine className="mt-3 w-16 bg-signal-live/60" />
          <h2 className="mt-5 text-balance text-[26px] font-semibold leading-[1.15] tracking-tight text-slate-50 sm:text-[34px]">
            {title}
          </h2>
          {lede && <p className="mt-4 text-pretty text-[15.5px] leading-relaxed text-slate-400">{lede}</p>}
        </Reveal>
        <div className="mt-10 sm:mt-12">{children}</div>
      </div>
    </section>
  )
}
