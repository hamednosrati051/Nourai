'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { THEME_STORAGE_KEY } from '@/lib/config';
import { applyTheme, getStoredTheme, resolveTheme, type ResolvedTheme, type ThemeMode } from '@/lib/theme';

// Re-exported for consumers (e.g. ThemeToggle).
export type { ResolvedTheme, ThemeMode };

interface ThemeContextValue {
  mode: ThemeMode;
  resolved: ResolvedTheme;
  setMode: (mode: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  mode: 'system',
  resolved: 'light',
  setMode: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>('system');
  const [resolved, setResolved] = useState<ResolvedTheme>('light');

  useEffect(() => {
    const initial = getStoredTheme();
    setModeState(initial);
    applyTheme(initial);
    setResolved(resolveTheme(initial));
  }, []);

  // Follow OS changes while in "system" mode.
  useEffect(() => {
    if (mode !== 'system') return;
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      applyTheme('system');
      setResolved(resolveTheme('system'));
    };
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, [mode]);

  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // Storage may be unavailable (private mode); theme still applies for the session.
    }
    applyTheme(next);
    setResolved(resolveTheme(next));
  }, []);

  const value = useMemo(() => ({ mode, resolved, setMode }), [mode, resolved, setMode]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}
