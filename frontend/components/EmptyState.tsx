import Link from 'next/link';

interface EmptyStateProps {
  icon?: string;
  title: string;
  description?: string;
  actionLabel?: string;
  actionHref?: string;
  onAction?: () => void;
}

/** Friendly empty state; never renders fake data. */
export function EmptyState({ icon = '📭', title, description, actionLabel, actionHref, onAction }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-neutral-300 px-6 py-12 text-center dark:border-white/15">
      <span aria-hidden="true" className="text-4xl">
        {icon}
      </span>
      <h3 className="text-base font-bold text-neutral-800 dark:text-slate-200">{title}</h3>
      {description && <p className="max-w-sm text-sm text-neutral-500 dark:text-slate-400">{description}</p>}
      {actionLabel && actionHref && (
        <Link href={actionHref} className="btn-secondary btn-sm mt-3">
          {actionLabel}
        </Link>
      )}
      {actionLabel && onAction && !actionHref && (
        <button type="button" onClick={onAction} className="btn-secondary btn-sm mt-3">
          {actionLabel}
        </button>
      )}
    </div>
  );
}
