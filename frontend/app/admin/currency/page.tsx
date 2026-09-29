'use client';

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  useCurrencySettings,
  useUpdateCurrencySettings,
} from '@/features/admin/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { ErrorState } from '@/components/ErrorState';
import { useToast } from '@/components/Toast';
import { ApiError, getErrorMessage } from '@/lib/api';
import { irrToToman, tomanToIrr } from '@/lib/currency';

const formSchema = z.object({
  /** USD rate in toman (converted to IRR on submit). */
  usd_toman: z.coerce.number().min(0, 'نرخ دلار نامعتبر است.'),
  /** Margin percent applied when provider cost exceeds our tariff. */
  margin_pct: z.coerce.number().min(0, 'باید عدد مثبت باشد.').max(100, 'حداکثر ۱۰۰ درصد.'),
});
type FormValues = z.infer<typeof formSchema>;

/** Admin currency settings: USD->IRR rate + image cost-protection margin. */
export default function AdminCurrencyPage() {
  const { toast } = useToast();
  const settings = useCurrencySettings();
  const update = useUpdateCurrencySettings();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(formSchema) });

  useEffect(() => {
    if (settings.data) {
      reset({
        usd_toman: irrToToman(settings.data.usd_to_irr),
        margin_pct: settings.data.image_cost_margin_pct,
      });
    }
  }, [settings.data, reset]);

  const onSave = (values: FormValues) => {
    update.mutate(
      {
        usd_to_irr: tomanToIrr(values.usd_toman),
        image_cost_margin_pct: values.margin_pct,
      },
      {
        onSuccess: () => toast('تنظیمات نرخ ارز ذخیره شد.', 'success'),
        onError: (err) =>
          toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'خطایی رخ داد.', 'error'),
      },
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">تنظیمات نرخ ارز</h1>
      <p className="text-sm text-neutral-600 dark:text-slate-400">
        نرخ دلار برای تبدیل هزینه دلاری تولید تصویر به ریال استفاده می‌شود. اگر
        هزینه واقعی تولید از تعرفه شما بیشتر شود، مبلغ نهایی برابر
        «هزینه × (۱ + مارجین)» از کاربر کسر می‌گردد. تا وقتی نرخ دلار صفر است،
        فقط تعرفه شما اعمال می‌شود.
      </p>

      {settings.isLoading && <LoadingSpinner />}
      {settings.isError && (
        <ErrorState message="بارگذاری تنظیمات ناموفق بود." onRetry={() => settings.refetch()} />
      )}

      {settings.data && (
        <form onSubmit={handleSubmit(onSave)} className="card flex max-w-xl flex-col gap-4" noValidate>
          <div>
            <label htmlFor="cur-usd" className="label">نرخ دلار (تومان)</label>
            <input
              id="cur-usd"
              type="number"
              min={0}
              step="any"
              dir="ltr"
              className={`input text-left tabular-nums ${errors.usd_toman ? 'input-error' : ''}`}
              {...register('usd_toman')}
            />
            {errors.usd_toman && <p role="alert" className="field-error">{errors.usd_toman.message}</p>}
            <p className="mt-1 text-xs text-neutral-500">صفر یعنی «تنظیم نشده» — محافظت هزینه غیرفعال می‌ماند.</p>
          </div>
          <div>
            <label htmlFor="cur-margin" className="label">مارجین هزینه تولید تصویر (٪)</label>
            <input
              id="cur-margin"
              type="number"
              min={0}
              max={100}
              step="any"
              dir="ltr"
              className={`input text-left tabular-nums ${errors.margin_pct ? 'input-error' : ''}`}
              {...register('margin_pct')}
            />
            {errors.margin_pct && <p role="alert" className="field-error">{errors.margin_pct.message}</p>}
          </div>
          <button type="submit" disabled={isSubmitting || update.isPending} className="btn-primary">
            {isSubmitting || update.isPending ? 'در حال ذخیره…' : 'ذخیره'}
          </button>
        </form>
      )}
    </div>
  );
}
