'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Home, Images, User } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useMe } from '@/features/auth/hooks';

interface NavEntry {
  href: string;
  label: string;
  icon: LucideIcon;
}

/**
 * Floating vertical navigation on the right edge (RTL).
 * Desktop: vertically centered rail. Mobile: bottom floating bar.
 */
export function FloatingNav() {
  const pathname = usePathname();
  const { data: user } = useMe();

  const items: NavEntry[] = [
    { href: '/', label: 'خانه', icon: Home },
    { href: '/gallery', label: 'نگارخانه', icon: Images },
    { href: user ? '/dashboard' : '/auth/login', label: 'حساب کاربری', icon: User },
  ];

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <nav
      aria-label="ناوبری شناور"
      className="pointer-events-none fixed inset-x-0 bottom-4 z-40 flex justify-center px-4 md:inset-x-auto md:bottom-auto md:right-5 md:top-1/2 md:-translate-y-1/2 md:px-0"
    >
      <ul className="floating-nav flex-row gap-1 p-2 md:flex-col">
        {items.map((item) => {
          const active = isActive(item.href);
          const Icon = item.icon;
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? 'page' : undefined}
                title={item.label}
                className={`flex h-12 w-12 flex-col items-center justify-center gap-0.5 rounded-2xl transition-colors md:h-14 md:w-14 ${
                  active
                    ? 'bg-brand-500/15 text-brand-700 dark:bg-brand-400/15 dark:text-brand-300'
                    : 'text-neutral-500 hover:bg-neutral-100 hover:text-neutral-800 dark:text-slate-400 dark:hover:bg-white/10 dark:hover:text-slate-100'
                }`}
              >
                <Icon aria-hidden="true" className="h-6 w-6 leading-none md:h-7 md:w-7" />
                <span className="text-[10px] font-medium leading-none">{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
