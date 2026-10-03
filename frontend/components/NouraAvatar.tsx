'use client';

/**
 * Small Noura avatar for page headers. Both states are looping videos:
 * the idle mascot animation at rest, and a busy variant while the page
 * works — "working on a laptop" by default, "playing with an orb" for
 * the image page.
 */
export function NouraAvatar({
  working = false,
  variant = 'working',
}: {
  working?: boolean;
  variant?: 'working' | 'playing';
}) {
  const busySrc =
    variant === 'playing' ? '/images/nourai-playing.mp4' : '/images/nourai-working.mp4';
  const busyPoster =
    variant === 'playing' ? '/images/nourai-playing.jpg' : '/images/nourai-working.jpg';
  return (
    <video
      src={working ? busySrc : '/images/nourai-mascot.mp4'}
      poster={working ? busyPoster : '/images/nourai-mascot.jpg'}
      autoPlay
      loop
      muted
      playsInline
      aria-label={working ? 'نورا در حال کار' : 'نورا'}
      className="h-11 w-11 rounded-full object-cover shadow-md"
    />
  );
}
