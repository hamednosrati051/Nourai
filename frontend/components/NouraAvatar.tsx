'use client';

/**
 * Small Noura avatar for page headers. While the page is busy it plays the
 * looping "working on a laptop" video; otherwise the idle mascot image.
 */
export function NouraAvatar({ working = false }: { working?: boolean }) {
  if (working) {
    return (
      <video
        src="/images/nourai-working.mp4"
        poster="/images/nourai-working.jpg"
        autoPlay
        loop
        muted
        playsInline
        aria-label="نورا در حال کار"
        className="h-11 w-11 rounded-full object-cover shadow-md"
      />
    );
  }
  return (
    <img
      src="/images/nourai-mascot.jpg"
      alt="نورا"
      className="h-11 w-11 rounded-full object-cover shadow-md"
      loading="lazy"
    />
  );
}
