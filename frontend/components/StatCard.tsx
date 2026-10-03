import type { LucideIcon } from 'lucide-react';

interface StatCardProps {
  label: string;
  value: string;
  hint?: string;
  icon?: LucideIcon;
  accent?: 'brand' | 'success' | 'info' | 'danger';
}

/** Small KPI card used on dashboards. */
export function StatCard({ label, value, hint, icon: Icon, accent = 'brand' }: StatCardProps) {
  const accents: Record<NonNullable<StatCardProps['accent']>, string> = {
    brand: 'text-brand-700 dark:text-brand-400',
    success: 'text-emerald-700 dark:text-emerald-400',
    info: 'text-sky-700 dark:text-sky-400',
    danger: 'text-red-700 dark:text-red-400',
  };
  return (
    <div className="card">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-neutral-500 dark:text-slate-400">{label}</p>
        {Icon && (
          <Icon aria-hidden="true" className="h-5 w-5" />
        )}
      </div>
      <p className={`mt-2 text-2xl font-extrabold tabular-nums ${accents[accent]}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-neutral-500 dark:text-slate-400">{hint}</p>}
    </div>
  );
}
