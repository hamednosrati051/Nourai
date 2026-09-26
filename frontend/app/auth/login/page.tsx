'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { BRAND } from '@/lib/config';
import { mobileSchema } from '@/lib/phone';
import { useOtpRequest } from '@/features/auth/hooks';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';
import { useToast } from '@/components/Toast';
import { ApiError, getErrorMessage } from '@/lib/api';

const loginSchema = z.object({ mobile: mobileSchema });
type LoginForm = z.infer<typeof loginSchema>;

/** Step 1 of user auth: mobile number -> OTP request. */
export default function LoginPage() {
  const router = useRouter();
  const { toast } = useToast();
  const otpRequest = useOtpRequest();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({ resolver: zodResolver(loginSchema) });

  const onSubmit = (values: LoginForm) => {
    setServerError(null);
    otpRequest.mutate(values.mobile, {
      onSuccess: () => {
        toast('کد تأیید به شماره شما پیامک شد.', 'success');
        router.push(`/auth/verify?mobile=${encodeURIComponent(values.mobile)}`);
      },
      onError: (err) => {
        if (err instanceof ApiError && err.code === 'RATE_LIMITED') {
          setServerError('درخواست‌های شما زیاد است؛ لطفاً چند دقیقه بعد تلاش کنید.');
        } else {
          setServerError(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'خطایی رخ داد.');
        }
      },
    });
  };

  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="card w-full max-w-md">
          <h1 className="text-2xl font-extrabold">ورود به {BRAND.fa}</h1>
          <p className="mt-2 text-sm text-neutral-600 dark:text-slate-400">
            شماره موبایل خود را وارد کنید تا کد تأیید برایتان پیامک شود.
          </p>

          <form onSubmit={handleSubmit(onSubmit)} className="mt-6 flex flex-col gap-4" noValidate>
            <div>
              <label htmlFor="mobile" className="label">
                شماره موبایل
              </label>
              <input
                id="mobile"
                type="tel"
                inputMode="tel"
                autoComplete="tel"
                dir="ltr"
                placeholder="09123456789"
                className={`input text-left ${errors.mobile ? 'input-error' : ''}`}
                aria-invalid={!!errors.mobile}
                aria-describedby={errors.mobile ? 'mobile-error' : 'mobile-hint'}
                {...register('mobile')}
              />
              {errors.mobile ? (
                <p id="mobile-error" role="alert" className="field-error">
                  {errors.mobile.message}
                </p>
              ) : (
                <p id="mobile-hint" className="field-hint">
                  مثال: 09123456789
                </p>
              )}
            </div>

            {serverError && (
              <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
                {serverError}
              </p>
            )}

            <button type="submit" disabled={isSubmitting || otpRequest.isPending} className="btn-primary w-full">
              {isSubmitting || otpRequest.isPending ? 'در حال ارسال…' : 'ارسال کد تأیید'}
            </button>
          </form>
        </div>
      </main>
      <Footer />
    </div>
  );
}
