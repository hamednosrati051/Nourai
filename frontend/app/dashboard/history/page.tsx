'use client';

import { useState } from 'react';
import { useImageJobs } from '@/features/image/hooks';
import { useAudioJobs, useAssetDownloadUrl } from '@/features/voice/hooks';
import { formatToman } from '@/lib/currency';
import { formatDateTime } from '@/lib/format';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { Pagination } from '@/components/Pagination';
import { ResponsiveTable } from '@/components/DataTable';
import type { AudioJobStatus, ImageJobStatus } from '@/types/api';

type Tab = 'image' | 'audio';

const IMAGE_STATUS: Record<ImageJobStatus, { label: string; badge: string }> = {
  queued: { label: 'در صف', badge: 'badge-neutral' },
  processing: { label: 'در حال تولید', badge: 'badge-info' },
  succeeded: { label: 'آماده', badge: 'badge-success' },
  failed: { label: 'ناموفق', badge: 'badge-danger' },
  cancelled: { label: 'لغوشده', badge: 'badge-neutral' },
};

const AUDIO_STATUS: Record<AudioJobStatus, { label: string; badge: string }> = {
  queued: { label: 'در صف', badge: 'badge-neutral' },
  processing: { label: 'در حال پردازش', badge: 'badge-info' },
  succeeded: { label: 'موفق', badge: 'badge-success' },
  failed: { label: 'ناموفق', badge: 'badge-danger' },
  cancelled: { label: 'لغوشده', badge: 'badge-neutral' },
};

/** Output history: generated images + voice jobs in tabs. */
export default function HistoryPage() {
  const [tab, setTab] = useState<Tab>('image');
  const [imagePage, setImagePage] = useState(1);
  const [audioPage, setAudioPage] = useState(1);

  const imageJobs = useImageJobs(imagePage);
  const audioJobs = useAudioJobs(audioPage);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">تاریخچه خروجی‌ها</h1>

      <div role="tablist" aria-label="نوع خروجی" className="flex gap-2">
        {(
          [
            { value: 'image', label: 'تصاویر تولیدشده', icon: '🎨' },
            { value: 'audio', label: 'پردازش‌های صوتی', icon: '🎙️' },
          ] as const
        ).map((t) => (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={tab === t.value}
            onClick={() => setTab(t.value)}
            className={`btn-sm flex items-center gap-1.5 rounded-xl px-4 font-semibold transition-colors ${
              tab === t.value
                ? 'bg-brand-600 text-white dark:bg-brand-500 dark:text-navy-950'
                : 'btn-secondary'
            }`}
          >
            <span aria-hidden="true">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'image' && (
        <section aria-label="تصاویر تولیدشده">
          {imageJobs.isLoading && <LoadingSpinner />}
          {imageJobs.isError && <ErrorState message="بارگذاری تاریخچه ناموفق بود." onRetry={() => imageJobs.refetch()} />}
          {imageJobs.data && imageJobs.data.items.length === 0 && (
            <EmptyState icon="🎨" title="تصویری تولید نشده" description="هنوز درخواستی برای تولید تصویر ثبت نکرده‌اید." actionLabel="تولید تصویر" actionHref="/dashboard/image" />
          )}
          {imageJobs.data && imageJobs.data.items.length > 0 && (
            <>
              <ResponsiveTable
                ariaLabel="تاریخچه تولید تصویر"
                keyOf={(j) => j.id}
                rows={imageJobs.data.items}
                cardHeader={(j) => <span className="line-clamp-1">{j.prompt}</span>}
                columns={[
                  {
                    header: 'پیش‌نمایش',
                    render: (j) =>
                      j.result_url ? (
                        <img src={j.result_url} alt="تصویر تولیدشده" loading="lazy" className="h-16 w-16 rounded-lg object-cover" />
                      ) : (
                        <span className="text-neutral-400">—</span>
                      ),
                    hideOnCard: true,
                  },
                  { header: 'توضیح', render: (j) => <span className="line-clamp-2 max-w-xs">{j.prompt}</span>, hideOnCard: true },
                  { header: 'نوع', render: (j) => (j.type === 'text_to_image' ? 'تولید از متن' : 'ویرایش تصویر') },
                  {
                    header: 'وضعیت',
                    render: (j) => <span className={IMAGE_STATUS[j.status].badge}>{IMAGE_STATUS[j.status].label}</span>,
                  },
                  {
                    header: 'هزینه',
                    render: (j) => (j.cost_irr != null ? <span className="tabular-nums">{formatToman(j.cost_irr)}</span> : '—'),
                  },
                  { header: 'تاریخ', render: (j) => formatDateTime(j.created_at) },
                ]}
              />
              <Pagination page={imagePage} totalPages={imageJobs.data.meta.total_pages} totalItems={imageJobs.data.meta.total_items} onPageChange={setImagePage} />
            </>
          )}
        </section>
      )}

      {tab === 'audio' && (
        <section aria-label="پردازش‌های صوتی">
          {audioJobs.isLoading && <LoadingSpinner />}
          {audioJobs.isError && <ErrorState message="بارگذاری تاریخچه ناموفق بود." onRetry={() => audioJobs.refetch()} />}
          {audioJobs.data && audioJobs.data.items.length === 0 && (
            <EmptyState icon="🎙️" title="پردازش صوتی نیست" description="هنوز فایل صوتی ارسال نکرده‌اید." actionLabel="تبدیل صوت به متن" actionHref="/dashboard/voice" />
          )}
          {audioJobs.data && audioJobs.data.items.length > 0 && (
            <>
              <ResponsiveTable
                ariaLabel="تاریخچه پردازش صوتی"
                keyOf={(j) => j.id}
                rows={audioJobs.data.items}
                cardHeader={(j) => <span className={AUDIO_STATUS[j.status].badge}>{AUDIO_STATUS[j.status].label}</span>}
                columns={[
                  {
                    header: 'وضعیت',
                    render: (j) => <span className={AUDIO_STATUS[j.status].badge}>{AUDIO_STATUS[j.status].label}</span>,
                  },
                  { header: 'متن استخراج‌شده', render: (j) => <span className="line-clamp-2 max-w-xs">{j.transcript ?? '—'}</span>, hideOnCard: true },
                  {
                    header: 'پاسخ صوتی',
                    render: (j) => <HistoryAudioCell assetId={j.output_asset_id} />,
                    hideOnCard: true,
                  },
                  { header: 'تاریخ', render: (j) => formatDateTime(j.created_at) },
                ]}
              />
              <Pagination page={audioPage} totalPages={audioJobs.data.meta.total_pages} totalItems={audioJobs.data.meta.total_items} onPageChange={setAudioPage} />
            </>
          )}
        </section>
      )}
    </div>
  );
}

/** Audio player cell backed by a signed asset download URL. */
function HistoryAudioCell({ assetId }: { assetId: string | null }) {
  const { data, isLoading } = useAssetDownloadUrl(assetId);
  if (!assetId) return <span className="text-neutral-400">—</span>;
  if (isLoading) return <span className="text-xs text-neutral-400">در حال آماده‌سازی…</span>;
  if (!data?.download_url) return <span className="text-neutral-400">—</span>;
  return <audio controls src={data.download_url} className="w-48" aria-label="پاسخ صوتی" />;
}
