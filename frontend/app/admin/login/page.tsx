'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { BRAND } from '@/lib/config';
import { useAdminLogin } from '@/features/auth/hooks';
import { useToast } from '@/components/Toast';
import { ApiError } from '@/lib/api';

const adminLoginSchema = z.object({
  username: z.string().trim().min(1, 'نام کاربری را وارد کنید.'),
  password: z.string().min(1, 'رمز عبور را وارد کنید.'),
});
type AdminLoginForm = z.infer<typeof adminLoginSchema>;

/** Admin sign-in (username + password; separate session from users). */
export default function AdminLoginPage() {
  const router = useRouter();
  const { toast } = useToast();
  const adminLogin = useAdminLogin();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<AdminLoginForm>({ resolver: zodResolver(adminLoginSchema) });

  const onSubmit = (values: AdminLoginForm) => {
    setServerError(null);
    adminLogin.mutate(values, {
      onSuccess: () => {
        toast('ورود ادمین با موفقیت انجام شد.', 'success');
        router.replace('/admin');
      },
      onError: (err) => {
        if (err instanceof ApiError && err.code === 'RATE_LIMITED') {
          setServerError('تلاش‌های ناموفق زیاد است؛ لطفاً کمی بعد دوباره تلاش کنید.');
        } else {
          setServerError('نام کاربری یا رمز عبور اشتباه است.');
        }
      },
    });
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="card w-full max-w-md">
        <h1 className="text-2xl font-extrabold">ورود ادمین {BRAND.fa}</h1>
        <p className="mt-2 text-sm text-neutral-600 dark:text-slate-400">
          این بخش فقط برای مدیران سیستم است.
        </p>

        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 flex flex-col gap-4" noValidate>
          <div>
            <label htmlFor="admin-username" className="label">
              نام کاربری
            </label>
            <input
              id="admin-username"
              type="text"
              autoComplete="username"
              dir="ltr"
              className={`input text-left ${errors.username ? 'input-error' : ''}`}
              {...register('username')}
            />
            {errors.username && (
              <p role="alert" className="field-error">
                {errors.username.message}
              </p>
            )}
          </div>
          <div>
            <label htmlFor="admin-password" className="label">
              رمز عبور
            </label>
            <input
              id="admin-password"
              type="password"
              autoComplete="current-password"
              dir="ltr"
              className={`input text-left ${errors.password ? 'input-error' : ''}`}
              {...register('password')}
            />
            {errors.password && (
              <p role="alert" className="field-error">
                {errors.password.message}
              </p>
            )}
          </div>

          {serverError && (
            <p role="alert" className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-300">
              {serverError}
            </p>
          )}

          <button type="submit" disabled={isSubmitting || adminLogin.isPending} className="btn-primary w-full">
            {isSubmitting || adminLogin.isPending ? 'در حال بررسی…' : 'ورود'}
          </button>
        </form>
      </div>
    </main>
  );
}
