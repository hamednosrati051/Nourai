'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Download, X } from 'lucide-react';
import type { GalleryItem } from '@/types/api';
import { BRAND } from '@/lib/config';
import { PromptBox } from './PromptBox';

const SWIPE_THRESHOLD_PX = 50;

/**
 * Fullscreen swipeable lightbox for the public gallery, with download.
 * Touch swipe on mobile, arrow keys on desktop, Esc to close.
 */
export function GalleryLightbox({
  items,
  initialIndex,
  onClose,
}: {
  items: GalleryItem[];
  initialIndex: number;
  onClose: () => void;
}) {
  const [index, setIndex] = useState(initialIndex);
  const [downloading, setDownloading] = useState(false);
  const touchX = useRef<number | null>(null);

  const count = items.length;
  const go = useCallback(
    (dir: 1 | -1) => setIndex((i) => (i + dir + count) % count),
    [count],
  );

  // Keyboard navigation.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      // Visual direction (RTL): left arrow = next, right arrow = previous.
      else if (e.key === 'ArrowLeft') go(1);
      else if (e.key === 'ArrowRight') go(-1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go, onClose]);

  // Lock body scroll while open.
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  const onTouchStart = (e: React.TouchEvent) => {
    touchX.current = e.touches[0]?.clientX ?? null;
  };
  const onTouchEnd = (e: React.TouchEvent) => {
    if (touchX.current === null) return;
    const dx = (e.changedTouches[0]?.clientX ?? 0) - touchX.current;
    touchX.current = null;
    if (Math.abs(dx) < SWIPE_THRESHOLD_PX) return;
    // Swipe left (dx<0) = next in RTL reading order.
    go(dx < 0 ? 1 : -1);
  };

  const download = async () => {
    const item = items[index];
    if (!item || downloading) return;
    setDownloading(true);
    try {
      const res = await fetch(item.image_url);
      if (!res.ok) throw new Error('fetch failed');
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `nourai-${item.id.slice(0, 8)}.jpg`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 5000);
    } catch {
      window.open(item.image_url, '_blank', 'noopener');
    } finally {
      setDownloading(false);
    }
  };

  const item = items[index];
  if (!item) return null;

  return (
    <div
      className="fixed inset-0 z-[90] flex flex-col bg-black/95 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="نمایش بزرگ تصویر گالری"
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-3 text-white">
        <span className="text-sm font-semibold tabular-nums" dir="rtl">
          {index + 1} از {count}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={download}
            disabled={downloading}
            className="btn-primary btn-sm inline-flex items-center gap-1.5 disabled:opacity-60"
          >
            {downloading ? 'در حال دانلود…' : (
              <span className="inline-flex items-center gap-1.5">
                <Download aria-hidden="true" className="h-4 w-4" />
                دانلود
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="بستن"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-white transition hover:bg-white/20"
          >
            <X aria-hidden="true" className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* Image area */}
      <div
        className="relative flex flex-1 flex-col items-center justify-center overflow-hidden px-12 pb-4"
        onClick={(e) => {
          if (e.target === e.currentTarget) onClose();
        }}
      >
        <div className="relative flex flex-1 items-center justify-center overflow-hidden">
        {/* Previous (right in RTL) */}
        <button
          type="button"
          onClick={() => go(-1)}
          aria-label="تصویر قبلی"
          className="absolute right-2 top-1/2 z-10 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-2xl text-white transition hover:bg-white/25"
        >
          ‹
        </button>
        <img
          key={item.id}
          src={item.image_url}
          alt={item.alt_text ?? `تصویر گالری ${BRAND.fa}`}
          className="max-h-full max-w-full rounded-xl object-contain shadow-2xl"
          draggable={false}
        />
        {/* Next (left in RTL) */}
        <button
          type="button"
          onClick={() => go(1)}
          aria-label="تصویر بعدی"
          className="absolute left-2 top-1/2 z-10 flex h-11 w-11 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 text-2xl text-white transition hover:bg-white/25"
        >
          ›
        </button>
        </div>
        {/* User prompt — full text, Binavira-style: heading + complete prompt */}
        {item.prompt && (
          <div className="mt-3 w-full max-w-2xl">
            <PromptBox prompt={item.prompt} dark />
          </div>
        )}
      </div>
    </div>
  );
}
