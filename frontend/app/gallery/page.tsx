'use client';

import { Clapperboard, Images } from 'lucide-react';
import { useState } from 'react';
import { BRAND } from '@/lib/config';
import { useGallery } from '@/features/gallery/hooks';
import { PillHeader } from '@/components/PillHeader';
import { FloatingNav } from '@/components/FloatingNav';
import { EmptyState } from '@/components/EmptyState';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { ErrorState } from '@/components/ErrorState';
import { GalleryLightbox } from '@/components/GalleryLightbox';
import { ApiError, getErrorMessage } from '@/lib/api';

/**
 * Public gallery in the Binavira-inspired app style:
 * floating pill header + vertical right-side nav + navy/light card grid.
 * At most 20 latest admin-approved items from GET /api/v1/gallery.
 * Images and videos have separate tabs; the homepage carousel uses
 * images only (useGallery() default).
 */
type MediaKind = 'image' | 'video';

export default function GalleryPage() {
  const [media, setMedia] = useState<MediaKind>('image');
  const { data: items, isLoading, isError, error, refetch } = useGallery(media);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  const mediaLabel = media === 'video' ? 'ویدیو' : 'تصویر';

  return (
    <div className="min-h-screen">
      <PillHeader />
      <FloatingNav />

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-20 pt-28 sm:px-6 md:pe-24">
        <div className="mb-8">
          <p className="badge badge-warning mb-3">نگارخانه عمومی</p>
          <h1 className="text-3xl font-black">
            نگارخانه <span className="text-gradient">{BRAND.fa}</span>
          </h1>
          <p className="mt-2 text-sm text-neutral-600 dark:text-slate-400">
            منتخبی از تصاویر و ویدیوهای ساخته‌شده توسط کاربران که توسط تیم ما تأیید شده‌اند.
          </p>
        </div>

        <div role="tablist" aria-label="نوع رسانه" className="mb-8 flex gap-2">
          {(
            [
              { value: 'image', label: 'تصاویر' },
              { value: 'video', label: 'ویدیوها' },
            ] as { value: MediaKind; label: string }[]
          ).map((t) => (
            <button
              key={t.value}
              type="button"
              role="tab"
              aria-selected={media === t.value}
              onClick={() => {
                setMedia(t.value);
                setLightboxIndex(null);
              }}
              className={`btn-sm whitespace-nowrap rounded-xl px-4 font-semibold transition-colors ${
                media === t.value
                  ? 'bg-brand-600 text-white dark:bg-brand-500 dark:text-navy-950'
                  : 'btn-secondary'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {isLoading && <LoadingSpinner label="در حال بارگذاری نگارخانه…" />}

        {isError && (
          <ErrorState
            message={error instanceof ApiError ? getErrorMessage(error.code, error.message) : 'بارگذاری نگارخانه ناموفق بود.'}
            onRetry={() => refetch()}
          />
        )}

        {!isLoading && !isError && (!items || items.length === 0) && (
          <EmptyState
            icon={media === 'video' ? Clapperboard : Images}
            title={`هنوز ${mediaLabel}ی تأیید نشده است`}
            description={`به‌زودی ${mediaLabel}های تأییدشده کاربران در این نگارخانه نمایش داده می‌شود.`}
            actionLabel="بازگشت به صفحه اصلی"
            actionHref="/"
          />
        )}

        {!isLoading && !isError && items && items.length > 0 && media === 'image' && (
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4" aria-label="تصاویر نگارخانه">
            {items.map((item, i) => (
              <li
                key={item.id}
                className="group relative overflow-hidden rounded-2xl border border-neutral-200 bg-neutral-100 shadow-sm transition hover:-translate-y-1 hover:shadow-lg dark:border-white/10 dark:bg-navy-800 dark:shadow-black/30"
              >
                <button
                  type="button"
                  onClick={() => setLightboxIndex(i)}
                  aria-label={`نمایش بزرگ تصویر ${i + 1}`}
                  className="block w-full cursor-zoom-in"
                >
                  {/* Uniform square thumbnails for a tidy grid. */}
                  <div className="relative aspect-square w-full">
                    <img
                      src={item.thumbnail_url ?? item.image_url}
                      alt={item.alt_text ?? `تصویر نگارخانه ${BRAND.fa}`}
                      loading="lazy"
                      decoding="async"
                      className="absolute inset-0 h-full w-full object-cover transition-transform duration-300 group-hover:scale-110"
                    />
                  </div>
                </button>
                <span
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-x-0 bottom-0 h-1 bg-gradient-to-l from-brand-500 to-violet-500 opacity-0 transition group-hover:opacity-100"
                />
              </li>
            ))}
          </ul>
        )}

        {!isLoading && !isError && items && items.length > 0 && media === 'video' && (
          <ul className="grid grid-cols-1 gap-6 sm:grid-cols-2" aria-label="ویدیوهای نگارخانه">
            {items.map((item) => (
              <li
                key={item.id}
                className="overflow-hidden rounded-2xl border border-neutral-200 bg-neutral-100 shadow-sm dark:border-white/10 dark:bg-navy-800 dark:shadow-black/30"
              >
                <div className="relative aspect-video w-full bg-black">
                  <video
                    src={item.image_url}
                    controls
                    preload="metadata"
                    className="absolute inset-0 h-full w-full"
                  />
                </div>
                {item.prompt && (
                  <p className="px-4 py-3 text-sm text-neutral-600 dark:text-slate-400">{item.prompt}</p>
                )}
              </li>
            ))}
          </ul>
        )}

        {lightboxIndex !== null && items && media === 'image' && (
          <GalleryLightbox
            items={items}
            initialIndex={lightboxIndex}
            onClose={() => setLightboxIndex(null)}
          />
        )}
      </main>
    </div>
  );
}
