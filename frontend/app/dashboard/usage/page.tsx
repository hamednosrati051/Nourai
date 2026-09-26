'use client';

import { useState } from 'react';
import { useUsage } from '@/features/usage/hooks';
import { useModels } from '@/features/models/hooks';
import { formatToman } from '@/lib/currency';
import { formatDateTime, formatNumber } from '@/lib/format';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { Pagination } from '@/components/Pagination';
import { ResponsiveTable } from '@/components/DataTable';
import type { ModelService, UsageStatus } from '@/types/api';

const SERVICE_LABELS: Record<ModelService, string> = {
  text: 'متن',
  audio: 'صوت',
  image: 'تصویر',
};

const STATUS_META: Record<UsageStatus, { label: string; badge: string }> = {
  succeeded: { label: 'موفق', badge: 'badge-success' },
  failed: { label: 'ناموفق', badge: 'badge-danger' },
  refunded: { label: 'برگشت‌خورده', badge: 'badge-warning' },
};

/** Usage history with server-side filters (service, model, date range). */
export default function UsagePage() {
  const [page, setPage] = useState(1);
  const [service, setService] = useState<ModelService | ''>('');
  const [modelId, setModelId] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');

  const models = useModels();
  const usage = useUsage({ page, service, modelId, from, to });

  const resetFilters = () => {
    setService('');
    setModelId('');
    setFrom('');
    setTo('');
    setPage(1);
  };

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">سابقه مصرف</h1>

      {/* Filters */}
      <section aria-label="فیلترهای مصرف" className="card">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label htmlFor="usage-service" className="label">
              سرویس
            </label>
            <select
              id="usage-service"
              className="input"
              value={service}
              onChange={(e) => {
                setService(e.target.value as ModelService | '');
                setPage(1);
              }}
            >
              <option value="">همه</option>
              <option value="text">متن</option>
              <option value="audio">صوت</option>
              <option value="image">تصویر</option>
            </select>
          </div>
          <div>
            <label htmlFor="usage-model" className="label">
              مدل
            </label>
            <select
              id="usage-model"
              className="input"
              value={modelId}
              onChange={(e) => {
                setModelId(e.target.value);
                setPage(1);
              }}
            >
              <option value="">همه مدل‌ها</option>
              {(models.data ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="usage-from" className="label">
              از تاریخ
            </label>
            <input
              id="usage-from"
              type="date"
              className="input"
              value={from}
              onChange={(e) => {
                setFrom(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <div>
            <label htmlFor="usage-to" className="label">
              تا تاریخ
            </label>
            <input
              id="usage-to"
              type="date"
              className="input"
              value={to}
              onChange={(e) => {
                setTo(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>
        <button type="button" onClick={resetFilters} className="btn-ghost btn-sm mt-4">
          پاک کردن فیلترها
        </button>
      </section>

      {/* Results */}
      {usage.isLoading && <LoadingSpinner />}
      {usage.isError && <ErrorState message="بارگذاری سابقه مصرف ناموفق بود." onRetry={() => usage.refetch()} />}
      {usage.data && usage.data.items.length === 0 && (
        <EmptyState icon="📊" title="مصرفی ثبت نشده" description="با این فیلترها سابقه‌ای پیدا نشد." />
      )}
      {usage.data && usage.data.items.length > 0 && (
        <>
          <ResponsiveTable
            ariaLabel="سابقه مصرف"
            keyOf={(u) => u.id}
            rows={usage.data.items}
            cardHeader={(u) => (
              <span className="tabular-nums">{formatToman(u.cost_irr)}</span>
            )}
            columns={[
              { header: 'سرویس', render: (u) => SERVICE_LABELS[u.service] ?? u.service },
              { header: 'مدل', render: (u) => u.model_name ?? u.model_id, hideOnCard: true },
              {
                header: 'مصرف',
                render: (u) =>
                  u.usage_amount != null ? `${formatNumber(u.usage_amount)} ${u.usage_unit ?? ''}` : '—',
              },
              {
                header: 'هزینه',
                render: (u) => <span className="tabular-nums">{formatToman(u.cost_irr)}</span>,
              },
              {
                header: 'وضعیت',
                render: (u) => <span className={STATUS_META[u.status].badge}>{STATUS_META[u.status].label}</span>,
              },
              { header: 'زمان', render: (u) => formatDateTime(u.created_at) },
            ]}
          />
          <Pagination page={page} totalPages={usage.data.meta.total_pages} totalItems={usage.data.meta.total_items} onPageChange={setPage} />
        </>
      )}
    </div>
  );
}
