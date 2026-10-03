'use client';

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
 * At most 20 latest admin-approved images from GET /api/v1/gallery only.
 */
export default function GalleryPage() {
  const { data: items, isLoading, isError, error, refetch } = useGallery();
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  return (
    <div className="min-h-screen">
      <PillHeader />
      <FloatingNav />

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-20 pt-28 sm:px-6 md:pe-24">
        <div className="mb-8">
          <p className="badge badge-warning mb-3">گالری عمومی</p>
          <h1 className="text-3xl font-black">
            گالری <span className="text-gradient">{BRAND.fa}</span>
          </h1>
          <p className="mt-2 text-sm text-neutral-600 dark:text-slate-400">
            منتخبی از تصاویر ساخته‌شده توسط کاربران که توسط تیم ما تأیید شده‌اند.
          </p>
        </div>

        {isLoading && <LoadingSpinner label="در حال بارگذاری گالری…" />}

        {isError && (
          <ErrorState
            message={error instanceof ApiError ? getErrorMessage(error.code, error.message) : 'بارگذاری گالری ناموفق بود.'}
            onRetry={() => refetch()}
          />
        )}

        {!isLoading && !isError && (!items || items.length === 0) && (
          <EmptyState
            icon="🖼️"
            title="هنوز تصویری تأیید نشده است"
            description="به‌زودی تصاویر تأییدشده کاربران در این گالری نمایش داده می‌شود."
            actionLabel="بازگشت به صفحه اصلی"
            actionHref="/"
          />
        )}

        {!isLoading && !isError && items && items.length > 0 && (
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4" aria-label="تصاویر گالری">
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
                  {/* Reserved aspect ratio from API dimensions prevents layout shift. */}
                  <div
                    className="relative w-full"
                    style={{
                      aspectRatio:
                        item.width && item.height ? `${item.width} / ${item.height}` : '1 / 1',
                    }}
                  >
                    <img
                      src={item.thumbnail_url ?? item.image_url}
                      alt={item.alt_text ?? `تصویر گالری ${BRAND.fa}`}
                      loading="lazy"
                      decoding="async"
                      className="absolute inset-0 h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
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

        {lightboxIndex !== null && items && (
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
