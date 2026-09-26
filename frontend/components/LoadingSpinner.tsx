/** Centered loading spinner with an accessible label. */
export function LoadingSpinner({ label = 'در حال بارگذاری…' }: { label?: string }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col items-center justify-center gap-3 py-12">
      <span
        aria-hidden="true"
        className="h-10 w-10 animate-spin rounded-full border-4 border-neutral-200 border-t-brand-600 dark:border-white/15 dark:border-t-brand-400"
      />
      <span className="text-sm text-neutral-500 dark:text-slate-400">{label}</span>
    </div>
  );
}
