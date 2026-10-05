'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BRAND } from '@/lib/config';
import { useMe } from '@/features/auth/hooks';
import { ThemeToggle } from './ThemeToggle';

/** Public site header: logo, gallery link, theme control, auth CTA. */
export function Header() {
  const pathname = usePathname();
  const { data: user, isLoading } = useMe();
  const isAdminArea = pathname.startsWith('/noura-roham1197');
  const isAuthed = !!user;

  const ctaHref = isAdminArea ? '/noura-roham1197' : isAuthed ? '/dashboard' : '/auth/login';
  const ctaLabel = isAdminArea ? 'پنل ادمین' : isAuthed ? 'داشبورد من' : 'ثبت‌نام / ورود';

  return (
    <header className="sticky top-0 z-40 border-b border-neutral-200 bg-white/90 backdrop-blur dark:border-white/10 dark:bg-navy-950/90">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2" aria-label={`${BRAND.fa} — صفحه اصلی`}>
          <span
            aria-hidden="true"
            className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 text-xl font-black text-white dark:text-navy-950"
          >
            ن
          </span>
          <span className="text-xl font-extrabold tracking-tight">{BRAND.fa}</span>
        </Link>

        <nav aria-label="ناوبری اصلی" className="flex items-center gap-1 sm:gap-2">
          <Link
            href="/gallery"
            className={`btn-ghost btn-sm ${pathname === '/gallery' ? 'bg-neutral-100 dark:bg-navy-800' : ''}`}
          >
            گالری
          </Link>
          <ThemeToggle compact />
          <Link href={ctaHref} className="btn-primary btn-sm">
            {isLoading ? '…' : ctaLabel}
          </Link>
        </nav>
      </div>
    </header>
  );
}
