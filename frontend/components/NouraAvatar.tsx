'use client';

/**
 * Small Noura avatar for page headers. Shows the "working on a laptop"
 * variant while the page is busy, the idle mascot otherwise.
 */
export function NouraAvatar({ working = false }: { working?: boolean }) {
  return (
    <img
      src={working ? '/images/nourai-working.jpg' : '/images/nourai-mascot.jpg'}
      alt={working ? 'نورا در حال کار' : 'نورا'}
      className="h-11 w-11 rounded-full object-cover shadow-md"
      loading="lazy"
    />
  );
}
