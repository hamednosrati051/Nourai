'use client';

import { useState } from 'react';
import { useAdminJobs, useAdminCancelJob, type AdminJob } from '@/features/admin/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { ResponsiveTable } from '@/components/DataTable';
import { useToast } from '@/components/Toast';
import { formatDateTime } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';

const CAPABILITY_LABEL: Record<string, string> = {
  image: 'تصویر',
  audio: 'صوت',
  tts: 'متن به صوت',
  chat: 'گفتگو',
};

const STATUS_LABEL: Record<string, string> = {
  queued: 'در صف',
  processing: 'در حال پردازش',
};

/** Admin live jobs: monitor queued/processing jobs and cancel stuck ones. */
export default function AdminJobsPage() {
  const { toast } = useToast();
  const queued = useAdminJobs('queued');
  const processing = useAdminJobs('processing');
  const cancel = useAdminCancelJob();
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const onCancel = (job: AdminJob) => {
    if (!window.confirm(`درخواست ${job.id} لغو شود؟ مبلغ رزروشده به کیف پول کاربر برمی‌گردد.`)) return;
    setCancellingId(job.id);
    cancel.mutate(job.id, {
      onSuccess: () => {
        toast('درخواست لغو شد.', 'success');
        setCancellingId(null);
      },
      onError: (err) => {
        toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'لغو ناموفق بود.', 'error');
        setCancellingId(null);
      },
    });
  };

  const isLoading = queued.isLoading || processing.isLoading;
  const isError = queued.isError || processing.isError;
  const refetch = () => {
    queued.refetch();
    processing.refetch();
  };
  const items = [
    ...(processing.data?.items ?? []),
    ...(queued.data?.items ?? []),
  ];

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-extrabold">درخواست‌های جاری</h1>
        <p className="mt-1 text-sm text-neutral-500">
          درخواست‌های در صف و در حال پردازش. لغو، مبلغ رزروشده را به کیف پول کاربر برمی‌گرداند.
        </p>
      </div>

      {isLoading && <LoadingSpinner label="در حال بارگذاری…" />}
      {isError && <ErrorState message="بارگذاری ناموفق بود." onRetry={refetch} />}
      {!isLoading && !isError && items.length === 0 && (
        <EmptyState icon="📭" title="درخواست جاری نیست" description="همه درخواست‌ها تعیین تکلیف شده‌اند." />
      )}

      {items.length > 0 && (
        <ResponsiveTable<AdminJob>
          ariaLabel="درخواست‌های جاری"
          columns={[
            { header: 'سرویس', render: (j: AdminJob) => CAPABILITY_LABEL[j.capability] ?? j.capability },
            { header: 'وضعیت', render: (j: AdminJob) => STATUS_LABEL[j.status] ?? j.status },
            { header: 'کاربر', render: (j: AdminJob) => <span dir="ltr">{j.user_mobile_masked ?? '—'}</span> },
            {
              header: 'متن',
              render: (j: AdminJob) => (
                <span className="line-clamp-2 max-w-64 text-sm">{j.prompt_text || '—'}</span>
              ),
            },
            { header: 'ایجاد', render: (j: AdminJob) => (j.created_at ? formatDateTime(j.created_at) : '—') },
            {
              header: '',
              render: (j: AdminJob) => (
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  disabled={cancellingId === j.id}
                  onClick={() => onCancel(j)}
                >
                  {cancellingId === j.id ? 'در حال لغو…' : 'لغو'}
                </button>
              ),
            },
          ]}
          rows={items}
          keyOf={(j) => j.id}
        />
      )}
    </div>
  );
}
