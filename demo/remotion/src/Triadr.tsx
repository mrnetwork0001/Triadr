import React from 'react'
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame } from 'remotion'
import { AppLogo, Backdrop, Body, Chip, Counter, Eyebrow, FAIL, HEAL, Headline, LIVE, Lockup, MONO, OK, Phone, SANS, SLATE, Screen, UNDO, useRise } from './ui'

const FPS = 30
const s = (sec: number) => Math.round(sec * FPS)

// Scene lengths are set from the measured narration (vo/*.mp3) plus a little air.
// Total stays under 120 s, which the hackathon requires.
const SCENES = [
  { id: 'v00', dur: s(3.2) },
  { id: 'v01', dur: s(13.4) },
  { id: 'v02', dur: s(11.3) },
  { id: 'v03', dur: s(11.7) },
  { id: 'v04', dur: s(10.4) },
  { id: 'v05', dur: s(10.1) },
  { id: 'v06', dur: s(15.1) },
  { id: 'v07', dur: s(12.9) },
  { id: 'v08', dur: s(11.9) },
  { id: 'v09', dur: s(17.0) },
]
const STARTS = SCENES.reduce<number[]>((a, sc, i) => [...a, i === 0 ? 0 : a[i - 1] + SCENES[i - 1].dur], [])
export const TRIADR_DURATION = SCENES.reduce((n, sc) => n + sc.dur, 0)

const Pad: React.FC<{ children: React.ReactNode; center?: boolean }> = ({ children, center }) => (
  <AbsoluteFill style={{ padding: '92px 110px', justifyContent: 'center', alignItems: center ? 'center' : 'flex-start' }}>
    {children}
  </AbsoluteFill>
)

/** Fade the whole scene in and out so cuts never snap. */
const Scene: React.FC<{ dur: number; children: React.ReactNode }> = ({ dur, children }) => {
  const f = useCurrentFrame()
  const o = Math.min(
    interpolate(f, [0, 8], [0, 1], { extrapolateRight: 'clamp' }),
    interpolate(f, [dur - 9, dur - 1], [1, 0], { extrapolateLeft: 'clamp' }),
  )
  return <AbsoluteFill style={{ opacity: o }}>{children}</AbsoluteFill>
}

// 00 - title
const S0: React.FC = () => (
  <>
    <Backdrop />
    <Pad center>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 30 }}>
        <Lockup height={104} />
        <div style={{ ...useRise(8), fontFamily: SANS, fontSize: 34, color: SLATE, letterSpacing: 1 }}>
          A self-healing multi-app agent
        </div>
      </div>
    </Pad>
  </>
)

// 01 - the problem
const S1: React.FC = () => (
  <>
    <Backdrop tone={FAIL} />
    <Pad>
      <div style={{ display: 'flex', gap: 70, alignItems: 'center', width: '100%' }}>
        <div style={{ flex: 1 }}>
          <Eyebrow tone={FAIL}>The problem</Eyebrow>
          <div style={{ height: 22 }} />
          <Headline delay={6} size={64}>Step four of six dies.<br />One to three already happened.</Headline>
        </div>
        <div style={{ width: 640, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {[
            ['GitHub', 'commit status written', OK, 14],
            ['Telegram', 'approval card posted', OK, 20],
            ['Stripe', 'payout - rate limited', FAIL, 26],
            ['', 'script crashes here', FAIL, 34],
          ].map(([app, text, tone, d], i) => (
            <div key={i} style={{ ...useRise(d as number, 18), display: 'flex', alignItems: 'center', gap: 18,
              border: `1px solid ${tone as string}44`, background: `${tone as string}12`, borderRadius: 14, padding: '20px 26px' }}>
              <span style={{ width: 10, height: 10, borderRadius: 99, background: tone as string }} />
              <span style={{ fontFamily: SANS, fontSize: 24, color: '#e2e8f0', width: 140 }}>{app as string}</span>
              <span style={{ fontFamily: MONO, fontSize: 21, color: tone as string }}>{text as string}</span>
            </div>
          ))}
          <div style={{ ...useRise(44), fontFamily: SANS, fontSize: 25, color: FAIL, marginTop: 10 }}>
            The approval is still pending. The money already moved.
          </div>
        </div>
      </div>
    </Pad>
  </>
)

// 02 - three apps
const S2: React.FC = () => (
  <>
    <Backdrop />
    <Pad center>
      <Eyebrow>One sentence, three external apps</Eyebrow>
      <div style={{ height: 26 }} />
      <div style={{ ...useRise(6), fontFamily: MONO, fontSize: 26, color: '#cbd5e1', background: 'rgba(0,0,0,.42)',
        border: '1px solid rgba(255,255,255,.1)', borderRadius: 14, padding: '20px 30px', maxWidth: 1320, textAlign: 'center' }}>
        "Audit PR #1 in mrnetwork0001/Fluenci, get team sign-off on Telegram,<br />then release $25.00 USD from escrow to the contractor"
      </div>
      <div style={{ height: 54 }} />
      <div style={{ display: 'flex', gap: 30, alignItems: 'stretch' }}>
        {[['github', 'GitHub', 'Audits the pull request', 18], ['telegram', 'Telegram', 'Asks a human to approve', 26], ['stripe', 'Stripe', 'Releases the payout', 34]].map(([k, n, d, delay]) => (
          <div key={k as string} style={{ ...useRise(delay as number, 24), width: 400, background: 'rgba(11,13,20,.75)',
            border: '1px solid rgba(255,255,255,.1)', borderRadius: 20, padding: 32 }}>
            <AppLogo name={k as string} />
            <div style={{ fontFamily: SANS, fontSize: 32, fontWeight: 620, color: '#f1f5f9', marginTop: 20 }}>{n as string}</div>
            <div style={{ fontFamily: SANS, fontSize: 23, color: SLATE, marginTop: 8 }}>{d as string}</div>
          </div>
        ))}
      </div>
    </Pad>
  </>
)

// 03 - the gate
const S3: React.FC = () => {
  const stages = ['idempotency', 'schema', 'rate shaping', 'circuit breakers', 'typed faults', 'failover', 'drift check', 'compensation']
  return (
    <>
      <Backdrop />
      <Pad center>
        <Eyebrow>Every call passes one gate</Eyebrow>
        <div style={{ height: 30 }} />
        <Headline delay={5} size={58}>Validate. Retry. Reroute. Never pay twice.</Headline>
        <div style={{ height: 48 }} />
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, maxWidth: 1420, justifyContent: 'center' }}>
          {stages.map((st, i) => (
            <Chip key={st} tone={i === 7 ? UNDO : LIVE} delay={12 + i * 4}>
              <span style={{ fontFamily: MONO, opacity: .6 }}>{i + 1}</span> {st}
            </Chip>
          ))}
        </div>
        <div style={{ height: 40 }} />
        <Body delay={48} width={1080}>
          <span style={{ color: '#e2e8f0' }}>And if a step cannot be recovered, it rolls the whole workflow back.</span>
        </Body>
      </Pad>
    </>
  )
}

// 04 - the live audit
const S4: React.FC = () => (
  <>
    <Backdrop />
    <Pad>
      <div style={{ display: 'flex', gap: 60, alignItems: 'center', width: '100%' }}>
        <div style={{ width: 560 }}>
          <Eyebrow>Step 1 - GitHub</Eyebrow>
          <div style={{ height: 20 }} />
          <Headline delay={5} size={54}>A real pull request, scored.</Headline>
          <div style={{ height: 28 }} />
          <div style={{ ...useRise(16), display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <Chip tone={HEAL} delay={18}>risk 52 / 100</Chip>
            <Chip tone={HEAL} delay={24}>medium</Chip>
            <Chip tone={LIVE} delay={30}>approval required</Chip>
          </div>
          <div style={{ height: 26 }} />
          <Body delay={34} width={520}>The verdict is written back onto the commit as a status check.</Body>
        </div>
        <Screen src="console-live" delay={8} start={60} width={1150} />
      </div>
    </Pad>
  </>
)

// 05 - the card (phone beside motion graphics, as requested)
const S5: React.FC = () => (
  <>
    <Backdrop tone={UNDO} />
    <Pad>
      <div style={{ display: 'flex', gap: 90, alignItems: 'center', width: '100%' }}>
        <div style={{ flex: 1 }}>
          <Eyebrow tone={UNDO}>Step 2 - Telegram</Eyebrow>
          <div style={{ height: 22 }} />
          <Headline delay={5} size={58}>The agent stops<br />and waits for a person.</Headline>
          <div style={{ height: 30 }} />
          <Body delay={14} width={640}>Real inline Approve and Reject buttons, delivered by long-polling. No public callback URL, no webhook.</Body>
          <div style={{ height: 26 }} />
          <div style={{ ...useRise(24), fontFamily: MONO, fontSize: 22, color: UNDO }}>
            telegram.await_approval - blocking
          </div>
        </div>
        <Phone src="tg-before.png" delay={10} height={820} caption="the card, before approval" />
      </div>
    </Pad>
  </>
)

// 06 - approved + payout
const S6: React.FC = () => (
  <>
    <Backdrop tone={OK} />
    <Pad>
      <div style={{ display: 'flex', gap: 90, alignItems: 'center', width: '100%' }}>
        <Phone src="tg-after.png" delay={4} height={820} caption="approved - the receipt is posted back" />
        <div style={{ flex: 1 }}>
          <Eyebrow tone={OK}>Step 3 - Stripe</Eyebrow>
          <div style={{ height: 22 }} />
          <Headline delay={8} size={58}>Settled once.<br />Replays cannot pay again.</Headline>
          <div style={{ height: 30 }} />
          <div style={{ ...useRise(20), fontFamily: MONO, fontSize: 21, color: SLATE, background: 'rgba(0,0,0,.4)',
            border: '1px solid rgba(255,255,255,.1)', borderRadius: 12, padding: '18px 22px', maxWidth: 700 }}>
            <div style={{ color: OK }}>transfer tr_1UFIUBGrU43k7DbAlMLrSwTt</div>
            <div style={{ marginTop: 8 }}>USD 25.00 - idempotency key derived from the workload</div>
          </div>
          <div style={{ height: 26 }} />
          <Body delay={30} width={660}>Six steps, three apps, one settled payout. Every decision hash-chained.</Body>
        </div>
      </div>
    </Pad>
  </>
)

// 07 - chaos
const S7: React.FC = () => (
  <>
    <Backdrop tone={HEAL} />
    <Pad>
      <div style={{ display: 'flex', gap: 56, alignItems: 'center', width: '100%' }}>
        <div style={{ width: 470 }}>
          <Eyebrow tone={HEAL}>Now break it</Eyebrow>
          <div style={{ height: 20 }} />
          <Headline delay={5} size={54}>Three in four calls fail.</Headline>
          <div style={{ height: 26 }} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {[['TIMEOUT', 14], ['RATE_LIMITED', 20], ['NETWORK_PARTITION', 26], ['SERVER_ERROR', 32]].map(([t, d]) => (
              <div key={t as string} style={{ ...useRise(d as number, 14), fontFamily: MONO, fontSize: 21, color: FAIL }}>{t as string}</div>
            ))}
          </div>
          <div style={{ height: 26 }} />
          <Chip tone={HEAL} delay={40}>15 faults absorbed - payout still settles once</Chip>
        </div>
        <Screen src="chaos" delay={6} start={330} width={1230} label="Chaos storm" />
      </div>
    </Pad>
  </>
)

// 08 - rollback
const S8: React.FC = () => (
  <>
    <Backdrop tone={UNDO} />
    <Pad>
      <div style={{ display: 'flex', gap: 56, alignItems: 'center', width: '100%' }}>
        <Screen src="rollback" delay={4} start={300} width={1230} label="Stripe outage" />
        <div style={{ width: 470 }}>
          <Eyebrow tone={UNDO}>When it cannot recover</Eyebrow>
          <div style={{ height: 20 }} />
          <Headline delay={8} size={52}>It undoes itself.</Headline>
          <div style={{ height: 26 }} />
          {[['card retracted', 16], ['commit status reset', 22], ['no money moved', 28]].map(([t, d]) => (
            <div key={t as string} style={{ ...useRise(d as number, 14), display: 'flex', alignItems: 'center', gap: 14, marginBottom: 14 }}>
              <span style={{ width: 9, height: 9, borderRadius: 99, background: UNDO }} />
              <span style={{ fontFamily: SANS, fontSize: 25, color: '#e2e8f0' }}>{t as string}</span>
            </div>
          ))}
          <div style={{ height: 14 }} />
          <Body delay={36} width={440}>Reversed in the opposite order they were applied.</Body>
        </div>
      </div>
    </Pad>
  </>
)

// 09 - evidence + outro
const S9: React.FC = () => {
  const f = useCurrentFrame()
  const outro = interpolate(f, [s(11.4), s(12.6)], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })
  return (
    <>
      <Backdrop />
      <AbsoluteFill style={{ opacity: 1 - outro }}>
        <Pad center>
          <Eyebrow>40 runs under that storm</Eyebrow>
          <div style={{ height: 40 }} />
          <div style={{ display: 'flex', gap: 24 }}>
            <Counter to={356} label="faults absorbed" tone={HEAL} delay={8} />
            <Counter to={0} label="left half-executed" tone={OK} delay={16} />
            <Counter to={0} label="duplicate payouts" tone={OK} delay={24} />
            <Counter to={40} label="of 40 chains verify" tone={LIVE} delay={32} suffix="" />
          </div>
          <div style={{ height: 44 }} />
          <Body delay={44} width={1150}>
            <span style={{ color: '#e2e8f0' }}>Every decision is hash-chained, so you can recompute the numbers yourself.</span>
          </Body>
        </Pad>
      </AbsoluteFill>
      <AbsoluteFill style={{ opacity: outro, justifyContent: 'center', alignItems: 'center' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 28 }}>
          <Lockup height={112} />
          <div style={{ fontFamily: SANS, fontSize: 36, color: '#e2e8f0' }}>
            One agent, three apps, zero half-executed workflows.
          </div>
          <div style={{ fontFamily: MONO, fontSize: 24, color: LIVE, marginTop: 6 }}>
            github.com/mrnetwork0001/Triadr
          </div>
        </div>
      </AbsoluteFill>
    </>
  )
}

const COMPONENTS = [S0, S1, S2, S3, S4, S5, S6, S7, S8, S9]

export const Triadr: React.FC = () => (
  <AbsoluteFill style={{ background: '#07080c' }}>
    {SCENES.map((sc, i) => {
      const C = COMPONENTS[i]
      return (
        <Sequence key={sc.id} from={STARTS[i]} durationInFrames={sc.dur}>
          <Scene dur={sc.dur}><C /></Scene>
          <Audio src={staticFile(`vo/${sc.id}.mp3`)} />
        </Sequence>
      )
    })}
  </AbsoluteFill>
)
