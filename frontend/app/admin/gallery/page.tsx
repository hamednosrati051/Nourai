'use client';

import { useState } from 'react';
import {
  useAdminGallery,
  useApproveGalleryItem,
  useRejectGalleryItem,
  useRemoveGalleryItem,
} from '@/features/admin/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { Modal } from '@/components/Modal';
import { useToast } from '@/components/Toast';
import { formatDateTime } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';
import { BRAND } from '@/lib/config';
import type { GalleryQueueItem } from '@/types/api';

type Tab = 'pending' | 'approved' | 'rejected';

/** Admin gallery moderation: approve / reject / remove items. */
export default function AdminGalleryPage() {
  const { toast } = useToast();
  const [tab, setTab] = useState<Tab>('pending');
  const [rejectTarget, setRejectTarget] = useState<GalleryQueueItem | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  const queue = useAdminGallery(tab);
  const approve = useApproveGalleryItem();
  const reject = useRejectGalleryItem();
  const remove = useRemoveGalleryItem();

  const onApprove = (item: GalleryQueueItem) => {
    approve.mutate(item.asset_id, {
      onSuccess: () => toast('تصویر تأیید و در گالری منتشر شد.', 'success'),
      onError: (err) =>
        toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'تأیید ناموفق بود.', 'error'),
    });
  };

  const onReject = () => {
    if (!rejectTarget) return;
    reject.mutate(
      { assetId: rejectTarget.asset_id, reason: rejectReason || undefined },
      {
        onSuccess: () => {
          setRejectTarget(null);
          setRejectReason('');
          toast('تصویر رد شد.', 'success');
        },
        onError: (err) =>
          toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'رد ناموفق بود.', 'error'),
      },
    );
  };

  const onRemove = (item: GalleryQueueItem) => {
    if (!window.confirm('این تصویر از گالری عمومی خارج می‌شود (بدون حذف فایل اصلی). ادامه می‌دهید؟')) return;
    remove.mutate(item.asset_id, {
      onSuccess: () => toast('تصویر از گالری خارج شد.', 'success'),
      onError: (err) =>
        toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'عملیات ناموفق بود.', 'error'),
    });
  };

  const tabs: { value: Tab; label: string }[] = [
    { value: 'pending', label: 'در انتظار بررسی' },
    { value: 'approved', label: 'تأییدشده' },
    { value: 'rejected', label: 'ردشده' },
  ];

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">مدیریت گالری</h1>
      <p className="text-sm text-neutral-600 dark:text-slate-400">
        فقط تصاویر تأییدشده در گالری عمومی و چرخش صفحه اصلی نمایش داده می‌شوند (حداکثر ۲۰ تصویر آخر).
      </p>

      <div role="tablist" aria-label="وضعیت بررسی" className="flex gap-2 overflow-x-auto pb-1">
        {tabs.map((t) => (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={tab === t.value}
            onClick={() => setTab(t.value)}
            className={`btn-sm whitespace-nowrap rounded-xl px-4 font-semibold transition-colors ${
              tab === t.value
                ? 'bg-brand-600 text-white dark:bg-brand-500 dark:text-navy-950'
                : 'btn-secondary'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {queue.isLoading && <LoadingSpinner />}
      {queue.isError && <ErrorState message="بارگذاری صف گالری ناموفق بود." onRetry={() => queue.refetch()} />}
      {queue.data && queue.data.length === 0 && (
        <EmptyState
          icon="🖼️"
          title={tab === 'pending' ? 'صف بررسی خالی است' : 'موردی نیست'}
          description={tab === 'pending' ? 'تصویر جدیدی برای بررسی وجود ندارد.' : 'در این وضعیت تصویری ثبت نشده است.'}
        />
      )}

      {queue.data && queue.data.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {queue.data.map((item) => (
            <li key={item.id} className="card !p-3">
              <div
                className="relative w-full overflow-hidden rounded-xl bg-neutral-100 dark:bg-navy-800"
                style={{ aspectRatio: item.width && item.height ? `${item.width} / ${item.height}` : '1 / 1' }}
              >
                <img
                  src={item.thumbnail_url ?? item.image_url}
                  alt={item.alt_text ?? `تصویر گالری ${BRAND.fa}`}
                  loading="lazy"
                  className="absolute inset-0 h-full w-full object-cover"
                />
              </div>
              <div className="mt-2 flex items-center justify-between text-xs text-neutral-500 dark:text-slate-400">
                <span dir="ltr">{item.user_mobile_masked}</span>
                <span>{formatDateTime(item.reviewed_at)}</span>
              </div>
              {item.prompt_excerpt && (
                <p className="mt-1 line-clamp-2 text-xs text-neutral-600 dark:text-slate-400">{item.prompt_excerpt}</p>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                {tab === 'pending' && (
                  <>
                    <button
                      type="button"
                      onClick={() => onApprove(item)}
                      disabled={approve.isPending}
                      className="btn-primary btn-sm flex-1"
                    >
                      تأیید
                    </button>
                    <button
                      type="button"
                      onClick={() => setRejectTarget(item)}
                      disabled={reject.isPending}
                      className="btn-danger btn-sm flex-1"
                    >
                      رد
                    </button>
                  </>
                )}
                {tab === 'approved' && (
                  <button
                    type="button"
                    onClick={() => onRemove(item)}
                    disabled={remove.isPending}
                    className="btn-secondary btn-sm flex-1"
                  >
                    خارج کردن از گالری
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal open={!!rejectTarget} title="رد تصویر" onClose={() => setRejectTarget(null)}>
        <p className="mb-3 text-sm text-neutral-600 dark:text-slate-400">
          دلیل رد (اختیاری؛ در گزارش حسابرسی ثبت می‌شود):
        </p>
        <textarea
          rows={3}
          className="input resize-none"
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          aria-label="دلیل رد"
        />
        <div className="mt-4 flex gap-2">
          <button type="button" onClick={onReject} disabled={reject.isPending} className="btn-danger flex-1">
            {reject.isPending ? 'در حال ثبت…' : 'تأیید رد'}
          </button>
          <button type="button" onClick={() => setRejectTarget(null)} className="btn-secondary flex-1">
            انصراف
          </button>
        </div>
      </Modal>
    </div>
  );
}
