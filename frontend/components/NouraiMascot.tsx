'use client';

export type MascotMood = 'idle' | 'listening' | 'thinking' | 'speaking';

/**
 * Nourai's mascot: a little light-spirit with kawaii face.
 * The face swaps per mood (idle / listening / thinking / speaking),
 * like classic assistant mascots. Pure SVG + CSS, no image assets.
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

  // Pupil tweaks per mood.
  const pupilR = mood === 'listening' ? 8.5 : 7.5;
  const pupilDy = mood === 'thinking' ? -7 : 0;

  return (
    <svg
      viewBox="0 0 200 200"
      className={anim + ' ' + className}
      role="img"
      aria-label="نورا"
    >
      <defs>
        <radialGradient id="nourai-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#fbbf24" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#fbbf24" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="nourai-body" cx="38%" cy="30%" r="80%">
          <stop offset="0%" stopColor="#fef9c3" />
          <stop offset="45%" stopColor="#fde68a" />
          <stop offset="80%" stopColor="#fbbf24" />
          <stop offset="100%" stopColor="#f59e0b" />
        </radialGradient>
      </defs>

      {/* halo */}
      <circle cx="100" cy="108" r="80" fill="url(#nourai-glow)" />

      {/* listening waves */}
      {mood === 'listening' && (
        <g
          stroke="#f59e0b"
          strokeWidth="4"
          fill="none"
          strokeLinecap="round"
          className="animate-mascot-wave"
          style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
        >
          <path d="M28 92 C 20 100, 20 116, 28 124" />
          <path d="M16 86 C 4 98, 4 118, 16 130" style={{ animationDelay: '0.4s' }} className="animate-mascot-wave" />
          <path d="M172 92 C 180 100, 180 116, 172 124" />
          <path d="M184 86 C 196 98, 196 118, 184 130" style={{ animationDelay: '0.4s' }} className="animate-mascot-wave" />
        </g>
      )}

      {/* body */}
      <path
        d="M100 28 C 138 28, 166 60, 166 108 C 166 152, 134 182, 100 182 C 66 182, 34 152, 34 108 C 34 60, 62 28, 100 28 Z"
        fill="url(#nourai-body)"
      />
      {/* light tuft */}
      <path d="M100 30 Q 95 12, 110 5 Q 103 18, 113 29 Z" fill="#f59e0b" />

      {/* sparkles */}
      <g fill="#fde68a">
        <path
          d="M0 -9 C 1.5 -3, 3 -1.5, 9 0 C 3 1.5, 1.5 3, 0 9 C -1.5 3, -3 1.5, -9 0 C -3 -1.5, -1.5 -3, 0 -9 Z"
          transform="translate(42 54)"
          className="animate-pulse-soft"
        />
        <path
          d="M0 -9 C 1.5 -3, 3 -1.5, 9 0 C 3 1.5, 1.5 3, 0 9 C -1.5 3, -3 1.5, -9 0 C -3 -1.5, -1.5 -3, 0 -9 Z"
          transform="translate(162 46) scale(0.65)"
          className="animate-pulse-soft"
          style={{ animationDelay: '1.2s' }}
        />
      </g>

      {/* eyes (blink) */}
      {[
        { cx: 76 },
        { cx: 124 },
      ].map(({ cx }) => (
        <g
          key={cx}
          className="animate-mascot-blink"
          style={{ transformBox: 'fill-box', transformOrigin: 'center' }}
        >
          <ellipse cx={cx} cy={102} rx={15} ry={18} fill="#ffffff" />
          <circle cx={cx} cy={106 + pupilDy} r={pupilR} fill="#292524" />
          <circle cx={cx - 2.5} cy={103 + pupilDy} r={2.6} fill="#ffffff" />
        </g>
      ))}

      {/* blush */}
      <ellipse cx={56} cy={126} rx={10} ry={6.5} fill="#f9a8d4" opacity="0.65" />
      <ellipse cx={144} cy={126} rx={10} ry={6.5} fill="#f9a8d4" opacity="0.65" />

      {/* mouth per mood */}
      {mood === 'speaking' ? (
        <g>
          <ellipse cx={100} cy={136} rx={11} ry={13} fill="#7c2d12" />
          <ellipse cx={100} cy={141} rx={6.5} ry={5} fill="#f9a8d4" />
        </g>
      ) : mood === 'listening' ? (
        <circle cx={100} cy={133} r={5} fill="#9a3412" />
      ) : mood === 'thinking' ? (
        <path
          d="M92 133 Q100 130 108 133"
          stroke="#9a3412"
          strokeWidth={4}
          fill="none"
          strokeLinecap="round"
        />
      ) : (
        <path
          d="M88 130 Q100 141 112 130"
          stroke="#9a3412"
          strokeWidth={4}
          fill="none"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
}
