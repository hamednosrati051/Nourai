'use client';

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useSiteSettings, useUpdateSiteSettings } from '@/features/site/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { ErrorState } from '@/components/ErrorState';
import { useToast } from '@/components/Toast';
import { ApiError, getErrorMessage } from '@/lib/api';

const formSchema = z.object({
  contact_phone: z.string().max(64).optional().or(z.literal('')),
  contact_email: z.string().max(128).optional().or(z.literal('')),
  contact_address: z.string().max(512).optional().or(z.literal('')),
  contact_telegram: z.string().max(128).optional().or(z.literal('')),
  contact_instagram: z.string().max(128).optional().or(z.literal('')),
  contact_description: z.string().max(2048).optional().or(z.literal('')),
});
type FormValues = z.infer<typeof formSchema>;

/** Admin site settings: contact page info. */
export default function AdminSiteSettingsPage() {
  const { toast } = useToast();
  const settings = useSiteSettings();
  const update = useUpdateSiteSettings();

  const {
    register,
    handleSubmit,
    reset,
    formState: { isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(formSchema) });

  useEffect(() => {
    if (settings.data) {
      reset({
        contact_phone: settings.data.contact_phone ?? '',
        contact_email: settings.data.contact_email ?? '',
        contact_address: settings.data.contact_address ?? '',
        contact_telegram: settings.data.contact_telegram ?? '',
        contact_instagram: settings.data.contact_instagram ?? '',
        contact_description: settings.data.contact_description ?? '',
      });
    }
  }, [settings.data, reset]);

  const onSave = (values: FormValues) => {
    update.mutate(values, {
      onSuccess: () => toast('تنظیمات سایت ذخیره شد.', 'success'),
      onError: (e) =>
        toast(
          e instanceof ApiError ? getErrorMessage(e.code, e.message) : 'ذخیره ناموفق بود.',
          'error',
        ),
    });
  };

  if (settings.isLoading) return <LoadingSpinner label="در حال بارگذاری تنظیمات…" />;
  if (settings.isError)
    return (
      <ErrorState
        message={
          settings.error instanceof ApiError
            ? getErrorMessage(settings.error.code, settings.error.message)
            : 'بارگذاری تنظیمات ناموفق بود.'
        }
        onRetry={() => settings.refetch()}
      />
    );

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="mb-6 text-2xl font-black">تنظیمات سایت — تماس با ما</h1>
      <form onSubmit={handleSubmit(onSave)} className="card space-y-4">
        <div>
          <label htmlFor="ss-phone" className="label">تلفن</label>
          <input id="ss-phone" className="input" dir="ltr" {...register('contact_phone')} />
        </div>
        <div>
          <label htmlFor="ss-email" className="label">ایمیل</label>
          <input id="ss-email" className="input" dir="ltr" {...register('contact_email')} />
        </div>
        <div>
          <label htmlFor="ss-address" className="label">نشانی</label>
          <textarea id="ss-address" className="input resize-none" rows={2} {...register('contact_address')} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="ss-telegram" className="label">تلگرام (آیدی)</label>
            <input id="ss-telegram" className="input" dir="ltr" placeholder="@nourai" {...register('contact_telegram')} />
          </div>
          <div>
            <label htmlFor="ss-instagram" className="label">اینستاگرام (آیدی)</label>
            <input id="ss-instagram" className="input" dir="ltr" placeholder="@nourai" {...register('contact_instagram')} />
          </div>
        </div>
        <div>
          <label htmlFor="ss-desc" className="label">توضیحات</label>
          <textarea id="ss-desc" className="input resize-none" rows={4} {...register('contact_description')} />
        </div>
        <button type="submit" className="btn-primary" disabled={isSubmitting || update.isPending}>
          {isSubmitting || update.isPending ? 'در حال ذخیره…' : 'ذخیره'}
        </button>
      </form>
    </div>
  );
}
