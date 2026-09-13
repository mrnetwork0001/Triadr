/* eslint-disable @next/next/no-img-element */
/**
 * The Triadr header lockup (public/brand/triadr-header.png), a 3:1 artwork on a
 * pure-black ground. The app's surfaces are near-black, not black, so the image
 * is composited with `screen`: black contributes nothing and the artwork sits on
 * whatever is behind it without a visible box.
 */
export function BrandHeader({ height = 32, className = '' }: { height?: number; className?: string }) {
  return (
    <img
      src="/brand/triadr-header.png"
      alt="Triadr"
      height={height}
      width={Math.round(height * 3)}
      draggable={false}
      className={`block h-auto w-auto shrink-0 select-none ${className}`}
      style={{ height, width: 'auto', mixBlendMode: 'screen' }}
    />
  )
}
