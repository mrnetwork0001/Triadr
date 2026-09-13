import type { Metadata } from 'next'
import { Backdrop } from '@/components/landing/Backdrop'
import { SiteFooter, SiteNav } from '@/components/landing/chrome'
import { AuditLog, Evidence, Scenarios } from '@/components/landing/Evidence'
import { Hero } from '@/components/landing/Hero'
import { ClosingCta, RunIt } from '@/components/landing/Run'
import { Apps, Gate, Problem, Safety } from '@/components/landing/Sections'

export const metadata: Metadata = {
  title: 'Triadr - Self-Healing Multi-App Agent & Reliability Engine',
  description:
    'One agent across GitHub, Telegram and Stripe, behind a gate that retries, reroutes, deduplicates and rolls back - so a multi-step workflow is never left half-executed.',
}

export default function LandingPage() {
  return (
    <>
      <Backdrop />
      <SiteNav />
      <main>
        <Hero />
        <Problem />
        <Apps />
        <Gate />
        <Scenarios />
        <Evidence />
        <AuditLog />
        <Safety />
        <RunIt />
        <ClosingCta />
      </main>
      <SiteFooter />
    </>
  )
}
