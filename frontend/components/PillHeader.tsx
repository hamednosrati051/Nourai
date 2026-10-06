'use client';

import Link from 'next/link';
import { Image as ImageIcon, Newspaper } from 'lucide-react';
import { BRAND } from '@/lib/config';
import { useMe } from '@/features/auth/hooks';
import { ThemeToggle } from './ThemeToggle';

/** Floating pill-shaped header, centered at the top of the page. */
export function PillHeader() {
  const { data: user, isLoading } = useMe();
  const authed = !!user;

  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-50 flex justify-center sm:top-5 sm:px-4">
      <header className="pill-header">
        <Link href="/" className="flex items-center gap-2" aria-label={`${BRAND.fa} — صفحه اصلی`}>
          <span
            aria-hidden="true"
            className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-brand-600 text-lg font-black text-white dark:text-navy-950"
          >
            ن
          </span>
          <span className="hidden text-lg font-extrabold tracking-tight sm:inline">{BRAND.fa}</span>
        </Link>

        <span aria-hidden="true" className="h-6 w-px bg-neutral-200 dark:bg-white/10" />

        <Link
          href="/gallery"
          className="btn-ghost btn-sm whitespace-nowrap"
          aria-label="نگارخانه"
        >
          <ImageIcon className="h-4 w-4 sm:hidden" />
          <span className="hidden sm:inline">نگارخانه</span>
        </Link>

        <Link
          href="/blog"
          className="btn-ghost btn-sm whitespace-nowrap"
          aria-label="بلاگ"
        >
          <Newspaper className="h-4 w-4 sm:hidden" />
          <span className="hidden sm:inline">بلاگ</span>
        </Link>

        <ThemeToggle compact />

        <Link href={authed ? '/dashboard' : '/auth/login'} className="btn-primary btn-sm whitespace-nowrap">
          {isLoading ? '…' : authed ? 'داشبورد' : (
            <>
              <span className="sm:hidden">ورود</span>
              <span className="hidden sm:inline">ثبت‌نام / ورود</span>
            </>
          )}
        </Link>
      </header>
    </div>
  );
}
