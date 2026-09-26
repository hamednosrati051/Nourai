'use client';

import { useTheme, type ThemeMode } from './ThemeProvider';

const OPTIONS: { value: ThemeMode; label: string; icon: string }[] = [
  { value: 'light', label: 'روشن', icon: '☀️' },
  { value: 'dark', label: 'تیره', icon: '🌙' },
  { value: 'system', label: 'سیستم', icon: '🖥️' },
];

/** Segmented light/dark/system theme switcher. */
export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { mode, setMode } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label="انتخاب تم"
      className="inline-flex items-center gap-1 rounded-xl border border-neutral-200 bg-neutral-50 p-1 dark:border-white/15 dark:bg-navy-900"
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
          <span aria-hidden="true">{opt.icon}</span>
          {!compact && <span>{opt.label}</span>}
          <span className="sr-only">{opt.label}</span>
        </button>
      ))}
    </div>
  );
}
