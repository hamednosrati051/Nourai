'use client';

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
  const audit = useAuditLog(page);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">گزارش حسابرسی</h1>

      {audit.isLoading && <LoadingSpinner />}
      {audit.isError && <ErrorState message="بارگذاری گزارش ناموفق بود." onRetry={() => audit.refetch()} />}
      {audit.data && audit.data.items.length === 0 && (
        <EmptyState icon="📋" title="رکوردی نیست" description="هنوز اقدامی در گزارش حسابرسی ثبت نشده است." />
      )}
      {audit.data && audit.data.items.length > 0 && (
        <>
          <ResponsiveTable
            ariaLabel="گزارش حسابرسی"
            keyOf={(a) => a.id}
            rows={audit.data.items}
            cardHeader={(a) => a.action}
            columns={[
              { header: 'اقدام', render: (a) => <span className="font-semibold">{a.action}</span> },
              { header: 'کنشگر', render: (a) => a.actor_label ?? `${a.actor_type}:${a.actor_id ?? '—'}` },
              { header: 'هدف', render: (a) => (a.target_type ? `${a.target_type}:${a.target_id ?? ''}` : '—'), hideOnCard: true },
              {
                header: 'جزئیات',
                render: (a) =>
                  a.details ? (
                    <span dir="ltr" className="block max-w-xs truncate text-xs tabular-nums" title={JSON.stringify(a.details)}>
                      {JSON.stringify(a.details)}
                    </span>
                  ) : (
                    '—'
                  ),
                hideOnCard: true,
              },
              { header: 'زمان', render: (a) => formatDateTime(a.created_at) },
            ]}
          />
          <Pagination page={page} totalPages={audit.data.meta.total_pages} totalItems={audit.data.meta.total_items} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
