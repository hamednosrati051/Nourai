'use client';

import { useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import Link from 'next/link';

function VerifyContent() {
  const params = useSearchParams();
  const status = params.get('status');
  const success = status === 'success';

  return (
    <div className="min-h-screen flex items-center justify-center bg-neutral-100 dark:bg-slate-900 p-4">
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-lg p-8 max-w-md w-full text-center">
        <div className="text-6xl mb-4">{success ? '✅' : '❌'}</div>
        <h1 className="text-2xl font-bold mb-3 text-neutral-900 dark:text-white">
          {success ? 'پرداخت موفق' : 'پرداخت ناموفق'}
        </h1>
        <p className="text-neutral-600 dark:text-slate-400 mb-6">
          {success
            ? 'حساب کاربری شما شارژ شد. می‌توانید به بات برگردید و از خدمات استفاده کنید.'
            : 'پرداخت انجام نشد. لطفاً دوباره تلاش کنید.'}
        </p>
        <div className="flex flex-col gap-3">
          <a
            href="https://ble.ir/nourai_bot"
            className="bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-6 rounded-xl transition"
          >
            🤖 بازگشت به بات نورا
          </a>
          <Link
            href="/"
            className="text-neutral-500 hover:text-neutral-700 dark:text-slate-400 py-2 transition"
          >
            بازگشت به سایت
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function PaymentVerifyPage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">در حال بارگذاری...</div>}>
      <VerifyContent />
    </Suspense>
  );
}
