'use client';

import Link from 'next/link';
import { CircleCheck, CircleDollarSign, Crown, FileText, Image as ImageIcon, MessageSquare, Mic, Phone, ShoppingCart, Volume2 } from 'lucide-react';
import { useWallet } from '@/features/wallet/hooks';
import { useMySubscription } from '@/features/plans/hooks';
import { useMe } from '@/features/auth/hooks';
import { useModels } from '@/features/models/hooks';
import type { ModelCapability } from '@/types/api';
import { IMAGE_CAPABILITIES } from '@/types/api';
import { formatToman } from '@/lib/currency';
import { formatDateTime } from '@/lib/format';
import { BRAND } from '@/lib/config';
import { ServiceCard } from '@/components/ServiceCard';
import { FloatingNav } from '@/components/FloatingNav';
import { PillHeader } from '@/components/PillHeader';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { ErrorState } from '@/components/ErrorState';
import { ApiError, getErrorMessage } from '@/lib/api';

/**
 * User dashboard (Binavira-inspired): floating pill header + vertical
 * right-side nav, color-coded service cards, wallet overview with top-up /
 * history shortcuts, and the «اشتراک فعال شما» banner from GET /api/v1/me/plan.
 */

const REMAINING_LABELS: Record<string, string> = {
  text: 'پیام متنی',
  image: 'تصویر',
  audio: 'دقیقه صوت',
};

function formatRemaining(remaining: Record<string, number>): string {
  const fmt = (n: number) =>
    (Number.isInteger(n) ? n : Math.round(n * 10) / 10).toLocaleString('fa-IR');
  return Object.entries(remaining)
    .map(([kind, n]) => `${fmt(n)} ${REMAINING_LABELS[kind] ?? kind}`)
    .join('، ');
}

export default function DashboardPage() {
  const { data: user } = useMe();
  const wallet = useWallet();
  const myPlan = useMySubscription(!!user);
  const models = useModels();

  // Capabilities that have at least one active model. While loading (or on
  // error) keep every card visible so a slow/failed request never breaks
  // navigation; only a confirmed-empty capability hides its card.
  const readyCaps = new Set(
    (models.data ?? []).map((m) => m.capability),
  );
  const settled = models.isSuccess;
  const hasCap = (cap: ModelCapability) => !settled || readyCaps.has(cap);
  // The image tile covers both generation and editing (plus legacy "image").
  const hasImageCap = !settled || IMAGE_CAPABILITIES.some((c) => readyCaps.has(c));

  return (
    <div className="min-h-screen">
      <PillHeader />
      <FloatingNav />

      <main className="mx-auto w-full max-w-6xl px-4 pb-20 pt-28 sm:px-6 md:pe-24">
        <div className="mb-8">
          <p className="badge badge-warning mb-3">داشبورد</p>
          <h1 className="text-3xl font-black">
            خوش برگشتی به <span className="text-gradient">{BRAND.fa}</span>
          </h1>
        </div>

        {/* Noura hero: animated avatar linking to the voice assistant */}
        {hasCap('speech_to_text') && (
          <Link
            href="/dashboard/voice"
            aria-label="نورا — دستیار صوتی"
            className="group mb-8 flex flex-col items-center gap-2 p-2 text-center"
          >
            <video
              src="/images/nourai-mascot.mp4"
              poster="/images/nourai-mascot.jpg"
              autoPlay
              loop
              muted
              playsInline
              className="h-24 w-24 rounded-full object-cover shadow-xl transition group-hover:scale-105"
            />
            <p className="text-2xl font-black">نورا</p>
            <p className="-mt-1 text-sm text-neutral-500 dark:text-slate-400">
              دستیار صوتی‌ات — بزن و حرف بزن
            </p>
          </Link>
        )}

        {/* Active plan banner */}
        {myPlan.data?.plan && (
          <div
            role="status"
            className="mb-6 flex items-center gap-3 rounded-2xl border border-emerald-500/40 bg-emerald-500/10 p-4 dark:bg-emerald-500/10"
          >
            <CircleCheck aria-hidden="true" className="h-8 w-8 shrink-0 text-emerald-500" />
            <div>
              <p className="font-extrabold text-emerald-700 dark:text-emerald-300">
                اشتراک فعال شما: {myPlan.data.plan.name}
                <span className="mr-2 text-xs font-normal text-neutral-500 dark:text-slate-400">
                  {myPlan.data.days_remaining.toLocaleString('fa-IR')} روز مانده
                </span>
              </p>
              {Object.keys(myPlan.data.remaining).length > 0 && (
                <p className="text-xs text-neutral-600 dark:text-slate-400">
                  باقی‌مانده: {formatRemaining(myPlan.data.remaining)}
                </p>
              )}
            </div>
            <Link href="/#plans" className="btn-secondary mr-auto !px-4 !py-2 text-xs">
              تغییر اشتراک
            </Link>
          </div>
        )}

        {/* Wallet overview */}
        {wallet.isLoading && <LoadingSpinner label="در حال بارگذاری موجودی…" />}
        {wallet.isError && (
          <ErrorState
            message={
              wallet.error instanceof ApiError
                ? getErrorMessage(wallet.error.code, wallet.error.message)
                : 'بارگذاری موجودی ناموفق بود.'
            }
            onRetry={() => wallet.refetch()}
          />
        )}
        {wallet.data && (
          <section aria-labelledby="wallet-heading" className="mb-8">
            <h2 id="wallet-heading" className="mb-3 text-lg font-bold">کیف پول</h2>
            <div className="service-card !border-brand-500/30">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <p className="text-sm text-neutral-500 dark:text-slate-400">موجودی فعلی</p>
                  <p className="text-3xl font-black tabular-nums">
                    {formatToman(wallet.data.balance_irr).replace(' تومان', '')}{' '}
                    <span className="text-sm font-normal text-neutral-500 dark:text-slate-400">تومان</span>
                  </p>
                  {wallet.data.updated_at && (
                    <p className="mt-1 text-xs text-neutral-400 dark:text-slate-500">
                      آخرین به‌روزرسانی: {formatDateTime(wallet.data.updated_at)}
                    </p>
                  )}
                </div>
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Link href="/dashboard/wallet" className="btn-primary">
                    شارژ کیف پول
                  </Link>
                  <Link href="/dashboard/usage" className="btn-secondary">
                    سابقه مصرف
                  </Link>
                </div>
              </div>
              <span aria-hidden="true" className="service-accent" style={{ ['--svc' as string]: '#f59e0b' }} />
            </div>
          </section>
        )}

        {/* Service cards */}
        <section aria-labelledby="services-heading">
          <h2 id="services-heading" className="mb-3 text-lg font-bold">سرویس‌ها</h2>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {hasCap('text') && (
              <ServiceCard
                href="/dashboard/chat"
                icon={MessageSquare}
                title="گفت‌وگوی متنی"
                description="مکالمه با مدل‌های زبانی با استریم زنده پاسخ‌ها"
                color="#38bdf8"
              />
            )}
            {hasImageCap && (
              <ServiceCard
                href="/dashboard/image"
                icon={ImageIcon}
                title="تولید تصویر"
                description="ساخت و ویرایش تصویر با مدل‌های پیشرفته"
                color="#a78bfa"
              />
            )}
            {hasCap('speech_to_text') && (
              <ServiceCard
                href="/dashboard/voice"
                icon={Mic}
                title="نورا"
                description="دستیار صوتی نورا؛ حرف بزن، جواب متنی و صوتی بگیر"
                color="#f472b6"
              />
            )}
            {hasCap('speech_to_text') && (
              <ServiceCard
                href="/dashboard/stt"
                icon={FileText}
                title="تبدیل صوت به متن"
                description="ارسال صوت و دریافت متن پیاده‌شده"
                color="#38bdf8"
              />
            )}
            {hasCap('text_to_speech') && (
              <ServiceCard
                href="/dashboard/tts"
                icon={Volume2}
                title="تبدیل متن به صوت"
                description="تبدیل متن به گفتار و دانلود فایل صوتی"
                color="#34d399"
              />
            )}
            <ServiceCard
              href="/dashboard/subscription"
              icon={Crown}
              title="اشتراک من"
              description="اشتراک فعال و سابقه اشتراک‌های قبلی"
              color="#fbbf24"
              ctaLabel="مشاهده"
            />
            <ServiceCard
              href="/#plans"
              icon={ShoppingCart}
              title="خرید اشتراک"
              description="انتخاب و خرید اشتراک جدید"
              color="#f472b6"
              ctaLabel="خرید"
            />
            <ServiceCard
              href="/dashboard/pricing"
              icon={CircleDollarSign}
              title="تعرفه خدمات"
              description="هزینه هر سرویس به تومان"
              color="#34d399"
              ctaLabel="مشاهده"
            />
            <ServiceCard
              href="/contact"
              icon={Phone}
              title="تماس با ما"
              description="راه‌های ارتباطی با تیم نورا"
              color="#38bdf8"
              ctaLabel="مشاهده"
            />
          </div>
        </section>
      </main>
    </div>
  );
}
