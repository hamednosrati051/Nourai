import { formatNumber } from '@/lib/format';

interface PaginationProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  totalItems?: number;
}

/** Server-side pagination controls (RTL-aware). */
export function Pagination({ page, totalPages, onPageChange, totalItems }: PaginationProps) {
  if (totalPages <= 1) return null;
  return (
    <nav aria-label="صفحه‌بندی" className="flex flex-wrap items-center justify-center gap-2 pt-4">
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        aria-label="صفحه قبلی"
        className="btn-secondary btn-sm"
      >
        قبلی
      </button>
      <span aria-current="page" className="px-2 text-sm text-neutral-600 dark:text-slate-400">
        صفحه {formatNumber(page)} از {formatNumber(totalPages)}
        {totalItems !== undefined && <> ({formatNumber(totalItems)} مورد)</>}
      </span>
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        aria-label="صفحه بعدی"
        className="btn-secondary btn-sm"
      >
        بعدی
      </button>
    </nav>
  );
}
