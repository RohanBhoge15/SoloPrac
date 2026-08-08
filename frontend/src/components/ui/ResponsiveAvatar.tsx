/**
 * P2.22 — Responsive doctor profile photo.
 *
 * The doctor upload flow stores one canonical photo (up to ~4 MB) in MinIO.
 * The search results grid renders it at 48×48, patient portal renders at
 * 96×96, and settings render at 128×128 — all serving the same full-size
 * image, which wastes ~3.9 MB and forces layout/decoding delays on
 * low-power devices.
 *
 * This component:
 *   1. Requests a size hint via `?w=` and `?dpr=` on the S3 URL. The backend's
 *      image handler (routers/images.py) accepts these query params and
 *      resamples on the fly (already implemented for patient images).
 *   2. Emits `srcSet` at 1x + 2x so retina screens still get sharp pixels
 *      without desktop clients wasting bandwidth.
 *   3. Uses native `loading="lazy"` + `decoding="async"` so off-screen
 *      images never block the main thread.
 *
 * Fallback: when `src` is missing, render the initials bubble the caller
 * would otherwise have to code twice.
 */

import { memo } from 'react'

export interface ResponsiveAvatarProps {
  src?: string | null
  alt: string
  size?: number            // logical CSS pixels (default 48)
  className?: string
  fallbackInitials?: string
}

function initialsOf(name: string): string {
  return name
    .split(' ')
    .filter(Boolean)
    .map((n) => n[0])
    .join('')
    .slice(0, 3)
    .toUpperCase()
}

function buildSrc(url: string, width: number, dpr: number): string {
  try {
    const u = new URL(url, window.location.origin)
    u.searchParams.set('w', String(Math.round(width * dpr)))
    u.searchParams.set('dpr', String(dpr))
    return u.toString()
  } catch {
    // Not a real URL (e.g. a relative data-uri) — return unmodified.
    return url
  }
}

function ResponsiveAvatarImpl({
  src,
  alt,
  size = 48,
  className,
  fallbackInitials,
}: ResponsiveAvatarProps) {
  if (!src) {
    const initials = fallbackInitials ?? initialsOf(alt)
    return (
      <div
        className={
          className ??
          'flex items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/30'
        }
        style={{ width: size, height: size }}
        aria-label={alt}
      >
        <span className="text-sm font-medium text-primary-700 dark:text-primary-300">
          {initials}
        </span>
      </div>
    )
  }

  const src1x = buildSrc(src, size, 1)
  const src2x = buildSrc(src, size, 2)

  return (
    <img
      src={src1x}
      srcSet={`${src1x} 1x, ${src2x} 2x`}
      alt={alt}
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      className={className ?? 'rounded-full object-cover'}
      style={{ width: size, height: size }}
    />
  )
}

export const ResponsiveAvatar = memo(ResponsiveAvatarImpl)
