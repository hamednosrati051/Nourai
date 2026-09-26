'use client';

import { useState } from 'react';
import { useAdminPayments } from '@/features/admin/hooks';
import { formatToman } from '@/lib/currency';
import { formatDateTime } from '@/lib/format';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { Pagination } from '@/components/Pagination';
import { ResponsiveTable } from '@/components/DataTable';
import type { PaymentStatus } from '@/types/api';

const STATUS_META: Record<PaymentStatus, { label: string; badge: string }> = {
  pending: { label: 'در انتظار', badge: 'badge-warning' },
  paid: { label: 'پرداخت‌شده', badge: 'badge-success' },
  failed: { label: 'ناموفق', badge: 'badge-danger' },
  cancelled: { label: 'لغوشده', badge: 'badge-neutral' },
  expired: { label: 'منقضی‌شده', badge: 'badge-neutral' },
};

/** Admin payments list with status filter. */
export default function AdminPaymentsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');

  const payments = useAdminPayments(page, status);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">پرداخت‌ها</h1>

      <section aria-label="فیلتر پرداخت‌ها" className="card">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div>
            <label htmlFor="pay-status" className="label">
              وضعیت
            </label>
            <select
              id="pay-status"
              className="input sm:w-48"
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">همه</option>
              <option value="pending">در انتظار</option>
              <option value="paid">پرداخت‌شده</option>
              <option value="failed">ناموفق</option>
              <option value="cancelled">لغوشده</option>
              <option value="expired">منقضی‌شده</option>
            </select>
          </div>
        </div>
      </section>

      {payments.isLoading && <LoadingSpinner />}
      {payments.isError && <ErrorState message="بارگذاری پرداخت‌ها ناموفق بود." onRetry={() => payments.refetch()} />}
      {payments.data && payments.data.items.length === 0 && (
        <EmptyState icon="🧾" title="پرداختی نیست" description="با این فیلتر پرداختی یافت نشد." />
      )}
      {payments.data && payments.data.items.length > 0 && (
        <>
          <ResponsiveTable
            ariaLabel="فهرست پرداخت‌ها"
            keyOf={(p) => p.id}
            rows={payments.data.items}
            cardHeader={(p) => <span className="tabular-nums">{formatToman(p.amount_irr)}</span>}
            columns={[
              { header: 'مبلغ', render: (p) => <span className="tabular-nums">{formatToman(p.amount_irr)}</span> },
              {
                header: 'وضعیت',
                render: (p) => <span className={STATUS_META[p.status].badge}>{STATUS_META[p.status].label}</span>,
              },
              { header: 'درگاه', render: (p) => p.gateway, hideOnCard: true },
              { header: 'شناسه پیگیری', render: (p) => <span dir="ltr" className="tabular-nums">{p.track_id ?? '—'}</span>, hideOnCard: true },
              { header: 'تاریخ ثبت', render: (p) => formatDateTime(p.created_at) },
              { header: 'تاریخ پرداخت', render: (p) => formatDateTime(p.paid_at), hideOnCard: true },
            ]}
          />
          <Pagination page={page} totalPages={payments.data.meta.total_pages} totalItems={payments.data.meta.total_items} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
