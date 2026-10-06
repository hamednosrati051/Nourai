'use client';

import Link from 'next/link';
import { ArrowRight, Mail, MapPin, MessageCircle, Phone, Send } from 'lucide-react';
import { BRAND } from '@/lib/config';
import { useContactInfo } from '@/features/site/hooks';
import { PillHeader } from '@/components/PillHeader';
import { FloatingNav } from '@/components/FloatingNav';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { ErrorState } from '@/components/ErrorState';

/**
 * Public contact page: admin-managed contact info from GET /api/v1/site/contact.
 */
export default function ContactPage() {
  const { data, isLoading, isError, refetch } = useContactInfo();

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
          <p className="badge badge-warning mb-3">تماس با ما</p>
          <h1 className="text-3xl font-black">
            در ارتباط با <span className="text-gradient">{BRAND.fa}</span>
          </h1>
          <p className="mt-2 text-sm text-neutral-600 dark:text-slate-400">
            سوال، پیشنهاد یا مشکلی دارید؟ از راه‌های زیر با ما در میان بگذارید.
          </p>
        </div>

        {isLoading && <LoadingSpinner label="در حال بارگذاری اطلاعات تماس…" />}

        {isError && (
          <ErrorState
            message="بارگذاری اطلاعات تماس ناموفق بود."
            onRetry={() => refetch()}
          />
        )}

        {!isLoading && !isError && data && (
          <div className="card space-y-5">
            {data.contact_description && (
              <p className="leading-8 text-neutral-700 dark:text-slate-300">
                {data.contact_description}
              </p>
            )}
            <ul className="space-y-4">
              {data.contact_phone && (
                <li className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-500/10 text-brand-500">
                    <Phone className="h-5 w-5" />
                  </span>
                  <div>
                    <p className="text-xs text-neutral-500">تلفن</p>
                    <a href={`tel:${data.contact_phone}`} className="font-bold" dir="ltr">
                      {data.contact_phone}
                    </a>
                  </div>
                </li>
              )}
              {data.contact_email && (
                <li className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/10 text-violet-500">
                    <Mail className="h-5 w-5" />
                  </span>
                  <div>
                    <p className="text-xs text-neutral-500">ایمیل</p>
                    <a href={`mailto:${data.contact_email}`} className="font-bold" dir="ltr">
                      {data.contact_email}
                    </a>
                  </div>
                </li>
              )}
              {data.contact_address && (
                <li className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-500">
                    <MapPin className="h-5 w-5" />
                  </span>
                  <div>
                    <p className="text-xs text-neutral-500">نشانی</p>
                    <p className="font-bold">{data.contact_address}</p>
                  </div>
                </li>
              )}
              {data.contact_telegram && (
                <li className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-500/10 text-sky-500">
                    <Send className="h-5 w-5" />
                  </span>
                  <div>
                    <p className="text-xs text-neutral-500">تلگرام</p>
                    <a
                      href={`https://t.me/${data.contact_telegram.replace(/^@/, '')}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-bold"
                      dir="ltr"
                    >
                      {data.contact_telegram}
                    </a>
                  </div>
                </li>
              )}
              {data.contact_instagram && (
                <li className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-pink-500/10 text-pink-500">
                    <MessageCircle className="h-5 w-5" />
                  </span>
                  <div>
                    <p className="text-xs text-neutral-500">اینستاگرام</p>
                    <a
                      href={`https://instagram.com/${data.contact_instagram.replace(/^@/, '')}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-bold"
                      dir="ltr"
                    >
                      {data.contact_instagram}
                    </a>
                  </div>
                </li>
              )}
              {data.contact_eitaa && (
                <li className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-orange-500/10 text-orange-500">
                    <Send className="h-5 w-5" />
                  </span>
                  <div>
                    <p className="text-xs text-neutral-500">ایتا</p>
                    <a
                      href={data.contact_eitaa.startsWith('http') ? data.contact_eitaa : `https://eitaa.com/${data.contact_eitaa.replace(/^@/, '')}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-bold"
                      dir="ltr"
                    >
                      {data.contact_eitaa}
                    </a>
                  </div>
                </li>
              )}
              {data.contact_bale && (
                <li className="flex items-center gap-3">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-teal-500/10 text-teal-500">
                    <Send className="h-5 w-5" />
                  </span>
                  <div>
                    <p className="text-xs text-neutral-500">بله</p>
                    <a
                      href={data.contact_bale.startsWith('http') ? data.contact_bale : `https://ble.ir/${data.contact_bale.replace(/^@/, '')}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-bold"
                      dir="ltr"
                    >
                      {data.contact_bale}
                    </a>
                  </div>
                </li>
              )}
            </ul>
            {!data.contact_phone && !data.contact_email && !data.contact_address &&
              !data.contact_telegram && !data.contact_instagram && !data.contact_eitaa &&
              !data.contact_bale && !data.contact_description && (
                <p className="text-sm text-neutral-500">
                  اطلاعات تماس به‌زودی ثبت می‌شود.
                </p>
              )}
          </div>
        )}
      </main>
    </div>
  );
}
