'use client';

export type MascotMood = 'idle' | 'listening' | 'thinking' | 'speaking';

/**
 * Nourai's mascot avatar with mood-based motion.
 * idle = gentle float, listening = pulsing rings,
 * thinking = soft tilt, speaking = happy bounce.
 */
export function NouraiMascot({
  mood = 'idle',
  className = 'h-52 w-52',
}: {
  mood?: MascotMood;
  className?: string;
}) {
  const anim =
    mood === 'speaking'
      ? 'animate-mascot-bounce'
      : mood === 'thinking'
        ? 'animate-mascot-wobble'
        : 'animate-mascot-float';

  return (
    <div className={`relative ${className}`} role="img" aria-label="نورا">
      {/* warm halo */}
      <span className="absolute -inset-6 rounded-full bg-amber-300/30 blur-2xl dark:bg-amber-400/15" />
      {/* listening rings */}
      {mood === 'listening' && (
        <>
          <span
            className="absolute inset-0 animate-mascot-wave rounded-full border-4 border-amber-400/60"
            style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
          />
          <span
            className="absolute inset-0 animate-mascot-wave rounded-full border-4 border-amber-400/40"
            style={{ transformBox: 'fill-box', transformOrigin: 'center', animationDelay: '0.6s' }}
          />
        </>
      )}
      <div
        className={`relative h-full w-full overflow-hidden rounded-full shadow-2xl shadow-amber-500/25 ring-4 ring-amber-200/80 dark:ring-amber-300/25 ${anim}`}
      >
        <video
          className="h-full w-full object-cover"
          src="/images/nourai-mascot.mp4"
          poster="/images/nourai-mascot.jpg"
          autoPlay
          loop
          muted
          playsInline
          aria-label="نورا"
        />
      </div>
    </div>
  );
}
