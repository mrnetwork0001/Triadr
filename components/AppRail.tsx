'use client'

import { Radio, FlaskConical } from 'lucide-react'
import { BrandLogo } from '@/components/BrandLogo'
import type { AppStatus, RouteHealth } from '@/lib/types'
import { APP_META, Chip } from './primitives'

const BREAKER_TONE: Record<string, string> = {
  CLOSED: 'bg-signal-ok',
  HALF_OPEN: 'bg-signal-heal',
  OPEN: 'bg-signal-fail',
}

/**
 * The three connected apps, each showing live/simulated mode plus the health of
 * its MCP gateways. When the gate reroutes, the endpoint bars re-rank live.
 */
export function AppRail({
  apps,
  routes,
  activeApp,
}: {
  apps: AppStatus[]
  routes: Record<string, RouteHealth[]>
  activeApp: string | null
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {apps.map((app, index) => {
        const meta = APP_META[app.app] ?? { label: app.app, role: '', accent: 'text-slate-200' }
        const endpoints = routes[app.app] ?? []
        const isActive = activeApp === app.app
        return (
          <article
            key={app.app}
            className={`panel min-w-0 overflow-hidden transition-colors duration-300 ${
              isActive ? 'border-signal-live/40 bg-signal-live/[0.04]' : ''
            }`}
          >
            <div className="flex items-start gap-3 px-4 pb-3 pt-3.5">
              <BrandLogo app={app.app} size={36} className="mt-0.5" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="truncate text-sm font-semibold text-slate-100">{meta.label}</h3>
                  <span className="text-[10px] font-medium text-slate-600">App #{index + 1}</span>
                </div>
                <p className="mt-0.5 text-xs text-slate-500">{meta.role}</p>
              </div>
              {app.mode === 'LIVE' ? (
                <Chip tone="ok">
                  <Radio className="h-2.5 w-2.5" aria-hidden /> live
                </Chip>
              ) : (
                <Chip tone="idle">
                  <FlaskConical className="h-2.5 w-2.5" aria-hidden /> simulated
                </Chip>
              )}
            </div>

            <div className="flex items-center gap-4 border-t border-white/[0.06] px-4 py-2 text-[11px] text-slate-500">
              <span>
                <span className="font-mono text-slate-300">{app.tools}</span> tools
              </span>
              <span>
                <span className="font-mono text-slate-300">{app.calls}</span> calls
              </span>
              {isActive && (
                <span className="ml-auto flex items-center gap-1.5 text-signal-live">
                  <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-signal-live" />
                  active
                </span>
              )}
            </div>

            {endpoints.length > 0 && (
              <div className="space-y-1.5 border-t border-white/[0.06] px-4 py-2.5">
                {endpoints.map((route) => (
                  <div key={route.url} className="flex items-center gap-2">
                    <span
                      className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                        BREAKER_TONE[route.breaker.state] ?? 'bg-slate-600'
                      }`}
                      title={`circuit ${route.breaker.state.toLowerCase()}`}
                    />
                    <code className="min-w-0 flex-1 truncate font-mono text-[10px] text-slate-500">
                      {route.url.replace(/^https?:\/\//, '')}
                    </code>
                    <div className="h-1 w-14 overflow-hidden rounded-full bg-white/[0.06]">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          route.score > 0.6 ? 'bg-signal-ok' : route.score > 0.25 ? 'bg-signal-heal' : 'bg-signal-fail'
                        }`}
                        style={{ width: `${Math.max(4, route.score * 100)}%` }}
                      />
                    </div>
                    <span className="w-7 shrink-0 text-right font-mono text-[10px] tabular-nums text-slate-600">
                      {route.failures > 0 ? `${route.failures} fail` : '·'}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {app.credentials_missing.length > 0 && (
              <p className="border-t border-white/[0.06] px-4 py-2 text-[10px] text-slate-600">
                set <code className="font-mono text-slate-500">{app.credentials_missing.join(', ')}</code> for live mode
              </p>
            )}
          </article>
        )
      })}
    </div>
  )
}
