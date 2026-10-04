'use client';

import Link from 'next/link';
import { BRAND } from '@/lib/config';
import {
  ArrowLeftRight,
  Bot,
  CircleDollarSign,
  ClipboardList,
  CreditCard,
  Home,
  Hourglass,
  Image as ImageIcon,
  Receipt,
  Settings,
  ShieldCheck,
  Users,
} from 'lucide-react';
import { useAdminLogout, useAdminMe } from '@/features/auth/hooks';
import { usePathname } from 'next/navigation';
import { AdminGuard } from '@/components/ProtectedRoute';
import { SideNav, type NavItem } from '@/components/SideNav';
import { ThemeToggle } from '@/components/ThemeToggle';

const NAV_ITEMS: NavItem[] = [
  { href: '/admin', label: 'داشبورد', icon: Home },
  { href: '/admin/users', label: 'کاربران', icon: Users },
  { href: '/admin/payments', label: 'پرداخت‌ها', icon: Receipt },
  { href: '/admin/gallery', label: 'گالری', icon: ImageIcon },
  { href: '/admin/models', label: 'مدل‌ها', icon: Bot },
  { href: '/admin/plans', label: 'اشتراک‌ها', icon: CreditCard },
  { href: '/admin/pricing', label: 'تعرفه‌ها', icon: CircleDollarSign },
  { href: '/admin/currency', label: 'تنظیمات نرخ ارز', icon: ArrowLeftRight },
  { href: '/admin/image-settings', label: 'تنظیمات تصویر', icon: Settings },
  { href: '/admin/prompt-filter', label: 'فیلتر پرامت', icon: ShieldCheck },
  { href: '/admin/jobs', label: 'درخواست‌های جاری', icon: Hourglass },
  { href: '/admin/audit', label: 'گزارش حسابرسی', icon: ClipboardList },
];

/** Admin panel shell: admin guard + header + responsive navigation. */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  // The login page must render without the guard (it establishes the session).
  if (pathname === '/admin/login') {
    return <>{children}</>;
  }
  return (
    <AdminGuard>
      <AdminShell>{children}</AdminShell>
    </AdminGuard>
  );
}

function AdminShell({ children }: { children: React.ReactNode }) {
  const { data: admin } = useAdminMe();
  const logout = useAdminLogout();

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-neutral-200 bg-white/90 backdrop-blur dark:border-white/10 dark:bg-navy-950/90">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
          <Link href="/admin" className="flex items-center gap-2" aria-label="پنل ادمین">
            <span
              aria-hidden="true"
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 text-xl font-black text-white dark:text-navy-950"
            >
              ن
            </span>
            <span className="text-xl font-extrabold">{BRAND.fa}</span>
            <span className="badge badge-warning">ادمین</span>
          </Link>
          <div className="flex items-center gap-2">
            <span className="hidden text-sm text-neutral-500 sm:inline dark:text-slate-400" dir="ltr">
              {admin?.username ?? ''}
            </span>
            <ThemeToggle compact />
            <button
              type="button"
              onClick={() => logout.mutate()}
              disabled={logout.isPending}
              className="btn-ghost btn-sm"
            >
              {logout.isPending ? '…' : 'خروج'}
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 px-4 py-6 sm:px-6 lg:flex-row">
        <SideNav items={NAV_ITEMS} ariaLabel="ناوبری پنل ادمین" />
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
