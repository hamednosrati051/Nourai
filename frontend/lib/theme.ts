'use client';

import { THEME_STORAGE_KEY } from './config';

export type ThemeMode = 'light' | 'dark' | 'system';
export type ResolvedTheme = 'light' | 'dark';

/** Read the persisted theme preference; defaults to 'system'. */
export function getStoredTheme(): ThemeMode {
  if (typeof window === 'undefined') return 'system';
  const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
  return stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system';
}

/** Resolve 'system' to the OS preference. */
export function resolveTheme(mode: ThemeMode): ResolvedTheme {
  if (mode !== 'system' || typeof window === 'undefined') {
    return mode === 'dark' ? 'dark' : 'light';
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** Apply the resolved theme to <html data-theme> without a flash. */
export function applyTheme(mode: ThemeMode): void {
  if (typeof document === 'undefined') return;
  document.documentElement.dataset.theme = resolveTheme(mode);
  document.documentElement.style.colorScheme = resolveTheme(mode);
}
