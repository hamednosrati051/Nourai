'use client';

import { useEffect, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  useImageConfig,
  useImageEstimate,
  useCreateImageJob,
  useImageJob,
} from '@/features/image/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { useToast } from '@/components/Toast';
import { formatToman } from '@/lib/currency';
import { formatBytes, formatDateTime, formatNumber } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { ImageEstimate, ImageJob, ImageJobStatus } from '@/types/api';

const formSchema = z.object({
  type: z.enum(['text_to_image', 'image_to_image']),
  model_id: z.string().min(1, 'مدل را انتخاب کنید.'),
  prompt: z.string().trim().min(1, 'توضیح تصویر (prompt) را بنویسید.').max(2000, 'متن بیش از حد طولانی است.'),
  size: z.string().optional(),
  quality: z.string().optional(),
});
type ImageForm = z.infer<typeof formSchema>;

const JOB_STATUS_META: Record<ImageJobStatus, { label: string; badge: string }> = {
  queued: { label: 'در صف', badge: 'badge-neutral' },
  processing: { label: 'در حال تولید', badge: 'badge-info' },
  succeeded: { label: 'آماده', badge: 'badge-success' },
  failed: { label: 'ناموفق', badge: 'badge-danger' },
};

/** Image studio: text-to-image + image-to-image with limits, preview, estimate, polling. */
export default function ImagePage() {
  const { toast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [inputFile, setInputFile] = useState<File | null>(null);
  const [inputPreview, setInputPreview] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [estimate, setEstimate] = useState<ImageEstimate | null>(null);
  const [trackedJobId, setTrackedJobId] = useState<string | null>(null);

  const config = useImageConfig();
  const estimateMutation = useImageEstimate();
  const createJob = useCreateImageJob();
  const trackedJob = useImageJob(trackedJobId);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ImageForm>({
    resolver: zodResolver(formSchema),
    defaultValues: { type: 'text_to_image' },
  });

  const jobType = watch('type');
  const modelId = watch('model_id');

  // Object URL for the selected input image preview.
  useEffect(() => {
    if (!inputFile) {
      setInputPreview(null);
      return;
    }
    const url = URL.createObjectURL(inputFile);
    setInputPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [inputFile]);

  // Clear the estimate whenever inputs change.
  useEffect(() => {
    setEstimate(null);
  }, [jobType, modelId, inputFile]);

  const cfg = config.data;
  // /image/config already returns only image-capable models.
  const imageModels = cfg?.models ?? [];

  const onFileChange = (f: File | null) => {
    setFileError(null);
    if (!f) {
      setInputFile(null);
      return;
    }
    if (cfg) {
      if (!cfg.allowed_mime_types.includes(f.type)) {
        setFileError(`فرمت مجاز نیست. فرمت‌های مجاز: ${cfg.allowed_mime_types.join('، ')}`);
        setInputFile(null);
        return;
      }
      if (f.size > cfg.max_upload_bytes) {
        setFileError(`حجم فایل نباید بیشتر از ${formatBytes(cfg.max_upload_bytes)} باشد.`);
        setInputFile(null);
        return;
      }
    }
    setInputFile(f);
  };

  const runEstimate = handleSubmit((values) => {
    if (values.type === 'image_to_image' && !inputFile) {
      setFileError('برای ویرایش تصویر، یک فایل انتخاب کنید.');
      return;
    }
    estimateMutation.mutate(
      {
        type: values.type,
        model_id: values.model_id,
        prompt: values.prompt,
        size: values.size || undefined,
        quality: values.quality || undefined,
      },
      {
        onSuccess: (data) => setEstimate(data),
        onError: (err) =>
          toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'برآورد هزینه ناموفق بود.', 'error'),
      },
    );
  });

  const onSubmit = handleSubmit((values) => {
    if (values.type === 'image_to_image' && !inputFile) {
      setFileError('برای ویرایش تصویر، یک فایل انتخاب کنید.');
      return;
    }
    createJob.mutate(
      {
        type: values.type,
        model_id: values.model_id,
        prompt: values.prompt,
        size: values.size || undefined,
        quality: values.quality || undefined,
        inputFile: values.type === 'image_to_image' ? inputFile ?? undefined : undefined,
      },
      {
        onSuccess: (job) => {
          setTrackedJobId(job.id);
          setEstimate(null);
          toast('درخواست ثبت شد؛ تولید تصویر آغاز شد.', 'success');
        },
        onError: (err) => {
          if (err instanceof ApiError && err.code === 'INSUFFICIENT_BALANCE') {
            toast('موجودی کافی نیست؛ لطفاً کیف پول را شارژ کنید.', 'error');
          } else {
            toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'ثبت درخواست ناموفق بود.', 'error');
          }
        },
      },
    );
  });

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">تولید تصویر</h1>

      {config.isLoading && <LoadingSpinner label="در حال بارگذاری تنظیمات…" />}
      {config.isError && (
        <ErrorState message="بارگذاری تنظیمات تصویر ناموفق بود." onRetry={() => config.refetch()} />
      )}

      {cfg && (
        <>
          <form onSubmit={onSubmit} className="card flex flex-col gap-5" noValidate>
            {/* Mode toggle */}
            <div role="radiogroup" aria-label="نوع تولید" className="grid grid-cols-2 gap-2">
              {(
                [
                  { value: 'text_to_image', label: 'تولید از متن', icon: '✨' },
                  { value: 'image_to_image', label: 'ویرایش تصویر', icon: '🖌️' },
                ] as const
              ).map((opt) => (
                <label
                  key={opt.value}
                  className={`flex cursor-pointer items-center justify-center gap-2 rounded-xl border px-4 py-3 text-sm font-semibold transition-colors ${
                    jobType === opt.value
                      ? 'border-brand-600 bg-brand-50 text-brand-800 dark:border-brand-400 dark:bg-brand-900/30 dark:text-brand-300'
                      : 'border-neutral-300 text-neutral-600 hover:border-neutral-400 dark:border-white/15 dark:text-slate-400'
                  }`}
                >
                  <input type="radio" value={opt.value} className="sr-only" {...register('type')} />
                  <span aria-hidden="true">{opt.icon}</span>
                  {opt.label}
                </label>
              ))}
            </div>

            {/* Model */}
            <div>
              <label htmlFor="img-model" className="label">
                مدل
              </label>
              <select id="img-model" className={`input ${errors.model_id ? 'input-error' : ''}`} {...register('model_id')}>
                <option value="">انتخاب مدل…</option>
                {imageModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.display_name}
                  </option>
                ))}
              </select>
              {errors.model_id && (
                <p role="alert" className="field-error">
                  {errors.model_id.message}
                </p>
              )}
            </div>

            {/* Prompt */}
            <div>
              <label htmlFor="img-prompt" className="label">
                توضیح تصویر (prompt)
              </label>
              <textarea
                id="img-prompt"
                rows={3}
                placeholder="مثلاً: غروب آفتاب بر فراز کوهستان، سبک نقاشی آبرنگ"
                className={`input resize-none ${errors.prompt ? 'input-error' : ''}`}
                {...register('prompt')}
              />
              {errors.prompt && (
                <p role="alert" className="field-error">
                  {errors.prompt.message}
                </p>
              )}
            </div>

            {/* Size & quality */}
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="img-size" className="label">
                  ابعاد خروجی
                </label>
                <select id="img-size" className="input" {...register('size')}>
                  <option value="">پیش‌فرض</option>
                  {(cfg.sizes ?? []).map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="img-quality" className="label">
                  کیفیت
                </label>
                <select id="img-quality" className="input" {...register('quality')}>
                  <option value="">پیش‌فرض</option>
                  {(cfg.qualities ?? []).map((q) => (
                    <option key={q} value={q}>
                      {q}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Input image for image_to_image */}
            {jobType === 'image_to_image' && (
              <div>
                <label htmlFor="img-input" className="label">
                  تصویر ورودی
                </label>
                <input
                  id="img-input"
                  ref={fileRef}
                  type="file"
                  accept={cfg.allowed_mime_types.join(',')}
                  onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
                  className="input cursor-pointer"
                />
                <p className="field-hint">
                  حداکثر حجم {formatBytes(cfg.max_upload_bytes)} و حداکثر ابعاد{' '}
                  {cfg.max_input_width}×{cfg.max_input_height} پیکسل.
                </p>
                {fileError && (
                  <p role="alert" className="field-error">
                    {fileError}
                  </p>
                )}
                {inputPreview && inputFile && (
                  <div className="mt-3">
                    <p className="mb-2 text-sm font-semibold">پیش‌نمایش تصویر ورودی</p>
                    <img
                      src={inputPreview}
                      alt="پیش‌نمایش تصویر ورودی انتخاب‌شده"
                      className="max-h-64 rounded-xl border border-neutral-200 object-contain dark:border-white/15"
                    />
                    <p className="mt-1 text-xs text-neutral-500">
                      {inputFile.name} — {formatBytes(inputFile.size)}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Current limits */}
            <details className="rounded-xl bg-neutral-50 p-4 text-sm dark:bg-navy-800/60">
              <summary className="cursor-pointer font-semibold">محدودیت‌های فعلی آپلود</summary>
              <ul className="mt-2 list-disc space-y-1 pr-5 text-neutral-600 dark:text-slate-400">
                <li>حداکثر حجم فایل: {formatBytes(cfg.max_upload_bytes)}</li>
                <li>
                  حداکثر ابعاد ورودی: {cfg.max_input_width}×{cfg.max_input_height} پیکسل (
                  {formatNumber(cfg.max_input_pixels)} پیکسل)
                </li>
                <li>فرمت‌های مجاز: {(cfg.allowed_mime_types ?? []).join('، ')}</li>
              </ul>
            </details>

            {/* Estimate */}
            {estimate && (
              <div className="rounded-xl border border-brand-200 bg-brand-50 p-4 dark:border-brand-900/50 dark:bg-brand-950/30" aria-live="polite">
                <h2 className="font-bold">برآورد هزینه</h2>
                <ul className="mt-2 space-y-1 text-sm">
                  {estimate.breakdown.map((line, i) => (
                    <li key={i} className="flex justify-between gap-3">
                      <span className="text-neutral-600 dark:text-slate-400">{line.label}</span>
                      <span className="font-semibold tabular-nums">{formatToman(line.amount_irr)}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-2 flex justify-between border-t border-brand-200 pt-2 font-bold dark:border-brand-900/50">
                  <span>جمع برآورد</span>
                  <span className="tabular-nums">{formatToman(estimate.total_irr)}</span>
                </p>
                <p className="mt-1 text-xs text-neutral-500">
                  این مبلغ برآورد است؛ هزینه نهایی پس از تولید، بر اساس مصرف واقعی تسویه می‌شود.
                </p>
              </div>
            )}

            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                type="button"
                onClick={runEstimate}
                disabled={estimateMutation.isPending || isSubmitting}
                className="btn-secondary flex-1"
              >
                {estimateMutation.isPending ? 'در حال محاسبه…' : 'برآورد هزینه'}
              </button>
              <button
                type="submit"
                disabled={isSubmitting || createJob.isPending}
                className="btn-primary flex-1"
              >
                {isSubmitting || createJob.isPending ? 'در حال ثبت…' : 'ثبت و تولید تصویر'}
              </button>
            </div>
          </form>

          {/* Tracked job */}
          {trackedJobId && (
            <section aria-labelledby="img-job-heading" aria-live="polite" className="card">
              <h2 id="img-job-heading" className="text-lg font-bold">
                نتیجه تولید
              </h2>
              {trackedJob.isLoading && <LoadingSpinner label="در حال بررسی وضعیت…" />}
              {trackedJob.data && <ImageJobResult job={trackedJob.data} />}
            </section>
          )}
        </>
      )}
    </div>
  );
}

function ImageJobResult({ job }: { job: ImageJob }) {
  const meta = JOB_STATUS_META[job.status];

  return (
    <div className="mt-3 flex flex-col gap-3">
      <p>
        وضعیت: <span className={meta.badge}>{meta.label}</span>
      </p>
      {(job.status === 'queued' || job.status === 'processing') && (
        <LoadingSpinner label="تصویر در حال تولید است… لطفاً صبر کنید." />
      )}
      {job.status === 'failed' && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          تولید تصویر ناموفق بود. مبلغ رزروشده به کیف پول برگشت.
        </p>
      )}
      {job.status === 'succeeded' && job.result_url && (
        <>
          <div
            className="relative w-full overflow-hidden rounded-xl border border-neutral-200 dark:border-white/15"
            style={{ aspectRatio: job.result_width && job.result_height ? `${job.result_width} / ${job.result_height}` : '1 / 1' }}
          >
            <img src={job.result_url} alt="تصویر تولیدشده" className="absolute inset-0 h-full w-full object-contain bg-neutral-100 dark:bg-navy-800" />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-neutral-500 dark:text-slate-400">
            <span>
              {formatDateTime(job.created_at)}
              {job.cost_irr != null && <> — هزینه نهایی: {formatToman(job.cost_irr)}</>}
            </span>
            <a href={job.result_url} download className="btn-secondary btn-sm" target="_blank" rel="noopener noreferrer">
              دانلود تصویر
            </a>
          </div>
        </>
      )}
      {job.status === 'succeeded' && !job.result_url && (
        <EmptyState icon="🖼️" title="نتیجه‌ای ثبت نشده" description="تصویری برای این درخواست یافت نشد." />
      )}
    </div>
  );
}
