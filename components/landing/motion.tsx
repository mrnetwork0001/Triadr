'use client'

import { animate, motion, useInView, useReducedMotion } from 'framer-motion'
import { useEffect, useRef, useState, type ReactNode } from 'react'

/** One easing for the whole page so every reveal feels like the same hand. */
export const EASE = [0.22, 1, 0.36, 1] as const

/** Fade-and-rise when the element scrolls into view. Runs once. */
export function Reveal({
  children,
  delay = 0,
  y = 18,
  className = '',
}: {
  children: ReactNode
  delay?: number
  y?: number
  className?: string
}) {
  const reduce = useReducedMotion()
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-12% 0px -8% 0px' }}
      transition={{ duration: 0.65, delay, ease: EASE }}
      className={`min-w-0 ${className}`}
    >
      {children}
    </motion.div>
  )
}

/** Parent for a grid of cards: children using `itemVariants` enter one after another. */
export function Stagger({
  children,
  className = '',
  gap = 0.08,
  delay = 0,
  as = 'div',
}: {
  children: ReactNode
  className?: string
  gap?: number
  delay?: number
  as?: 'div' | 'ul' | 'ol'
}) {
  const reduce = useReducedMotion()
  const Tag = motion[as]
  return (
    <Tag
      initial={reduce ? false : 'hidden'}
      whileInView="show"
      viewport={{ once: true, margin: '-10% 0px -6% 0px' }}
      variants={{ hidden: {}, show: { transition: { staggerChildren: gap, delayChildren: delay } } }}
      className={`min-w-0 ${className}`}
    >
      {children}
    </Tag>
  )
}

export const itemVariants = {
  hidden: { opacity: 0, y: 18, scale: 0.985 },
  show: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.6, ease: EASE } },
}

/** Counts from 0 to `value` the first time it scrolls into view. */
export function CountUp({
  value,
  prefix = '',
  suffix = '',
  duration = 1.4,
  className = '',
}: {
  value: number
  prefix?: string
  suffix?: string
  duration?: number
  className?: string
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, margin: '-10% 0px' })
  const reduce = useReducedMotion()
  const [n, setN] = useState(reduce ? value : 0)

  useEffect(() => {
    if (!inView || reduce) return
    const controls = animate(0, value, {
      duration,
      ease: EASE,
      onUpdate: (v) => setN(Math.round(v)),
    })
    return () => controls.stop()
  }, [inView, value, reduce, duration])

  return (
    <span ref={ref} className={className}>
      {prefix}
      {n}
      {suffix}
    </span>
  )
}

/** A hairline that draws itself from left to right when seen. */
export function DrawLine({ className = '' }: { className?: string }) {
  const reduce = useReducedMotion()
  return (
    <motion.span
      aria-hidden
      initial={reduce ? false : { scaleX: 0 }}
      whileInView={{ scaleX: 1 }}
      viewport={{ once: true }}
      transition={{ duration: 0.9, ease: EASE }}
      className={`block h-px origin-left ${className}`}
    />
  )
}
