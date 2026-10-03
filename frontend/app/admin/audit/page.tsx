'use client';

import { ClipboardList } from 'lucide-react';
import { useState } from 'react';
import { useAuditLog } from '@/features/admin/hooks';
import { formatDateTime } from '@/lib/format';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { Pagination } from '@/components/Pagination';
import { ResponsiveTable } from '@/components/DataTable';

/** Admin audit log: every admin action, recorded. */
export default function AdminAuditPage() {
  const [page, setPage] = useState(1);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const audit = useAuditLog(page, search);

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearch(searchInput.trim());
    setPage(1);
  };

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">گزارش حسابرسی</h1>

      <form onSubmit={submitSearch} className="flex gap-2">
        <input
          type="search"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="جستجوی کاربر با شماره موبایل…"
          dir="ltr"
          className="input max-w-xs text-left"
          aria-label="جستجوی کاربر در گزارش حسابرسی"
        />
        <button type="submit" className="btn-secondary btn-sm">
          جستجو
        </button>
        {search && (
          <button
            type="button"
            className="btn-ghost btn-sm"
            onClick={() => {
              setSearchInput('');
              setSearch('');
              setPage(1);
            }}
          >
            پاک کردن
          </button>
        )}
      </form>

      {audit.isLoading && <LoadingSpinner />}
      {audit.isError && <ErrorState message="بارگذاری گزارش ناموفق بود." onRetry={() => audit.refetch()} />}
      {audit.data && audit.data.items.length === 0 && (
        <EmptyState icon={ClipboardList} title="رکوردی نیست" description="هنوز اقدامی در گزارش حسابرسی ثبت نشده است." />
      )}
      {audit.data && audit.data.items.length > 0 && (
        <>
          <ResponsiveTable
            ariaLabel="گزارش حسابرسی"
            keyOf={(a) => a.id}
            rows={audit.data.items}
            cardHeader={(a) => a.action}
            columns={[
              { header: 'زمان', render: (a) => formatDateTime(a.created_at) },
              { header: 'اقدام', render: (a) => <span className="font-semibold">{a.action}</span> },
              { header: 'کنشگر', render: (a) => a.actor_label ?? a.actor_type },
              { header: 'هدف', render: (a) => a.target_label ?? a.target_type ?? '—', hideOnCard: true },
              {
                header: 'جزئیات',
                render: (a) =>
                  a.metadata ? (
                    <span dir="ltr" className="block max-w-xs truncate text-xs tabular-nums" title={JSON.stringify(a.metadata)}>
                      {JSON.stringify(a.metadata)}
                    </span>
                  ) : (
                    '—'
                  ),
                hideOnCard: true,
              },
            ]}
          />
          <Pagination page={page} totalPages={audit.data.meta.total_pages} totalItems={audit.data.meta.total_items} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
