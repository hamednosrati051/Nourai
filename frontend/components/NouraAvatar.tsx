'use client';

/**
 * Small Noura avatar for page headers. Both states are looping videos:
 * the "working on a laptop" clip while the page is busy, the idle mascot
 * animation otherwise.
 */
export function NouraAvatar({ working = false }: { working?: boolean }) {
  return (
    <video
      src={working ? '/images/nourai-working.mp4' : '/images/nourai-mascot.mp4'}
      poster={working ? '/images/nourai-working.jpg' : '/images/nourai-mascot.jpg'}
      autoPlay
      loop
      muted
      playsInline
      aria-label={working ? 'نورا در حال کار' : 'نورا'}
      className="h-11 w-11 rounded-full object-cover shadow-md"
    />
  );
}
