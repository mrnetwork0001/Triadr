'use client'

import Link from 'next/link'
import { Activity, ArrowUpRight, ListTree, Radio, ScrollText, ShieldCheck, Terminal } from 'lucide-react'
import { BrandHeader } from '@/components/BrandHeader'
import { BrandLogo } from '@/components/BrandLogo'
import { APP_META } from '@/components/primitives'
import type { AppStatus } from '@/lib/types'

export const DASHBOARD_SECTIONS = [
  { id: 'console', label: 'Run console', icon: Terminal },
  { id: 'execution', label: 'Execution', icon: ListTree },
  { id: 'reliability', label: 'Reliability', icon: Activity },
  { id: 'events', label: 'Gate events', icon: Radio },
  { id: 'audit', label: 'Audit log', icon: ShieldCheck },
] as const

export type SectionId = (typeof DASHBOARD_SECTIONS)[number]['id']

/**
 * Left rail: brand, section navigation with scroll-spy highlighting, the three
 * connected apps with their live/simulated state, and the control-plane status.
 */
type SidebarProps = {
  apps: AppStatus[]
  apiUp: boolean | null
  toolCount: number
  activeId: SectionId
  running: boolean
  /** Called when a section link is chosen - the mobile sheet closes itself. */
  onNavigate?: () => void
}

export function Sidebar(props: SidebarProps) {
  return (
    <aside className="hidden lg:flex lg:sticky lg:top-0 lg:h-screen lg:w-[248px] lg:shrink-0 lg:flex-col lg:border-r lg:border-white/[0.07] lg:bg-ink-950/80">
      <div className="flex h-[72px] items-center border-b border-white/[0.07] px-5">
        <Link href="/" aria-label="Triadr home" className="flex items-center">
          <BrandHeader height={40} />
        </Link>
      </div>
      <SidebarContent {...props} />
    </aside>
  )
}

/** Navigation, connected apps and control-plane status - shared by the rail and the mobile sheet. */
export function SidebarContent({ apps, apiUp, toolCount, activeId, running, onNavigate }: SidebarProps) {
  return (
    <>
      <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="Dashboard sections">
        <p className="px-3 pb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-600">Console</p>
        <ul className="space-y-0.5">
          {DASHBOARD_SECTIONS.map(({ id, label, icon: Icon }) => {
            const active = id === activeId
            return (
              <li key={id}>
                <a
                  href={`#${id}`}
                  onClick={onNavigate}
                  aria-current={active ? 'location' : undefined}
                  className={`group flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-colors ${
                    active
                      ? 'bg-signal-live/10 text-signal-live'
                      : 'text-slate-400 hover:bg-white/[0.04] hover:text-slate-200'
                  }`}
                >
                  <Icon className={`h-3.5 w-3.5 ${active ? 'text-signal-live' : 'text-slate-500 group-hover:text-slate-300'}`} aria-hidden />
                  <span className="flex-1">{label}</span>
                  {id === 'events' && running && (
                    <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-signal-live" aria-hidden />
                  )}
                </a>
              </li>
            )
          })}
        </ul>

        <p className="px-3 pb-2 pt-6 text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-600">Connected apps</p>
        <ul className="space-y-0.5">
          {apps.map((app, i) => {
            const meta = APP_META[app.app] ?? { label: app.app, role: '' }
            const live = app.mode === 'LIVE'
            return (
              <li key={app.app} className="flex items-center gap-2.5 rounded-lg px-3 py-2">
                <BrandLogo app={app.app} size={20} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] text-slate-300">{meta.label}</span>
                  <span className="block text-[10px] text-slate-600">App #{i + 1} · {meta.role}</span>
                </span>
                <span
                  className={`h-1.5 w-1.5 shrink-0 rounded-full ${live ? 'bg-signal-ok' : 'bg-slate-600'}`}
                  title={live ? 'live' : 'simulated'}
                  aria-label={live ? 'live' : 'simulated'}
                />
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="space-y-2 border-t border-white/[0.07] px-5 py-4 text-[11px]">
        <div className="flex items-center justify-between text-slate-500">
          <span>Control plane</span>
          <span className={`flex items-center gap-1.5 ${apiUp === false ? 'text-signal-fail' : apiUp ? 'text-signal-ok' : 'text-slate-500'}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${apiUp === false ? 'bg-signal-fail' : apiUp ? 'bg-signal-ok' : 'bg-slate-600'}`} />
            {apiUp === false ? 'offline' : apiUp ? 'online' : 'connecting'}
          </span>
        </div>
        <div className="flex items-center justify-between text-slate-500">
          <span>MCP tools</span>
          <span className="font-mono text-slate-300">{toolCount}</span>
        </div>
        <Link
          href="/"
          className="mt-1 flex items-center gap-1 text-slate-500 transition-colors hover:text-slate-200"
        >
          Back to site <ArrowUpRight className="h-3 w-3" aria-hidden />
        </Link>
      </div>
    </>
  )
}
