'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export interface NavItem {
  href: string;
  label: string;
  icon: string;
}

/**
 * Panel navigation: horizontal scrollable tabs on mobile, sidebar on desktop.
 */
export function SideNav({ items, ariaLabel }: { items: NavItem[]; ariaLabel: string }) {
  const pathname = usePathname();

  const isActive = (href: string) =>
    pathname === href || (href !== '/dashboard' && href !== '/admin' && pathname.startsWith(`${href}/`));

  return (
    <nav aria-label={ariaLabel} className="lg:w-60 lg:shrink-0">
      <ul className="flex gap-1 overflow-x-auto pb-1 lg:sticky lg:top-20 lg:flex-col lg:overflow-visible lg:pb-0">
        {items.map((item) => {
          const active = isActive(item.href);
          return (
            <li key={item.href} className="shrink-0 lg:shrink">
              <Link
                href={item.href}
                aria-current={active ? 'page' : undefined}
                className={`flex items-center gap-2 whitespace-nowrap rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${
                  active
                    ? 'bg-brand-100 text-brand-800 dark:bg-brand-900/40 dark:text-brand-300'
                    : 'text-neutral-600 hover:bg-neutral-100 dark:text-slate-400 dark:hover:bg-neutral-800'
                }`}
              >
                <span aria-hidden="true" className="text-lg">
                  {item.icon}
                </span>
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
