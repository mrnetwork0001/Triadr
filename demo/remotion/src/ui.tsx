import React from 'react'
import { AbsoluteFill, Img, OffthreadVideo, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from 'remotion'

export const INK = '#07080c'
export const PANEL = '#0b0d14'
export const OK = '#34d399'
export const HEAL = '#fbbf24'
export const FAIL = '#f87171'
export const UNDO = '#c084fc'
export const LIVE = '#38bdf8'
export const SLATE = '#94a3b8'
export const SANS = 'ui-sans-serif, -apple-system, "Helvetica Neue", Arial, sans-serif'
export const MONO = 'ui-monospace, "SF Mono", Menlo, monospace'

/** Slow drifting aurora + dot grid - the same language as the product's own backdrop. */
export const Backdrop: React.FC<{ tone?: string }> = ({ tone = LIVE }) => {
  const f = useCurrentFrame()
  const drift = (s: number, amp: number) => Math.sin((f / 30) * s) * amp
  return (
    <AbsoluteFill style={{ background: INK }}>
      <div style={{ position: 'absolute', width: 1500, height: 1500, left: -400 + drift(0.06, 90), top: -600 + drift(0.05, 70),
        borderRadius: '50%', filter: 'blur(150px)', opacity: 0.5,
        background: `radial-gradient(closest-side, ${tone}55, transparent)` }} />
      <div style={{ position: 'absolute', width: 1200, height: 1200, right: -350 - drift(0.04, 80), bottom: -450 + drift(0.07, 60),
        borderRadius: '50%', filter: 'blur(150px)', opacity: 0.4,
        background: `radial-gradient(closest-side, ${UNDO}44, transparent)` }} />
      <AbsoluteFill style={{
        backgroundImage: 'radial-gradient(rgba(255,255,255,.055) 1px, transparent 1.2px)',
        backgroundSize: '34px 34px',
        maskImage: 'linear-gradient(180deg,#000,rgba(0,0,0,.35))',
        WebkitMaskImage: 'linear-gradient(180deg,#000,rgba(0,0,0,.35))',
      }} />
    </AbsoluteFill>
  )
}

export const useRise = (delay = 0, dist = 26) => {
  const f = useCurrentFrame()
  const { fps } = useVideoConfig()
  const s = spring({ frame: f - delay, fps, config: { damping: 200, mass: 0.6 } })
  return { opacity: s, transform: `translateY(${interpolate(s, [0, 1], [dist, 0])}px)` }
}

export const Eyebrow: React.FC<{ children: React.ReactNode; tone?: string; delay?: number }> = ({ children, tone = LIVE, delay = 0 }) => (
  <div style={{ ...useRise(delay), fontFamily: SANS, fontSize: 21, fontWeight: 700, letterSpacing: 4,
    textTransform: 'uppercase', color: tone }}>{children}</div>
)

export const Headline: React.FC<{ children: React.ReactNode; delay?: number; size?: number }> = ({ children, delay = 4, size = 74 }) => (
  <div style={{ ...useRise(delay), fontFamily: SANS, fontSize: size, fontWeight: 640, lineHeight: 1.08,
    letterSpacing: -1.6, color: '#f8fafc', maxWidth: 1040 }}>{children}</div>
)

export const Body: React.FC<{ children: React.ReactNode; delay?: number; width?: number }> = ({ children, delay = 10, width = 860 }) => (
  <div style={{ ...useRise(delay), fontFamily: SANS, fontSize: 30, lineHeight: 1.5, color: SLATE, maxWidth: width }}>{children}</div>
)

/** A screen recording in a browser chrome, so the viewer knows it is the real app. */
export const Screen: React.FC<{ src: string; delay?: number; start?: number; width?: number; label?: string }> = ({
  src, delay = 0, start = 0, width = 1180, label,
}) => {
  const r = useRise(delay, 34)
  return (
    <div style={{ ...r, width, borderRadius: 16, overflow: 'hidden', border: '1px solid rgba(255,255,255,.12)',
      boxShadow: '0 50px 120px -40px rgba(0,0,0,.9)', background: PANEL }}>
      <div style={{ height: 38, display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px',
        background: '#11131b', borderBottom: '1px solid rgba(255,255,255,.08)' }}>
        {['#ff5f57', '#febc2e', '#28c840'].map((c) => (
          <span key={c} style={{ width: 11, height: 11, borderRadius: 99, background: c, opacity: .85 }} />
        ))}
        <span style={{ marginLeft: 14, fontFamily: MONO, fontSize: 14, color: '#64748b' }}>{label ?? 'localhost:8771'}</span>
      </div>
      <OffthreadVideo src={staticFile(`clips/${src}.mp4`)} startFrom={start} muted style={{ width: '100%', display: 'block' }} />
    </div>
  )
}

/** Telegram screenshots in a phone frame. */
export const Phone: React.FC<{ src: string; delay?: number; height?: number; caption?: string }> = ({
  src, delay = 0, height = 800, caption,
}) => {
  const r = useRise(delay, 40)
  return (
    <div style={{ ...r, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
      <div style={{ height, aspectRatio: '9 / 19.5', borderRadius: 42, padding: 10, background: '#15171f',
        border: '1px solid rgba(255,255,255,.16)', boxShadow: '0 50px 110px -40px rgba(0,0,0,.95)' }}>
        <div style={{ height: '100%', borderRadius: 33, overflow: 'hidden', background: '#0e1621', position: 'relative' }}>
          <Img src={staticFile(src)} style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top' }} />
        </div>
      </div>
      {caption && <div style={{ fontFamily: MONO, fontSize: 17, color: '#64748b' }}>{caption}</div>}
    </div>
  )
}

/** A number that counts up once, then holds. */
export const Counter: React.FC<{ to: number; label: string; tone?: string; delay?: number; suffix?: string }> = ({
  to, label, tone = '#f8fafc', delay = 0, suffix = '',
}) => {
  const f = useCurrentFrame()
  const p = interpolate(f - delay, [0, 34], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  const eased = 1 - Math.pow(1 - p, 3)
  const r = useRise(delay, 20)
  return (
    <div style={{ ...r, background: 'rgba(11,13,20,.72)', border: '1px solid rgba(255,255,255,.09)',
      borderRadius: 18, padding: '26px 30px', minWidth: 270 }}>
      <div style={{ fontFamily: MONO, fontSize: 62, fontWeight: 700, color: tone, lineHeight: 1 }}>
        {Math.round(to * eased)}{suffix}
      </div>
      <div style={{ fontFamily: SANS, fontSize: 19, letterSpacing: 1.6, textTransform: 'uppercase',
        color: '#64748b', marginTop: 12 }}>{label}</div>
    </div>
  )
}

export const Chip: React.FC<{ children: React.ReactNode; tone: string; delay?: number }> = ({ children, tone, delay = 0 }) => (
  <span style={{ ...useRise(delay, 14), display: 'inline-flex', alignItems: 'center', gap: 10,
    border: `1px solid ${tone}55`, background: `${tone}1c`, color: tone, borderRadius: 999,
    padding: '10px 20px', fontFamily: SANS, fontSize: 20, fontWeight: 600 }}>{children}</span>
)

export const Lockup: React.FC<{ height?: number; delay?: number }> = ({ height = 78, delay = 0 }) => (
  <Img src={staticFile('triadr-header.png')} style={{ ...useRise(delay, 18), height, mixBlendMode: 'screen' }} />
)

export const AppLogo: React.FC<{ name: string; size?: number }> = ({ name, size = 62 }) => (
  <Img src={staticFile(`${name}.jpg`)} style={{ width: size, height: size, borderRadius: size * 0.24,
    border: '1px solid rgba(255,255,255,.12)' }} />
)
