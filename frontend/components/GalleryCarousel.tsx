'use client';

import { Images } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import type { GalleryItem } from '@/types/api';
import { BRAND, GALLERY_MAX_ITEMS } from '@/lib/config';
import { EmptyState } from './EmptyState';
import { LoadingSpinner } from './LoadingSpinner';

const AUTOPLAY_MS = 5000;

interface GalleryCarouselProps {
  items: GalleryItem[] | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry?: () => void;
}

/**
 * Homepage "user creations" slider.
 * Consumes ONLY the public gallery API (max 20 approved images).
 * Autoplay pauses on hover/focus and is disabled under prefers-reduced-motion.
 */
export function GalleryCarousel({ items, isLoading, isError, onRetry }: GalleryCarouselProps) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const timerRef = useRef<number | null>(null);

  const slides = (items ?? []).slice(0, GALLERY_MAX_ITEMS);
  const count = slides.length;

  const goTo = useCallback(
    (next: number) => {
      if (count === 0) return;
      setIndex(((next % count) + count) % count);
    },
    [count],
  );

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReducedMotion(media.matches);
    const onChange = (e: MediaQueryListEvent) => setReducedMotion(e.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    if (timerRef.current) window.clearInterval(timerRef.current);
    if (count <= 1 || paused || reducedMotion) return;
    timerRef.current = window.setInterval(() => {
      setIndex((i) => (i + 1) % count);
    }, AUTOPLAY_MS);
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, [count, paused, reducedMotion]);

  if (isLoading) return <LoadingSpinner label="در حال بارگذاری تصاویر…" />;
  if (isError) {
    return (
      <div className="card text-center">
        <p className="text-sm text-neutral-600 dark:text-slate-400">بارگذاری تصاویر ناموفق بود.</p>
        {onRetry && (
          <button type="button" onClick={onRetry} className="btn-secondary btn-sm mt-3">
            تلاش مجدد
          </button>
        )}
      </div>
    );
  }
  if (count === 0) {
    return (
      <EmptyState
        icon={Images}
        title="هنوز تصویری در گالری نیست"
        description="به‌زودی ساخته‌های کاربران تأییدشده در اینجا نمایش داده می‌شود."
        actionLabel="مشاهده گالری"
        actionHref="/gallery"
      />
    );
  }

  const current = slides[index]!;

  return (
    <div
      className="relative"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
    >
      <div
        role="region"
        aria-roledescription="carousel"
        aria-label="ساخته‌های کاربران"
        className="relative overflow-hidden rounded-2xl border border-neutral-200 bg-neutral-100 dark:border-white/10 dark:bg-navy-900"
      >
        {/* Reserved aspect-ratio box prevents layout shift. */}
        <div className="relative aspect-[4/3] w-full sm:aspect-[16/9]">
          {slides.map((item, i) => (
            <div
              key={item.id}
              aria-hidden={i !== index}
              aria-roledescription="slide"
              aria-label={`${i + 1} از ${count}`}
              className={`absolute inset-0 transition-opacity duration-500 ${
                i === index ? 'opacity-100' : 'pointer-events-none opacity-0'
              }`}
            >
              <img
                src={item.thumbnail_url ?? item.image_url}
                alt={item.alt_text ?? `تصویر ساخته‌شده توسط کاربران ${BRAND.fa}`}
                loading={i === 0 ? 'eager' : 'lazy'}
                decoding="async"
                className="h-full w-full object-cover"
              />
            </div>
          ))}
        </div>

        {count > 1 && (
          <>
            <button
              type="button"
              onClick={() => goTo(index - 1)}
              aria-label="تصویر قبلی"
              className="absolute top-1/2 right-3 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-xl text-white backdrop-blur transition hover:bg-black/70"
            >
              <span aria-hidden="true">‹</span>
            </button>
            <button
              type="button"
              onClick={() => goTo(index + 1)}
              aria-label="تصویر بعدی"
              className="absolute top-1/2 left-3 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-black/50 text-xl text-white backdrop-blur transition hover:bg-black/70"
            >
              <span aria-hidden="true">›</span>
            </button>
          </>
        )}
      </div>

      {count > 1 && (
        <div className="mt-3 flex items-center justify-center gap-2" role="tablist" aria-label="انتخاب تصویر">
          {slides.map((item, i) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={i === index}
              aria-label={`تصویر ${i + 1}`}
              onClick={() => goTo(i)}
              className="flex h-11 items-center px-1.5"
            >
              <span
                aria-hidden="true"
                className={`block h-2.5 rounded-full transition-all ${
                  i === index ? 'w-8 bg-brand-600 dark:bg-brand-400' : 'w-2.5 bg-neutral-300 dark:bg-white/15'
                }`}
              />
            </button>
          ))}
        </div>
      )}

      <div className="mt-4 text-center">
        <Link href="/gallery" className="btn-secondary btn-sm">
          مشاهده گالری
        </Link>
      </div>

      <span className="sr-only" aria-live="polite">
        تصویر {index + 1} از {count}
      </span>
    </div>
  );
}
