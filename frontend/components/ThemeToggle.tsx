'use client';

import { useTheme, type ThemeMode } from './ThemeProvider';
import { Monitor, Moon, Sun } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

const OPTIONS: { value: ThemeMode; label: string; icon: LucideIcon }[] = [
  { value: 'light', label: 'روشن', icon: Sun },
  { value: 'dark', label: 'تیره', icon: Moon },
  { value: 'system', label: 'سیستم', icon: Monitor },
];

/** Segmented light/dark/system theme switcher. */
export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { mode, setMode } = useTheme();

  // On mobile: single button cycling through modes (saves space).
  const cycle = () => {
    const order: ThemeMode[] = ['light', 'dark', 'system'];
    const next = order[(order.indexOf(mode) + 1) % order.length];
    setMode(next);
  };
  const CurrentIcon = OPTIONS.find((o) => o.value === mode)?.icon ?? Monitor;

  return (
    <>
      <button
        type="button"
        onClick={cycle}
        aria-label="تغییر تم"
        title="تغییر تم"
        className="btn-ghost btn-sm sm:hidden"
      >
        <CurrentIcon aria-hidden="true" className="h-4 w-4" />
      </button>
      <div
        role="radiogroup"
        aria-label="انتخاب تم"
        className="hidden items-center gap-1 rounded-xl border border-neutral-200 bg-neutral-50 p-1 sm:inline-flex dark:border-white/15 dark:bg-navy-900"
      >
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          role="radio"
          aria-checked={mode === opt.value}
          title={`تم ${opt.label}`}
          onClick={() => setMode(opt.value)}
          className={`flex items-center justify-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
            mode === opt.value
              ? 'bg-white text-neutral-900 shadow-sm dark:bg-navy-800 dark:text-slate-100'
              : 'text-neutral-500 hover:text-neutral-800 dark:text-slate-400 dark:hover:text-slate-200'
          }`}
        >
          <opt.icon aria-hidden="true" className="h-4 w-4" />
          {!compact && <span>{opt.label}</span>}
          <span className="sr-only">{opt.label}</span>
        </button>
      ))}
      </div>
    </>
  );
}
