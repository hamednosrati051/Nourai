'use client';

import { Settings } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  useImageProfiles,
  useImageProfilePreview,
  useUpdateImageProfile,
} from '@/features/admin/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { Modal } from '@/components/Modal';
import { useToast } from '@/components/Toast';
import { formatBytes, formatNumber } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { ImagePreviewResult, ImageProfile, ResizeMode } from '@/types/api';
import type { UseFormRegisterReturn } from 'react-hook-form';

const RESIZE_LABELS: Record<ResizeMode, string> = { fit: 'fit', fill: 'fill', stretch: 'stretch' };

const profileSchema = z.object({
  name: z.string().trim().min(1, 'نام پروفایل را وارد کنید.'),
  max_upload_bytes: z.number().int().positive('باید عدد مثبت باشد.'),
  max_input_pixels: z.number().int().positive('باید عدد مثبت باشد.'),
  allowed_mime_types: z.string().trim().min(1, 'حداقل یک MIME وارد کنید.'),
  target_width: z.number().int().positive('باید عدد مثبت باشد.'),
  target_height: z.number().int().positive('باید عدد مثبت باشد.'),
  resize_mode: z.enum(['fit', 'fill', 'stretch']),
  output_format: z.string().trim().min(1, 'فرمت خروجی را وارد کنید.'),
  output_quality: z.number().int().min(1).max(100),
  allow_upscale: z.boolean(),
  is_active: z.boolean(),
});
type ProfileForm = z.infer<typeof profileSchema>;

/** Admin image-processing profiles: limits, resize, preview before/after. */
export default function AdminImageSettingsPage() {
  const { toast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState<ImageProfile | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewFile, setPreviewFile] = useState<File | null>(null);
  const [previewResult, setPreviewResult] = useState<ImagePreviewResult | null>(null);

  const profiles = useImageProfiles();
  const updateProfile = useUpdateImageProfile();
  const preview = useImageProfilePreview();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ProfileForm>({ resolver: zodResolver(profileSchema) });

  useEffect(() => {
    if (editing) {
      reset({
        name: editing.name,
        max_upload_bytes: editing.max_upload_bytes,
        max_input_pixels: editing.max_input_pixels,
        allowed_mime_types: editing.allowed_mime_types.join(', '),
        target_width: editing.target_width,
        target_height: editing.target_height,
        resize_mode: editing.resize_mode,
        output_format: editing.output_format,
        output_quality: editing.output_quality,
        allow_upscale: editing.allow_upscale,
        is_active: editing.is_active,
      });
    }
  }, [editing, reset]);

  const onSave = (values: ProfileForm) => {
    if (!editing) return;
    if (values.target_width * values.target_height > values.max_input_pixels) {
      toast('ابعاد مقصد از سقف پیکسل بیشتر است.', 'error');
      return;
    }
    updateProfile.mutate(
      {
        id: editing.id,
        patch: {
          ...values,
          allowed_mime_types: values.allowed_mime_types.split(',').map((s) => s.trim()).filter(Boolean),
        },
      },
      {
        onSuccess: () => {
          setEditing(null);
          toast('پروفایل به‌روزرسانی شد.', 'success');
        },
        onError: (err) =>
          toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'خطایی رخ داد.', 'error'),
      },
    );
  };

  const runPreview = () => {
    if (!editing || !previewFile) {
      toast('یک فایل آزمایشی انتخاب کنید.', 'error');
      return;
    }
    setPreviewResult(null);
    preview.mutate(
      { profileId: editing.id, file: previewFile },
      {
        onSuccess: (data) => setPreviewResult(data),
        onError: (err) =>
          toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'پیش‌نمایش ناموفق بود.', 'error'),
      },
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">تنظیمات پردازش تصویر</h1>
      <p className="text-sm text-neutral-600 dark:text-slate-400">
        سقف حجم و ابعاد، فرمت‌های مجاز، ابعاد مقصد و روش resize. سقف‌های امنیتی backend با این تنظیمات قابل افزایش نیستند.
      </p>

      {profiles.isLoading && <LoadingSpinner />}
      {profiles.isError && <ErrorState message="بارگذاری پروفایل‌ها ناموفق بود." onRetry={() => profiles.refetch()} />}
      {profiles.data && profiles.data.length === 0 && (
        <EmptyState icon={Settings} title="پروفایلی نیست" description="هنوز پروفایل پردازش تصویر ثبت نشده است." />
      )}

      {profiles.data && profiles.data.length > 0 && (
        <ul className="grid gap-4 lg:grid-cols-2">
          {profiles.data.map((p) => (
            <li key={p.id} className="card">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-bold">{p.name}</h2>
                  <p className="text-xs text-neutral-500 dark:text-slate-400">
                    {p.is_global ? 'سراسری' : `مدل: ${p.model_id ?? '—'}`}
                  </p>
                </div>
                {p.is_active ? <span className="badge-success">فعال</span> : <span className="badge-neutral">غیرفعال</span>}
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <dt className="text-neutral-500 dark:text-slate-400">سقف حجم</dt>
                <dd className="text-left tabular-nums">{formatBytes(p.max_upload_bytes)}</dd>
                <dt className="text-neutral-500 dark:text-slate-400">ابعاد مقصد</dt>
                <dd className="text-left tabular-nums" dir="ltr">{p.target_width}×{p.target_height}</dd>
                <dt className="text-neutral-500 dark:text-slate-400">روش resize</dt>
                <dd className="text-left" dir="ltr">{RESIZE_LABELS[p.resize_mode]}</dd>
                <dt className="text-neutral-500 dark:text-slate-400">فرمت / کیفیت</dt>
                <dd className="text-left tabular-nums" dir="ltr">{p.output_format} / {formatNumber(p.output_quality)}</dd>
                <dt className="text-neutral-500 dark:text-slate-400">upscale</dt>
                <dd className="text-left">{p.allow_upscale ? 'مجاز' : 'ممنوع'}</dd>
              </dl>
              <div className="mt-4 flex gap-2">
                <button type="button" onClick={() => setEditing(p)} className="btn-secondary btn-sm flex-1">
                  ویرایش
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setEditing(p);
                    setPreviewOpen(true);
                    setPreviewResult(null);
                    setPreviewFile(null);
                  }}
                  className="btn-ghost btn-sm flex-1"
                >
                  پیش‌نمایش تبدیل
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Edit modal */}
      <Modal open={!!editing && !previewOpen} title={`ویرایش پروفایل: ${editing?.name ?? ''}`} onClose={() => setEditing(null)} maxWidth="max-w-2xl">
        <form onSubmit={handleSubmit(onSave)} className="grid gap-4 sm:grid-cols-2" noValidate>
          <div className="sm:col-span-2">
            <label htmlFor="pf-name" className="label">نام</label>
            <input id="pf-name" className={`input ${errors.name ? 'input-error' : ''}`} {...register('name')} />
            {errors.name && <p role="alert" className="field-error">{errors.name.message}</p>}
          </div>
          <NumberField id="pf-max-bytes" label="سقف حجم (بایت)" error={errors.max_upload_bytes?.message} register={register('max_upload_bytes', { valueAsNumber: true })} />
          <NumberField id="pf-max-pixels" label="سقف پیکسل" error={errors.max_input_pixels?.message} register={register('max_input_pixels', { valueAsNumber: true })} />
          <NumberField id="pf-target-w" label="عرض مقصد" error={errors.target_width?.message} register={register('target_width', { valueAsNumber: true })} />
          <NumberField id="pf-target-h" label="ارتفاع مقصد" error={errors.target_height?.message} register={register('target_height', { valueAsNumber: true })} />
          <div>
            <label htmlFor="pf-resize" className="label">روش resize</label>
            <select id="pf-resize" className="input" {...register('resize_mode')}>
              <option value="fit">fit</option>
              <option value="fill">fill</option>
              <option value="stretch">stretch</option>
            </select>
          </div>
          <div>
            <label htmlFor="pf-format" className="label">فرمت خروجی</label>
            <input id="pf-format" dir="ltr" className="input text-left" placeholder="webp" {...register('output_format')} />
          </div>
          <NumberField id="pf-quality" label="کیفیت (۱ تا ۱۰۰)" error={errors.output_quality?.message} register={register('output_quality', { valueAsNumber: true })} />
          <div>
            <label htmlFor="pf-mimes" className="label">MIMEهای مجاز (با کاما)</label>
            <input id="pf-mimes" dir="ltr" className="input text-left" placeholder="image/jpeg, image/png, image/webp" {...register('allowed_mime_types')} />
          </div>
          <label className="flex items-center gap-2 text-sm font-medium">
            <input type="checkbox" className="h-5 w-5 accent-amber-600" {...register('allow_upscale')} />
            بزرگ‌نمایی (upscale) مجاز باشد
          </label>
          <label className="flex items-center gap-2 text-sm font-medium">
            <input type="checkbox" className="h-5 w-5 accent-amber-600" {...register('is_active')} />
            پروفایل فعال باشد
          </label>
          <div className="flex gap-2 sm:col-span-2">
            <button type="submit" disabled={isSubmitting || updateProfile.isPending} className="btn-primary flex-1">
              {isSubmitting || updateProfile.isPending ? 'در حال ذخیره…' : 'ذخیره'}
            </button>
            <button type="button" onClick={() => setEditing(null)} className="btn-secondary flex-1">
              انصراف
            </button>
          </div>
        </form>
      </Modal>

      {/* Preview modal */}
      <Modal open={previewOpen} title="پیش‌نمایش تبدیل (بدون ذخیره عمومی)" onClose={() => { setPreviewOpen(false); setEditing(null); }} maxWidth="max-w-2xl">
        <p className="mb-3 text-sm text-neutral-600 dark:text-slate-400">
          فایل آزمایشی فقط برای پیش‌نمایش پردازش می‌شود و عمومی نمی‌شود.
        </p>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          onChange={(e) => setPreviewFile(e.target.files?.[0] ?? null)}
          className="input cursor-pointer"
          aria-label="فایل آزمایشی"
        />
        <button type="button" onClick={runPreview} disabled={preview.isPending || !previewFile} className="btn-primary mt-3 w-full">
          {preview.isPending ? 'در حال پردازش…' : 'اجرای پیش‌نمایش'}
        </button>

        {previewResult && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2" aria-live="polite">
            <div className="rounded-xl border border-neutral-200 p-3 dark:border-white/15">
              <p className="mb-2 text-sm font-bold">قبل</p>
              <p className="text-xs text-neutral-500 tabular-nums" dir="ltr">
                {previewResult.before_width}×{previewResult.before_height} — {formatBytes(previewResult.before_bytes)}
              </p>
            </div>
            <div className="rounded-xl border border-neutral-200 p-3 dark:border-white/15">
              <p className="mb-2 text-sm font-bold">بعد</p>
              <p className="text-xs text-neutral-500 tabular-nums" dir="ltr">
                {previewResult.after_width}×{previewResult.after_height} — {formatBytes(previewResult.after_bytes)}
              </p>
            </div>
            <div className="sm:col-span-2">
              <img src={previewResult.preview_url} alt="پیش‌نمایش تصویر پردازش‌شده" className="max-h-80 rounded-xl border border-neutral-200 object-contain dark:border-white/15" />
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}

function NumberField({
  id,
  label,
  error,
  register,
}: {
  id: string;
  label: string;
  error?: string;
  register: UseFormRegisterReturn;
}) {
  return (
    <div>
      <label htmlFor={id} className="label">{label}</label>
      <input id={id} type="number" min={1} dir="ltr" className={`input text-left tabular-nums ${error ? 'input-error' : ''}`} {...register} />
      {error && <p role="alert" className="field-error">{error}</p>}
    </div>
  );
}
