'use client';

import { CreditCard, Star } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useActivatePlan, useMyPlan, usePlans, usePurchasePlan } from '@/features/plans/hooks';
import { useMe } from '@/features/auth/hooks';
import { formatToman } from '@/lib/currency';
import { LoadingSpinner } from './LoadingSpinner';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { useToast } from './Toast';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { Plan } from '@/types/api';

/**
 * Pricing plans section.
 * - Data comes ONLY from GET /api/v1/plans, ordered by sort_order.
 * - Free plan: «فعال‌سازی رایگان» -> POST /api/v1/plans/{id}/activate (no payment).
 * - Paid plans: «خرید» -> POST /api/v1/plans/{id}/purchase (wallet credit;
 *   top up the wallet first). 402 -> prompt to top up.
 * - Guests are sent to the login page first.
 */
export function PlansSection() {
  const plans = usePlans();

  return (
    <section id="plans" aria-labelledby="plans-heading" className="mx-auto w-full max-w-7xl px-4 py-16 sm:px-6 scroll-mt-24">
      <div className="mb-10 text-center">
        <p className="badge badge-warning mb-3">اشتراک‌ها</p>
        <h2 id="plans-heading" className="text-3xl font-black">
          اعتبار <span className="text-gradient">متناسب با نیاز شما</span>
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-7 text-neutral-600 dark:text-slate-400">
          خرید بسته اشتراک الزامی نیست؛ با اعتبار حساب خود، بدون محدودیت زمانی از خدمات هوش مصنوعی نورا استفاده کنید.
        </p>
      </div>

      <div className="mx-auto mb-10 max-w-3xl rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm leading-8 text-neutral-700 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-slate-300" role="note">
        اشتراک اجباری نیست! می‌تونی فقط کیف پولت رو شارژ کنی و بدون محدودیت زمانی از همه خدمات استفاده کنی. بسته‌های اشتراک برای پرمصرف‌هاست که می‌خوان ارزون‌تر تموم بشه. یادت باشه تو هر دوره فقط یه اشتراک فعال داری؛ با خرید بسته جدید، اشتراک قبلی — حتی اگه مهلت یا سهمیه داشته باشه — تموم می‌شه و برنمی‌گرده. برای خرید بسته، اول کیف پول رو شارژ کن.
      </div>

      {plans.isLoading && <LoadingSpinner label="در حال بارگذاری اشتراک‌ها…" />}
      {plans.isError && (
        <ErrorState message="بارگذاری اشتراک‌ها ناموفق بود." onRetry={() => plans.refetch()} />
      )}
      {plans.data && plans.data.length === 0 && (
        <EmptyState
          icon={CreditCard}
          title="اشتراکی ثبت نشده است"
          description="به‌زودی اشتراک‌ها در اینجا نمایش داده می‌شود."
        />
      )}

      {plans.data && plans.data.length > 0 && (
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          {plans.data.map((plan) => (
            <PlanCard key={plan.id} plan={plan} />
          ))}
        </div>
      )}
    </section>
  );
}

function PlanCard({ plan }: { plan: Plan }) {
  const router = useRouter();
  const { toast } = useToast();
  const { data: user } = useMe();
  const myPlan = useMyPlan(!!user);
  const activatePlan = useActivatePlan();
  const purchasePlan = usePurchasePlan();

  const isCurrent = myPlan.data?.id === plan.id;
  const busy = activatePlan.isPending || purchasePlan.isPending;

  const requireLogin = () => {
    if (!user) {
      router.push('/auth/login');
      return false;
    }
    return true;
  };

  const activateFree = () => {
    if (!requireLogin()) return;
    activatePlan.mutate(plan.id, {
      onSuccess: () => toast(`اشتراک «${plan.name}» برای شما فعال شد.`, 'success'),
      onError: (err) =>
        toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'فعال‌سازی ناموفق بود.', 'error'),
    });
  };

  const buy = () => {
    if (!requireLogin()) return;
    // Warn when replacing an active subscription: the old one is cancelled
    // even with remaining time/quota.
    const currentName = myPlan.data?.name;
    if (currentName && currentName !== plan.name) {
      const ok = window.confirm(
        `شما اشتراک فعال «${currentName}» دارید.\n` +
        `با خرید «${plan.name}»، اشتراک فعلی شما — حتی با وجود مهلت و سهمیه باقی‌مانده — لغو می‌شود و قابل بازگشت نیست.\n` +
        `ادامه می‌دهید؟`,
      );
      if (!ok) return;
    }
    purchasePlan.mutate(plan.id, {
      onSuccess: () => {
        toast(`اشتراک «${plan.name}» برای شما فعال شد.`, 'success');
      },
      onError: (err) => {
        if (err instanceof ApiError && err.code === 'INSUFFICIENT_BALANCE') {
          toast('موجودی کیف پول کافی نیست؛ ابتدا کیف پول را شارژ کنید.', 'error');
          router.push('/dashboard/wallet');
          return;
        }
        toast(
          err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'خرید اشتراک ناموفق بود.',
          'error',
        );
      },
    });
  };

  return (
    <article
      className={`service-card ${plan.is_featured ? 'border-2 !border-brand-500 dark:!border-brand-400 xl:-translate-y-2' : ''}`}
      aria-label={`اشتراک ${plan.name}`}
    >
      {plan.is_featured && (
        <span className="badge badge-warning absolute left-4 top-4 inline-flex items-center gap-1">پیشنهاد ما <Star aria-hidden="true" className="h-3.5 w-3.5" /></span>
      )}
      {isCurrent && (
        <span className="badge badge-success absolute left-4 top-4">اشتراک فعال شما ✓</span>
      )}

      <h3 className="text-xl font-extrabold text-neutral-900 dark:text-white">{plan.name}</h3>
      {plan.description && (
        <p className="text-sm text-neutral-500 dark:text-slate-400">{plan.description}</p>
      )}

      <p className="mt-1" aria-label={plan.is_free ? 'رایگان' : `قیمت: ${formatToman(plan.price_irr)}`}>
        {plan.is_free ? (
          <span className="text-3xl font-black text-emerald-600 dark:text-emerald-400">رایگان</span>
        ) : (
          <>
            <span className="text-3xl font-black tabular-nums text-neutral-900 dark:text-white">
              {formatToman(plan.price_irr).replace(' تومان', '')}
            </span>{' '}
            <span className="text-sm text-neutral-500 dark:text-slate-400">تومان</span>
          </>
        )}
        {!!plan.period_days && (
          <span className="block text-xs text-neutral-500 dark:text-slate-400">اعتبار {plan.period_days} روزه</span>
        )}
      </p>

      <ul className="flex flex-col gap-2 text-sm text-neutral-600 dark:text-slate-300">
        {plan.features.map((f, i) => (
          <li key={i} className="flex items-start gap-2">
            <span aria-hidden="true" className="text-emerald-500">✓</span>
            <span>{f}</span>
          </li>
        ))}
      </ul>

      {(plan.limits?.length ?? 0) > 0 && (
        <div className="rounded-xl bg-neutral-50 p-3 text-xs leading-6 text-neutral-500 dark:bg-white/5 dark:text-slate-400">
          <p className="mb-1 font-bold">محدودیت‌ها:</p>
          <ul className="list-disc pr-4">
            {plan.limits.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex-1" />

      {isCurrent ? (
        <p className="badge badge-success w-full justify-center py-2">اشتراک فعال شما</p>
      ) : plan.is_free ? (
        <button
          type="button"
          onClick={activateFree}
          disabled={busy}
          className="btn-secondary w-full"
        >
          {activatePlan.isPending ? 'در حال فعال‌سازی…' : 'فعال‌سازی رایگان'}
        </button>
      ) : (
        <button
          type="button"
          onClick={buy}
          disabled={busy}
          className={plan.is_featured ? 'btn-primary w-full' : 'btn-secondary w-full'}
        >
          {purchasePlan.isPending ? 'در حال خرید…' : 'خرید'}
        </button>
      )}

      <span
        aria-hidden="true"
        className="service-accent"
        style={{ ['--svc' as string]: plan.is_featured ? '#f59e0b' : '#64748b' }}
      />
    </article>
  );
}
