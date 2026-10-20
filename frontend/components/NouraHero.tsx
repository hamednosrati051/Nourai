'use client';

import { useState } from 'react';
import Link from 'next/link';

const GREETINGS = [
  'سلام! من نورام 👋',
  'بزن و حرف بزن! 🎙️',
  'امروز چطور کمکت کنم؟ ✨',
  'یه چیزی بگو ببینم! 😊',
];

/**
 * Noura hero avatar with a playful hover reaction: the mascot wiggles
 * and a speech bubble pops up with a random greeting.
 */
export function NouraHero({
  href,
  size = 'h-24 w-24',
  title = 'نورا',
  subtitle,
}: {
  href: string;
  size?: string;
  title?: string;
  subtitle?: string;
}) {
  const [greeting, setGreeting] = useState(GREETINGS[0]);
  const [hovered, setHovered] = useState(false);

  return (
    <Link
      href={href}
      aria-label="نورا — دستیار صوتی"
      className="group relative inline-flex flex-col items-center gap-2 p-2 text-center"
      onMouseEnter={() => {
        setGreeting(GREETINGS[Math.floor(Math.random() * GREETINGS.length)]);
        setHovered(true);
      }}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Speech bubble */}
      <span
        aria-hidden="true"
        className={`pointer-events-none absolute -top-2 right-1/2 translate-x-1/2 whitespace-nowrap rounded-2xl rounded-bl-sm bg-navy-900 px-3 py-1.5 text-sm font-bold text-white shadow-lg transition-all duration-200 dark:bg-white dark:text-navy-900 ${
          hovered
            ? ' -translate-y-10 opacity-100 scale-100'
            : ' -translate-y-6 opacity-0 scale-90'
        }`}
      >
        {greeting}
      </span>
      <span className={`relative shrink-0 ${size}`}>
        {/* Gentle pulsing ring: signals the mascot is tappable */}
        <span
          aria-hidden="true"
          className="absolute inset-0 rounded-full bg-brand-400/40 [animation:noura-pulse_2.4s_ease-out_infinite]"
        />
        <video
          src="/images/nourai-mascot.mp4"
          poster="/images/nourai-mascot.jpg"
          autoPlay
          loop
          muted
          playsInline
          className="relative h-full w-full rounded-full object-cover shadow-xl shadow-brand-500/20 transition-all duration-300 group-hover:scale-110 group-hover:shadow-brand-500/40 group-hover:[animation:noura-wiggle_0.6s_ease-in-out]"
        />
      </span>
      <span className="text-2xl font-black transition-colors group-hover:text-brand-600 dark:group-hover:text-brand-400">
        {title}
      </span>
      {subtitle && (
        <span className="-mt-1 text-sm text-neutral-500 dark:text-slate-400">{subtitle}</span>
      )}
      <span className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-brand-600 px-4 py-2 text-sm font-bold text-white shadow-lg shadow-brand-600/30 transition-colors group-hover:bg-brand-500 dark:bg-brand-500 dark:text-navy-950">
        🎙️ با نورا حرف بزن
      </span>
      <style jsx>{`
        @keyframes noura-wiggle {
          0%, 100% { transform: rotate(0deg) scale(1.1); }
          25% { transform: rotate(-8deg) scale(1.12); }
          50% { transform: rotate(8deg) scale(1.12); }
          75% { transform: rotate(-4deg) scale(1.1); }
        }
        @keyframes noura-pulse {
          0% { transform: scale(1); opacity: 0.5; }
          70% { transform: scale(1.35); opacity: 0; }
          100% { transform: scale(1.35); opacity: 0; }
        }
      `}</style>
    </Link>
  );
}
