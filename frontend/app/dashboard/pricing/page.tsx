'use client';

import { FileText, Image as ImageIcon, MessageSquare, Mic, ScanEye, Volume2 } from 'lucide-react';
import { PillHeader } from '@/components/PillHeader';
import { FloatingNav } from '@/components/FloatingNav';

/**
 * Service tariffs in toman. These are the public display prices;
 * actual billing follows the admin pricing rules per model.
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
    unit: 'هر دقیقه',
    price: '۱٬۴۸۲ تومان',
    description: 'پیاده‌سازی صوت فارسی به متن',
    color: '#f472b6',
  },
  {
    icon: Volume2,
    title: 'تبدیل متن به صوت',
    unit: 'هر دقیقه صدا',
    price: '۳٬۷۰۵ تومان',
    description: 'تبدیل متن به گفتار فارسی',
    color: '#34d399',
  },
  {
    icon: ImageIcon,
    title: 'تولید تصویر',
    unit: 'هر تصویر',
    price: '۱۷٬۲۹۰ تومان',
    description: 'ساخت تصویر از توضیح متنی',
    color: '#a78bfa',
  },
  {
    icon: ScanEye,
    title: 'تحلیل تصویر',
    unit: 'هر تصویر',
    price: '۹٬۸۸۰ تومان',
    description: 'ویرایش و تحلیل تصویر',
    color: '#fbbf24',
  },
  {
    icon: FileText,
    title: 'تاریخچه و نگارخانه',
    unit: 'رایگان',
    price: '۰ تومان',
    description: 'مشاهده سوابق و تصاویر تأییدشده',
    color: '#94a3b8',
  },
];

export default function PricingPage() {
  return (
    <div className="min-h-screen">
      <PillHeader />
      <FloatingNav />

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-20 pt-28 sm:px-6 md:pe-24">
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
          قیمت‌ها ممکن است با تغییر تعرفه مدل‌ها به‌روزرسانی شوند. مبلغ نهایی هر درخواست در تاریخچه مصرف ثبت می‌شود.
        </p>
      </main>
    </div>
  );
}
