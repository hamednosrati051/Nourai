'use client';

import Link from 'next/link';
import { ArrowRight, Crown } from 'lucide-react';
import { useSubscriptionHistory } from '@/features/plans/hooks';
import { formatToman } from '@/lib/currency';
import { formatDateTime } from '@/lib/format';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { ErrorState } from '@/components/ErrorState';
import { PillHeader } from '@/components/PillHeader';
import { FloatingNav } from '@/components/FloatingNav';
import { ApiError, getErrorMessage } from '@/lib/api';

const STATUS_LABELS: Record<string, string> = {
  active: 'فعال',
  expired: 'منقضی‌شده',
  cancelled: 'لغوشده',
};

/**
 * User's subscription: current plan + full history from GET /api/v1/me/subscriptions.
 */
export default function SubscriptionPage() {
  const { data: items, isLoading, isError, error, refetch } = useSubscriptionHistory();

  return (
    <div className="min-h-screen">
      <PillHeader />
      <FloatingNav />

      <main className="mx-auto w-full max-w-3xl flex-1 px-4 pb-20 pt-28 sm:px-6 md:pe-24">
        <Link
          href="/dashboard"
          className="mb-6 inline-flex items-center gap-1.5 text-sm font-bold text-neutral-600 hover:text-neutral-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          <ArrowRight className="h-4 w-4" />
          بازگشت به داشبورد
        </Link>

        <div className="mb-8">
          <p className="badge badge-warning mb-3">اشتراک</p>
          <h1 className="text-3xl font-black">اشتراک من</h1>
          <p className="mt-2 text-sm text-neutral-600 dark:text-slate-400">
            اشتراک فعال و سابقه اشتراک‌های قبلی شما.
          </p>
        </div>

        {isLoading && <LoadingSpinner label="در حال بارگذاری اشتراک…" />}

        {isError && (
          <ErrorState
            message={error instanceof ApiError ? getErrorMessage(error.code, error.message) : 'بارگذاری اشتراک ناموفق بود.'}
            onRetry={() => refetch()}
          />
        )}

        {!isLoading && !isError && (!items || items.length === 0) && (
          <div className="card text-center">
            <Crown className="mx-auto mb-3 h-10 w-10 text-brand-500" />
            <p className="font-bold">هنوز اشتراکی ندارید</p>
            <p className="mt-1 text-sm text-neutral-600 dark:text-slate-400">
              برای استفاده از سهمیه‌ها، یکی از اشتراک‌ها را انتخاب کنید.
            </p>
            <Link href="/#plans" className="btn-primary btn-sm mt-4 inline-flex">
              مشاهده اشتراک‌ها
            </Link>
          </div>
        )}

        {!isLoading && !isError && items && items.length > 0 && (
          <ul className="space-y-4">
            {items.map((sub) => (
              <li key={sub.id} className="card">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-extrabold">{sub.plan?.name ?? 'اشتراک'}</p>
                    {sub.plan?.description && (
                      <p className="mt-1 text-sm text-neutral-600 dark:text-slate-400">
                        {sub.plan.description}
                      </p>
                    )}
                  </div>
                  <span
                    className={`badge ${sub.status === 'active' ? 'badge-success' : 'badge-neutral'}`}
                  >
                    {STATUS_LABELS[sub.status] ?? sub.status}
                  </span>
                </div>
                <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                  <div>
                    <dt className="text-xs text-neutral-500">شروع</dt>
                    <dd className="font-bold">{formatDateTime(sub.started_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-neutral-500">پایان</dt>
                    <dd className="font-bold">{formatDateTime(sub.expires_at)}</dd>
                  </div>
                  {sub.plan && (
                    <div>
                      <dt className="text-xs text-neutral-500">مبلغ</dt>
                      <dd className="font-bold">{formatToman(sub.plan.price_irr)}</dd>
                    </div>
                  )}
                  {sub.status === 'active' && (
                    <div>
                      <dt className="text-xs text-neutral-500">روز باقی‌مانده</dt>
                      <dd className="font-bold">{sub.days_remaining}</dd>
                    </div>
                  )}
                </dl>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-6 text-center">
          <Link href="/#plans" className="btn-secondary btn-sm">
            مشاهده و خرید اشتراک
          </Link>
        </div>
      </main>
    </div>
  );
}
