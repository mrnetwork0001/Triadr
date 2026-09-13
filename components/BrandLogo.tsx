/* eslint-disable @next/next/no-img-element */
/**
 * Real vendor logos (public/logos), rendered as uniform rounded tiles.
 * GitHub's asset is black-on-white and the other two are white-on-brand-colour,
 * so the tile treatment keeps all three visually consistent on the dark UI.
 */
const LOGOS: Record<string, { src: string; alt: string }> = {
  github: { src: '/logos/github.jpg', alt: 'GitHub' },
  telegram: { src: '/logos/telegram.jpg', alt: 'Telegram' },
  stripe: { src: '/logos/stripe.jpg', alt: 'Stripe' },
}

export function BrandLogo({
  app,
  size = 32,
  className = '',
}: {
  app: string
  size?: number
  className?: string
}) {
  const logo = LOGOS[app]
  if (!logo) return null
  return (
    <img
      src={logo.src}
      alt={logo.alt}
      width={size}
      height={size}
      draggable={false}
      className={`shrink-0 select-none rounded-[24%] object-cover ring-1 ring-white/10 ${className}`}
      style={{ width: size, height: size }}
    />
  )
}
