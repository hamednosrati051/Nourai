'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useCreatePayment, usePayments, useWallet, useWalletTransactions } from '@/features/wallet/hooks';
import { formatToman, tomanToIrr } from '@/lib/currency';
import { formatDateTime, formatNumber } from '@/lib/format';
import { StatCard } from '@/components/StatCard';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { Pagination } from '@/components/Pagination';
import { ResponsiveTable } from '@/components/DataTable';
import { useToast } from '@/components/Toast';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { PaymentStatus, WalletTransactionType } from '@/types/api';

const MIN_TOPUP_TOMAN = 10_000;

const topupSchema = z.object({
  amountToman: z
    .number({ invalid_type_error: 'مبلغ را وارد کنید.' })
    .min(MIN_TOPUP_TOMAN, `حداقل مبلغ شارژ ${formatNumber(MIN_TOPUP_TOMAN)} تومان است.`),
});
type TopupForm = z.infer<typeof topupSchema>;

const PRESET_AMOUNTS = [50_000, 100_000, 200_000, 500_000];

const TX_TYPE_LABELS: Record<WalletTransactionType, string> = {
  deposit: 'شارژ',
  reserve: 'رزرو',
  settle: 'تسویه',
  release: 'آزادسازی رزرو',
  refund: 'بازگشت وجه',
  adjustment: 'اصلاحیه',
};

const PAYMENT_STATUS: Record<PaymentStatus, { label: string; badge: string }> = {
  pending: { label: 'در انتظار پرداخت', badge: 'badge-warning' },
  paid: { label: 'پرداخت‌شده', badge: 'badge-success' },
  failed: { label: 'ناموفق', badge: 'badge-danger' },
  cancelled: { label: 'لغوشده', badge: 'badge-neutral' },
  expired: { label: 'منقضی‌شده', badge: 'badge-neutral' },
};

/** Wallet: balance, top-up via Zibal, transaction ledger, payment history. */
export default function WalletPage() {
  const { toast } = useToast();
  const [txPage, setTxPage] = useState(1);
  const [payPage, setPayPage] = useState(1);

  const wallet = useWallet();
  const transactions = useWalletTransactions(txPage);
  const payments = usePayments(payPage);
  const createPayment = useCreatePayment();

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<TopupForm>({ resolver: zodResolver(topupSchema) });
  const amountToman = watch('amountToman');

  const onTopup = (values: TopupForm) => {
    createPayment.mutate(
      { amountToman: values.amountToman },
      {
        onSuccess: (payment) => {
          if (payment.redirect_url) {
            // Hand the user to the Zibal gateway; backend verifies server-side on callback.
            window.location.href = payment.redirect_url;
          } else {
            toast('درخواست پرداخت ثبت شد.', 'success');
          }
        },
        onError: (err) =>
          toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'ثبت پرداخت ناموفق بود.', 'error'),
      },
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">کیف پول</h1>

      {wallet.isLoading && <LoadingSpinner label="در حال بارگذاری موجودی…" />}
      {wallet.isError && (
        <ErrorState
          message={wallet.error instanceof ApiError ? getErrorMessage(wallet.error.code, wallet.error.message) : 'بارگذاری موجودی ناموفق بود.'}
          onRetry={() => wallet.refetch()}
        />
      )}
      {wallet.data && (
        <StatCard label="موجودی فعلی" value={formatToman(wallet.data.balance_irr)} icon="💰" accent="brand" />
      )}

      {/* Top-up */}
      <section aria-labelledby="topup-heading" className="card">
        <h2 id="topup-heading" className="text-lg font-bold">
          شارژ کیف پول
        </h2>
        <form onSubmit={handleSubmit(onTopup)} className="mt-4 flex flex-col gap-4" noValidate>
          <div>
            <span className="label">مبلغ سریع (تومان)</span>
            <div className="flex flex-wrap gap-2" role="group" aria-label="مبالغ پیشنهادی">
              {PRESET_AMOUNTS.map((amount) => (
                <button
                  key={amount}
                  type="button"
                  onClick={() => setValue('amountToman', amount, { shouldValidate: true })}
                  className={`btn-secondary btn-sm ${amountToman === amount ? '!border-brand-600 !text-brand-700 dark:!border-brand-400 dark:!text-brand-300' : ''}`}
                >
                  {formatNumber(amount)}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label htmlFor="topup-amount" className="label">
              مبلغ دلخواه (تومان)
            </label>
            <input
              id="topup-amount"
              type="number"
              inputMode="numeric"
              min={MIN_TOPUP_TOMAN}
              step={1000}
              placeholder={String(MIN_TOPUP_TOMAN)}
              className={`input ${errors.amountToman ? 'input-error' : ''}`}
              {...register('amountToman', { valueAsNumber: true })}
            />
            {errors.amountToman ? (
              <p role="alert" className="field-error">
                {errors.amountToman.message}
              </p>
            ) : (
              amountToman != null && !Number.isNaN(amountToman) && (
                <p className="field-hint">معادل {formatToman(tomanToIrr(amountToman))} شارژ می‌شود.</p>
              )
            )}
          </div>
          <button type="submit" disabled={isSubmitting || createPayment.isPending} className="btn-primary w-full sm:w-auto">
            {isSubmitting || createPayment.isPending ? 'در حال ثبت…' : 'پرداخت و شارژ'}
          </button>
          <p className="text-xs text-neutral-500 dark:text-slate-400">
            پرداخت از طریق درگاه امن زیبال انجام می‌شود. پس از پرداخت به همین صفحه برمی‌گردید.
          </p>
        </form>
      </section>

      {/* Payments */}
      <section aria-labelledby="payments-heading">
        <h2 id="payments-heading" className="mb-3 text-lg font-bold">
          سابقه پرداخت‌ها
        </h2>
        {payments.isLoading && <LoadingSpinner />}
        {payments.isError && <ErrorState message="بارگذاری پرداخت‌ها ناموفق بود." onRetry={() => payments.refetch()} />}
        {payments.data && payments.data.items.length === 0 && (
          <EmptyState icon="🧾" title="پرداختی ثبت نشده" description="هنوز کیف پول خود را شارژ نکرده‌اید." />
        )}
        {payments.data && payments.data.items.length > 0 && (
          <>
            <ResponsiveTable
              ariaLabel="سابقه پرداخت‌ها"
              keyOf={(p) => p.id}
              rows={payments.data.items}
              cardHeader={(p) => formatToman(p.amount_irr)}
              columns={[
                { header: 'مبلغ', render: (p) => <span className="tabular-nums">{formatToman(p.amount_irr)}</span> },
                {
                  header: 'وضعیت',
                  render: (p) => <span className={PAYMENT_STATUS[p.status].badge}>{PAYMENT_STATUS[p.status].label}</span>,
                },
                { header: 'تاریخ', render: (p) => formatDateTime(p.created_at), hideOnCard: true },
                {
                  header: 'اقدام',
                  render: (p) =>
                    p.status === 'pending' && p.redirect_url ? (
                      <a href={p.redirect_url} className="btn-secondary btn-sm">
                        ادامه پرداخت
                      </a>
                    ) : (
                      <span className="text-neutral-400">—</span>
                    ),
                  hideOnCard: true,
                },
              ]}
            />
            <Pagination page={payPage} totalPages={payments.data.meta.total_pages} totalItems={payments.data.meta.total_items} onPageChange={setPayPage} />
          </>
        )}
      </section>

      {/* Ledger */}
      <section aria-labelledby="ledger-heading">
        <h2 id="ledger-heading" className="mb-3 text-lg font-bold">
          تراکنش‌های کیف پول
        </h2>
        {transactions.isLoading && <LoadingSpinner />}
        {transactions.isError && <ErrorState message="بارگذاری تراکنش‌ها ناموفق بود." onRetry={() => transactions.refetch()} />}
        {transactions.data && transactions.data.items.length === 0 && (
          <EmptyState icon="📒" title="تراکنشی نیست" description="هنوز تراکنشی در کیف پول شما ثبت نشده است." />
        )}
        {transactions.data && transactions.data.items.length > 0 && (
          <>
            <ResponsiveTable
              ariaLabel="تراکنش‌های کیف پول"
              keyOf={(t) => t.id}
              rows={transactions.data.items}
              cardHeader={(t) => (
                <span className={`tabular-nums ${t.amount_irr >= 0 ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'}`}>
                  {t.amount_irr >= 0 ? '+' : ''}
                  {formatToman(t.amount_irr)}
                </span>
              )}
              columns={[
                { header: 'نوع', render: (t) => TX_TYPE_LABELS[t.type] ?? t.type },
                {
                  header: 'مبلغ',
                  render: (t) => (
                    <span className={`tabular-nums ${t.amount_irr >= 0 ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-700 dark:text-red-400'}`}>
                      {t.amount_irr >= 0 ? '+' : ''}
                      {formatToman(t.amount_irr)}
                    </span>
                  ),
                },
                {
                  header: 'موجودی بعد',
                  render: (t) => <span className="tabular-nums">{formatToman(t.balance_after_irr)}</span>,
                  hideOnCard: true,
                },
                { header: 'شرح', render: (t) => t.description ?? '—', hideOnCard: true },
                { header: 'تاریخ', render: (t) => formatDateTime(t.created_at) },
              ]}
            />
            <Pagination page={txPage} totalPages={transactions.data.meta.total_pages} totalItems={transactions.data.meta.total_items} onPageChange={setTxPage} />
          </>
        )}
      </section>
    </div>
  );
}
