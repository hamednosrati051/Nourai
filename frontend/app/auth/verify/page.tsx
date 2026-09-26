'use client';

import { Suspense, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { BRAND, OTP_LENGTH, OTP_RESEND_SECONDS } from '@/lib/config';
import { normalizeMobile, MOBILE_REGEX } from '@/lib/phone';
import { useOtpRequest, useOtpVerify } from '@/features/auth/hooks';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';
import { useToast } from '@/components/Toast';
import { ApiError, getErrorMessage } from '@/lib/api';

const verifySchema = z.object({
  code: z
    .string()
    .min(1, 'کد تأیید را وارد کنید.')
    .transform((v) => v.replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d))).replace(/\D/g, ''))
    .refine((v) => v.length === OTP_LENGTH, { message: `کد تأیید باید ${OTP_LENGTH} رقم باشد.` }),
});
type VerifyForm = z.infer<typeof verifySchema>;

/** Step 2 of user auth: OTP verification with countdown + controlled resend. */
export default function VerifyPage() {
  return (
    <Suspense fallback={<VerifyFallback />}>
      <VerifyForm />
    </Suspense>
  );
}

function VerifyFallback() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex flex-1 items-center justify-center px-4">
        <p className="text-neutral-500">در حال بارگذاری…</p>
      </main>
      <Footer />
    </div>
  );
}

function VerifyForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { toast } = useToast();
  const otpVerify = useOtpVerify();
  const otpRequest = useOtpRequest();
  const [serverError, setServerError] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(OTP_RESEND_SECONDS);

  const mobile = useMemo(() => {
    const raw = searchParams.get('mobile') ?? '';
    const normalized = normalizeMobile(raw);
    return MOBILE_REGEX.test(normalized) ? normalized : '';
  }, [searchParams]);

  useEffect(() => {
    if (!mobile) router.replace('/auth/login');
  }, [mobile, router]);

  useEffect(() => {
    if (secondsLeft <= 0) return;
    const t = window.setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => window.clearTimeout(t);
  }, [secondsLeft]);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<VerifyForm>({ resolver: zodResolver(verifySchema) });

  const onSubmit = (values: VerifyForm) => {
    setServerError(null);
    otpVerify.mutate(
      { mobile, code: values.code },
      {
        onSuccess: () => {
          toast('با موفقیت وارد شدید. خوش آمدید!', 'success');
          router.replace('/dashboard');
        },
        onError: (err) => {
          if (err instanceof ApiError && (err.code === 'RATE_LIMITED' || err.code === 'USER_DISABLED')) {
            setServerError(getErrorMessage(err.code, err.message));
          } else {
            setServerError('کد تأیید اشتباه است یا منقضی شده است.');
          }
        },
      },
    );
  };

  const resend = () => {
    setServerError(null);
    otpRequest.mutate(mobile, {
      onSuccess: () => {
        setSecondsLeft(OTP_RESEND_SECONDS);
        toast('کد تأیید جدید ارسال شد.', 'success');
      },
      onError: (err) => {
        setServerError(
          err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'ارسال مجدد ناموفق بود.',
        );
      },
    });
  };

  const mm = Math.floor(secondsLeft / 60);
  const ss = String(secondsLeft % 60).padStart(2, '0');

  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="card w-full max-w-md">
          <h1 className="text-2xl font-extrabold">تأیید شماره موبایل</h1>
          <p className="mt-2 text-sm text-neutral-600 dark:text-slate-400">
            کد {OTP_LENGTH} رقمی ارسال‌شده به <span dir="ltr" className="font-semibold tabular-nums">{mobile}</span> را
            وارد کنید.
          </p>

          <form onSubmit={handleSubmit(onSubmit)} className="mt-6 flex flex-col gap-4" noValidate>
            <div>
              <label htmlFor="code" className="label">
                کد تأیید
              </label>
              <input
                id="code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                dir="ltr"
                maxLength={OTP_LENGTH}
                placeholder="•••••"
                className={`input text-center text-2xl tracking-[0.5em] ${errors.code ? 'input-error' : ''}`}
                aria-invalid={!!errors.code}
                {...register('code')}
              />
              {errors.code && (
                <p role="alert" className="field-error">
                  {errors.code.message}
                </p>
              )}
            </div>

            {serverError && (
              <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
                {serverError}
              </p>
            )}

            <button type="submit" disabled={isSubmitting || otpVerify.isPending} className="btn-primary w-full">
              {isSubmitting || otpVerify.isPending ? 'در حال بررسی…' : 'ورود'}
            </button>

            <div className="text-center text-sm">
              {secondsLeft > 0 ? (
                <p className="text-neutral-500 dark:text-slate-400" aria-live="polite">
                  ارسال مجدد کد تا {mm}:{ss} دیگر
                </p>
              ) : (
                <button
                  type="button"
                  onClick={resend}
                  disabled={otpRequest.isPending}
                  className="inline-link font-semibold text-brand-700 hover:underline dark:text-brand-400"
                >
                  {otpRequest.isPending ? 'در حال ارسال…' : 'ارسال مجدد کد'}
                </button>
              )}
            </div>
          </form>
        </div>
      </main>
      <Footer />
    </div>
  );
}
