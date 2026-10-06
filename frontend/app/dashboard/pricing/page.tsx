'use client';

import Link from 'next/link';
import { ArrowRight, Image as ImageIcon, MessageSquare, Mic, ScanEye, Volume2 } from 'lucide-react';
import { PillHeader } from '@/components/PillHeader';
import { FloatingNav } from '@/components/FloatingNav';

/**
 * Service tariffs in toman, derived from the admin pricing rules
 * (USD tariffs × 2,660,000 IRR/USD rate).
 *
 * - Text: avalai-text $0.0000003/in + $0.0000008/out per token;
 *   ~1500 tokens per 1000 Persian words → ≈ ۴۴۰ تومان
 * - STT: shenava-stt $0.001 per request → ۲۶۶ تومان
 * - TTS: piper-tts $0.0037594 per request → ۱٬۰۰۰ تومان
 * - Generate: qwen-image $0.035 per image → ۹٬۳۱۰ تومان
 * - Edit: qwen-image-edit $0.045 per image → ۱۱٬۹۷۰ تومان
 */
const TARIFFS = [
  {
    icon: MessageSquare,
    title: 'گفت‌وگوی متنی',
    unit: 'هر ۱٬۰۰۰ کلمه',
    price: '≈ ۴۴۰ تومان',
    description: 'مکالمه با مدل‌های زبانی (ورودی + خروجی)',
    color: '#38bdf8',
  },
  {
    icon: Mic,
    title: 'تبدیل صوت به متن',
    unit: 'هر درخواست',
    price: '۲۶۶ تومان',
    description: 'پیاده‌سازی صوت فارسی به متن (شنوا)',
    color: '#f472b6',
  },
  {
    icon: Volume2,
    title: 'تبدیل متن به صوت',
    unit: 'هر درخواست',
    price: '۱٬۰۰۰ تومان',
    description: 'تبدیل متن به گفتار فارسی',
    color: '#34d399',
  },
  {
    icon: ImageIcon,
    title: 'تولید تصویر',
    unit: 'هر تصویر',
    price: '۹٬۳۱۰ تومان',
    description: 'ساخت تصویر از توضیح متنی',
    color: '#a78bfa',
  },
  {
    icon: ScanEye,
    title: 'ویرایش تصویر',
    unit: 'هر تصویر',
    price: '۱۱٬۹۷۰ تومان',
    description: 'ویرایش و تغییر تصویر',
    color: '#fbbf24',
  },
];

export default function PricingPage() {
  return (
    <div className="min-h-screen">
      <PillHeader />
      <FloatingNav />

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-20 pt-28 sm:px-6 md:pe-24">
        <Link
          href="/dashboard"
          className="mb-6 inline-flex items-center gap-1.5 text-sm font-bold text-neutral-600 hover:text-neutral-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          <ArrowRight className="h-4 w-4" />
          بازگشت به داشبورد
        </Link>

        <div className="mb-8">
          <p className="badge badge-warning mb-3">تعرفه‌ها</p>
          <h1 className="text-3xl font-black">تعرفه خدمات</h1>
          <p className="mt-2 text-sm text-neutral-600 dark:text-slate-400">
            هزینه هر سرویس به تومان. مبلغ دقیق هر درخواست از کیف پول شما کسر می‌شود.
          </p>
        </div>

        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {TARIFFS.map((t) => {
            const Icon = t.icon;
            return (
              <div key={t.title} className="card group" style={{ ['--svc' as string]: t.color }}>
                <span aria-hidden="true" className="service-icon">
                  <Icon className="h-7 w-7" style={{ color: t.color }} />
                </span>
                <h3 className="text-lg font-extrabold text-neutral-900 dark:text-white">
                  {t.title}
                </h3>
                <p className="flex-1 text-sm leading-7 text-neutral-600 dark:text-slate-400">
                  {t.description}
                </p>
                <div className="mt-2 flex items-baseline justify-between">
                  <span className="text-xs text-neutral-500">{t.unit}</span>
                  <span className="text-lg font-black" style={{ color: t.color }}>
                    {t.price}
                  </span>
                </div>
                <span aria-hidden="true" className="service-accent" />
              </div>
            );
          })}
        </div>

        <p className="mt-6 text-center text-xs text-neutral-500">
          قیمت‌ها بر اساس تعرفه‌های فعلی محاسبه شده‌اند و ممکن است تغییر کنند. مبلغ نهایی هر درخواست در تاریخچه مصرف ثبت می‌شود.
        </p>
      </main>
    </div>
  );
}
