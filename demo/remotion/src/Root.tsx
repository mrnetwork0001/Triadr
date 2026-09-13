import React from 'react'
import { Composition } from 'remotion'
import { Triadr, TRIADR_DURATION } from './Triadr'

export const RemotionRoot: React.FC = () => (
  <Composition id="Triadr" component={Triadr} durationInFrames={TRIADR_DURATION} fps={30} width={1920} height={1080} />
)
