'use client';

import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';

export type ToastKind = 'success' | 'error' | 'info';

interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastContextValue {
  toast: (message: string, kind?: ToastKind) => void;
}

const ToastContext = createContext<ToastContextValue>({ toast: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

const KIND_STYLES: Record<ToastKind, string> = {
  success: 'border-emerald-500/40 bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200',
  error: 'border-red-500/40 bg-red-50 text-red-900 dark:bg-red-950 dark:text-red-200',
  info: 'border-sky-500/40 bg-sky-50 text-sky-900 dark:bg-sky-950 dark:text-sky-200',
};

const KIND_ICONS: Record<ToastKind, string> = {
  success: '✅',
  error: '⚠️',
  info: 'ℹ️',
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const idRef = useRef(0);

  const toast = useCallback((message: string, kind: ToastKind = 'info') => {
    const id = ++idRef.current;
    setToasts((prev) => [...prev.slice(-2), { id, kind, message }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-4 z-[100] flex flex-col items-center gap-2 px-4"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className={`pointer-events-auto flex max-w-md items-start gap-2 rounded-xl border px-4 py-3 text-sm font-medium shadow-lg ${KIND_STYLES[t.kind]}`}
          >
            <span aria-hidden="true">{KIND_ICONS[t.kind]}</span>
            <span>{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
