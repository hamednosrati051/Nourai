'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BRAND } from '@/lib/config';
import { useLogout, useMe } from '@/features/auth/hooks';
import { UserGuard } from '@/components/ProtectedRoute';
import { SideNav, type NavItem } from '@/components/SideNav';
import { ThemeToggle } from '@/components/ThemeToggle';
import { useModels } from '@/features/models/hooks';
import type { ModelCapability } from '@/types/api';
import { IMAGE_CAPABILITIES } from '@/types/api';

type NavEntry = NavItem & { capability?: ModelCapability; capabilities?: ModelCapability[] };

const NAV_ITEMS: NavEntry[] = [
  { href: '/dashboard', label: 'داشبورد', icon: '🏠' },
  { href: '/dashboard/chat', label: 'گفت‌وگوی متنی', icon: '💬', capability: 'text' },
  { href: '/dashboard/voice', label: 'تعامل صوتی', icon: '🎙️', capability: 'speech_to_text' },
  { href: '/dashboard/tts', label: 'تبدیل متن به صوت', icon: '🔊', capability: 'text_to_speech' },
  { href: '/dashboard/image', label: 'تولید تصویر', icon: '🎨', capabilities: IMAGE_CAPABILITIES },
  { href: '/dashboard/history', label: 'تاریخچه', icon: '🕘' },
  { href: '/dashboard/wallet', label: 'کیف پول', icon: '💰' },
  { href: '/dashboard/usage', label: 'مصرف', icon: '📊' },
];

/** User panel shell: auth guard + header + responsive navigation. */
export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <UserGuard>
      <DashboardShell>{children}</DashboardShell>
    </UserGuard>
  );
}

function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  // The dashboard home page renders its own pill header + floating nav
  // (Binavira style); subpages keep the classic panel shell.
  if (pathname === '/dashboard') {
    return <>{children}</>;
  }

  return <PanelShell>{children}</PanelShell>;
}

function PanelShell({ children }: { children: React.ReactNode }) {
  const { data: user } = useMe();
  const logout = useLogout();
  // Hide nav entries whose capability has no active model. While loading
  // (or on error) keep everything visible; only a confirmed-empty
  // capability hides its entry.
  const models = useModels();
  const readyCaps = new Set((models.data ?? []).map((m) => m.capability));
  const settled = models.isSuccess;
  const items = NAV_ITEMS.filter((item) => {
    const caps = item.capabilities ?? (item.capability ? [item.capability] : []);
    return caps.length === 0 || !settled || caps.some((c) => readyCaps.has(c));
  });

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-neutral-200 bg-white/90 backdrop-blur dark:border-white/10 dark:bg-navy-950/90">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
          <Link href="/" className="flex items-center gap-2" aria-label={`${BRAND.fa} — صفحه اصلی`}>
            <span
              aria-hidden="true"
              className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 text-xl font-black text-white dark:text-navy-950"
            >
              ن
            </span>
            <span className="text-xl font-extrabold">{BRAND.fa}</span>
          </Link>
          <div className="flex items-center gap-2">
            <span className="hidden text-sm text-neutral-500 sm:inline dark:text-slate-400">
              {user?.mobile ?? ''}
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
        <SideNav items={items} ariaLabel="ناوبری پنل کاربر" />
        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
