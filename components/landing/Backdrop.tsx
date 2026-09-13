'use client'

import { useEffect, useRef } from 'react'
import { motion, useReducedMotion, useScroll, useTransform } from 'framer-motion'

/**
 * Landing-page backdrop: slow aurora blobs in the signal palette that also
 * parallax with scroll, a faint full-page dot grid, a grain overlay, and a soft
 * spotlight that follows the pointer. Fixed and non-interactive; everything is
 * a transform/opacity animation so it stays on the compositor. The global
 * reduced-motion rule freezes the keyframes; the scroll and pointer effects
 * check the preference themselves.
 */
export function Backdrop() {
  const reduce = useReducedMotion()
  const { scrollYProgress } = useScroll()
  const yA = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : -320])
  const yB = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : 220])
  const yC = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : -160])
  const spot = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = spot.current
    if (!el || reduce || !window.matchMedia('(pointer: fine)').matches) return
    let tx = window.innerWidth / 2, ty = window.innerHeight * 0.3, cx = tx, cy = ty, frame = 0
    const onMove = (e: PointerEvent) => { tx = e.clientX; ty = e.clientY }
    const tick = () => {
      cx += (tx - cx) * 0.08; cy += (ty - cy) * 0.08
      el.style.transform = `translate3d(${cx - 360}px, ${cy - 360}px, 0)`
      frame = requestAnimationFrame(tick)
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    frame = requestAnimationFrame(tick)
    return () => { window.removeEventListener('pointermove', onMove); cancelAnimationFrame(frame) }
  }, [reduce])

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-ink-950">
      <motion.div style={{ y: yA }} className="absolute inset-0"><div className="aurora aurora-a" /></motion.div>
      <motion.div style={{ y: yB }} className="absolute inset-0"><div className="aurora aurora-b" /></motion.div>
      <motion.div style={{ y: yC }} className="absolute inset-0"><div className="aurora aurora-c" /></motion.div>
      <div className="dotgrid absolute inset-0" />
      <div ref={spot} className="spotlight absolute left-0 top-0" />
      <div className="grain absolute inset-0" />
    </div>
  )
}

/** Thin horizontal lines with a pulse travelling along each - hero only. */
export function SignalLines() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <span className="signal-line" style={{ top: '22%', animationDuration: '9s', animationDelay: '0s' }} />
      <span className="signal-line" style={{ top: '48%', animationDuration: '12s', animationDelay: '-4s' }} />
      <span className="signal-line" style={{ top: '76%', animationDuration: '10s', animationDelay: '-7s' }} />
    </div>
  )
}

export type GlowTone = 'sky' | 'purple' | 'green' | 'amber' | 'rose'

const GLOW: Record<GlowTone, string> = {
  sky: 'rgba(56, 189, 248, 0.34)',
  purple: 'rgba(192, 132, 252, 0.30)',
  green: 'rgba(52, 211, 153, 0.26)',
  amber: 'rgba(251, 191, 36, 0.22)',
  rose: 'rgba(248, 113, 113, 0.22)',
}

/** A section's own ambient light: one drifting blob, on the left or the right. */
export function SectionGlow({ tone, side }: { tone: GlowTone; side: 'left' | 'right' }) {
  return (
    <span
      aria-hidden
      className={`section-glow ${side}`}
      style={{ background: `radial-gradient(closest-side, ${GLOW[tone]}, transparent)` }}
    />
  )
}
