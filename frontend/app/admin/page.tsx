'use client';

import { TrendingUp } from 'lucide-react';
import { Bot, Images, Receipt, UserCheck, Users, Wallet, Zap } from 'lucide-react';
import Link from 'next/link';
import { useAdminDashboard } from '@/features/admin/hooks';
import { formatToman } from '@/lib/currency';
import { formatNumber } from '@/lib/format';
import { StatCard } from '@/components/StatCard';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { ErrorState } from '@/components/ErrorState';
import { ApiError, getErrorMessage } from '@/lib/api';

/** Admin stats dashboard. */
export default function AdminDashboardPage() {
  const stats = useAdminDashboard();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">داشبورد ادمین</h1>

      {stats.isLoading && <LoadingSpinner label="در حال بارگذاری آمار…" />}
      {stats.isError && (
        <ErrorState
          message={stats.error instanceof ApiError ? getErrorMessage(stats.error.code, stats.error.message) : 'بارگذاری آمار ناموفق بود.'}
          onRetry={() => stats.refetch()}
        />
      )}

      {stats.data && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="کل کاربران" value={formatNumber(stats.data.total_users)} icon={Users} />
            <StatCard label="کاربران فعال" value={formatNumber(stats.data.active_users)} icon={UserCheck} accent="success" />
            <StatCard label="درآمد امروز" value={formatToman(stats.data.revenue_today_irr)} icon={Wallet} accent="success" />
            <StatCard label="درآمد کل" value={formatToman(stats.data.total_revenue_irr)} icon={TrendingUp} />
            <StatCard label="پرداخت‌های امروز" value={formatNumber(stats.data.payments_today)} icon={Receipt} accent="info" />
            <StatCard label="درخواست‌های امروز" value={formatNumber(stats.data.jobs_today)} icon={Zap} accent="info" />
            <StatCard label="مدل‌های فعال" value={formatNumber(stats.data.active_models)} icon={Bot} />
            <StatCard
              label="تصاویر در انتظار بررسی"
              value={formatNumber(stats.data.pending_gallery_items)}
              icon={Images}
              accent={stats.data.pending_gallery_items > 0 ? 'danger' : 'brand'}
            />
          </div>

          {stats.data.pending_gallery_items > 0 && (
            <Link href="/admin/gallery" className="card flex items-center justify-between gap-2 border-amber-300 hover:border-amber-500 dark:border-amber-800">
              <div>
                <p className="font-bold">صف بررسی گالری</p>
                <p className="text-sm text-neutral-500 dark:text-slate-400">
                  {formatNumber(stats.data.pending_gallery_items)} تصویر در انتظار تأیید است.
                </p>
              </div>
              <span aria-hidden="true" className="text-2xl">←</span>
            </Link>
          )}
        </>
      )}
    </div>
  );
}
