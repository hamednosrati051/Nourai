'use client';

import { Receipt } from 'lucide-react';
import { useState } from 'react';
import { useAdminPayments, useCancelPayment } from '@/features/admin/hooks';
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
  created: { label: 'در حال ایجاد', badge: 'badge-neutral' },
};

/** Admin payments list with status, mobile and date filters. */
export default function AdminPaymentsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [mobile, setMobile] = useState('');
  const [username, setUsername] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  // Applied filters (search runs on button/Enter, not on every keystroke).
  const [filters, setFilters] = useState({ status: '', mobile: '', username: '', date_from: '', date_to: '' });

  const payments = useAdminPayments(page, filters);
  const cancelPayment = useCancelPayment();

  const applyFilters = () => {
    setFilters({ status, mobile: mobile.trim(), username: username.trim(), date_from: dateFrom, date_to: dateTo });
    setPage(1);
  };

  const clearFilters = () => {
    setStatus('');
    setMobile('');
    setUsername('');
    setDateFrom('');
    setDateTo('');
    setFilters({ status: '', mobile: '', username: '', date_from: '', date_to: '' });
    setPage(1);
  };

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">پرداخت‌ها</h1>

      <section aria-label="فیلتر پرداخت‌ها" className="card">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:flex-wrap">
          <div>
            <label htmlFor="pay-status" className="label">
              وضعیت
            </label>
            <select
              id="pay-status"
              className="input sm:w-40"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">همه</option>
              <option value="pending">در انتظار</option>
              <option value="paid">پرداخت‌شده</option>
              <option value="failed">ناموفق</option>
              <option value="cancelled">لغوشده</option>
              <option value="expired">منقضی‌شده</option>
            </select>
          </div>
          <div>
            <label htmlFor="pay-mobile" className="label">
              شماره کاربر
            </label>
            <input
              id="pay-mobile"
              type="text"
              inputMode="tel"
              dir="ltr"
              placeholder="0912…"
              className="input sm:w-40"
              value={mobile}
              onChange={(e) => setMobile(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') applyFilters();
              }}
            />
          </div>
          <div>
            <label htmlFor="pay-username" className="label">
              یوزرنیم بات
            </label>
            <input
              id="pay-username"
              type="text"
              dir="ltr"
              placeholder="@username"
              className="input sm:w-40"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') applyFilters();
              }}
            />
          </div>
          <div>
            <label htmlFor="pay-date-from" className="label">
              از تاریخ
            </label>
            <input
              id="pay-date-from"
              type="date"
              className="input sm:w-40"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="pay-date-to" className="label">
              تا تاریخ
            </label>
            <input
              id="pay-date-to"
              type="date"
              className="input sm:w-40"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <button type="button" className="btn-primary btn-sm" onClick={applyFilters}>
              جستجو
            </button>
            <button type="button" className="btn-secondary btn-sm" onClick={clearFilters}>
              پاک کردن
            </button>
          </div>
        </div>
      </section>

      {payments.isLoading && <LoadingSpinner />}
      {payments.isError && <ErrorState message="بارگذاری پرداخت‌ها ناموفق بود." onRetry={() => payments.refetch()} />}
      {payments.data && payments.data.items.length === 0 && (
        <EmptyState icon={Receipt} title="پرداختی نیست" description="با این فیلتر پرداختی یافت نشد." />
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
                header: 'کاربر',
                render: (p) => p.user_mobile_masked ? (
                  <span dir="ltr" className="tabular-nums">{p.user_mobile_masked}</span>
                ) : p.bot_user ? (
                  <span className="text-sm">
                    <span className="tabular-nums" dir="ltr">{p.bot_user.platform_user_id}</span>
                    {p.bot_user.platform_username && (
                      <span className="block text-xs text-neutral-500" dir="ltr">@{p.bot_user.platform_username}</span>
                    )}
                  </span>
                ) : '—',
              },
              {
                header: 'وضعیت',
                render: (p) => <span className={STATUS_META[p.status].badge}>{STATUS_META[p.status].label}</span>,
              },
              { header: 'درگاه', render: (p) => p.gateway, hideOnCard: true },
              { header: 'شناسه پیگیری', render: (p) => <span dir="ltr" className="tabular-nums">{p.track_id ?? '—'}</span>, hideOnCard: true },
              { header: 'تاریخ ثبت', render: (p) => formatDateTime(p.created_at) },
              { header: 'تاریخ پرداخت', render: (p) => formatDateTime(p.paid_at), hideOnCard: true },
              {
                header: 'عملیات',
                render: (p) =>
                  p.status === 'pending' || p.status === 'created' ? (
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost text-error"
                      disabled={cancelPayment.isPending}
                      onClick={() => {
                        if (window.confirm('این پرداخت لغو شود؟')) {
                          cancelPayment.mutate(p.id);
                        }
                      }}
                    >
                      لغو
                    </button>
                  ) : (
                    '—'
                  ),
              },
            ]}
          />
          <Pagination page={page} totalPages={payments.data.meta.total_pages} totalItems={payments.data.meta.total_items} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
