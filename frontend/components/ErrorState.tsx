'use client';

import { TriangleAlert } from 'lucide-react';

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

/** Error panel with an optional retry action. Never shows raw provider errors. */
export function ErrorState({ title = 'خطایی رخ داد', message, onRetry }: ErrorStateProps) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-6 py-10 text-center dark:border-red-900/50 dark:bg-red-950/30"
    >
      <TriangleAlert aria-hidden="true" className="h-10 w-10 text-red-400 dark:text-red-500" />
      <h3 className="text-base font-bold text-red-800 dark:text-red-300">{title}</h3>
      <p className="max-w-sm text-sm text-red-700 dark:text-red-400">{message}</p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn-secondary btn-sm mt-3">
          تلاش مجدد
        </button>
      )}
    </div>
  );
}
