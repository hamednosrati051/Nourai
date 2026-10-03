'use client';

import { useEffect, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  useImageConfig,
  useCreateImageJob,
  useImageJob,
  useImageJobs,
} from '@/features/image/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { Modal } from '@/components/Modal';
import { useToast } from '@/components/Toast';
import { formatBytes, formatDateTime } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { ImageJob, ImageJobStatus } from '@/types/api';

const formSchema = z.object({
  type: z.enum(['text_to_image', 'image_to_image']),
  prompt: z.string().trim().min(1, 'توضیح تصویر (prompt) را بنویسید.').max(2000, 'متن بیش از حد طولانی است.'),
});
type ImageForm = z.infer<typeof formSchema>;

const JOB_STATUS_META: Record<ImageJobStatus, { label: string; badge: string }> = {
  queued: { label: 'در صف', badge: 'badge-neutral' },
  processing: { label: 'در حال تولید', badge: 'badge-info' },
  succeeded: { label: 'آماده', badge: 'badge-success' },
  failed: { label: 'ناموفق', badge: 'badge-danger' },
  cancelled: { label: 'لغوشده', badge: 'badge-neutral' },
};

/** Image studio: text-to-image + image-to-image with limits, preview, polling. */
export default function ImagePage() {
  const { toast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [inputFile, setInputFile] = useState<File | null>(null);
  const [inputPreview, setInputPreview] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [trackedJobId, setTrackedJobId] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState(1);
  const [viewingJob, setViewingJob] = useState<ImageJob | null>(null);

  const config = useImageConfig();
  const createJob = useCreateImageJob();
  const trackedJob = useImageJob(trackedJobId);
  const history = useImageJobs(historyPage);
  const doneImages = (history.data?.items ?? []).filter(
    (job) => job.status === 'succeeded' && job.result_url,
  );

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<ImageForm>({
    resolver: zodResolver(formSchema),
    defaultValues: { type: 'text_to_image' },
  });

  // The backend picks the right image model per mode automatically
  // (edit model for image_to_image, generation model otherwise), so the
  // user never chooses a model here.
  const jobType = watch('type');

  // Object URL for the selected input image preview.

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

  const cfg = config.data;

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

  const onSubmit = handleSubmit((values) => {
    if (values.type === 'image_to_image' && !inputFile) {
      setFileError('برای ویرایش تصویر، یک فایل انتخاب کنید.');
      return;
    }
    createJob.mutate(
      {
        type: values.type,
        prompt: values.prompt,
        inputFile: values.type === 'image_to_image' ? inputFile ?? undefined : undefined,
        // No model_id: the backend picks the generation model or the edit
        // model automatically based on the job type.
      },
      {
        onSuccess: (job) => {
          setTrackedJobId(job.id);
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

            <div className="flex flex-col gap-2 sm:flex-row">
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

          {/* User's image history */}
          <section aria-label="تصاویر شما" className="flex flex-col gap-3">
            <h2 className="text-lg font-extrabold">تصاویر شما</h2>
            {history.isLoading && <LoadingSpinner label="در حال بارگذاری تصاویر…" />}
            {history.isError && (
              <ErrorState message="بارگذاری تصاویر ناموفق بود." onRetry={() => history.refetch()} />
            )}
            {history.data && doneImages.length === 0 && (
              <EmptyState
                icon="🎨"
                title="هنوز تصویری تولید نکرده‌اید"
                description="از فرم بالا اولین تصویرتان را بسازید."
              />
            )}
            {doneImages.length > 0 && (
              <>
                <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {doneImages.map((job) => (
                    <li key={job.id} className="card group !p-2">
                      <button
                        type="button"
                        onClick={() => setViewingJob(job)}
                        className="relative block w-full overflow-hidden rounded-lg bg-neutral-100 dark:bg-navy-800"
                        style={{ aspectRatio: '1 / 1' }}
                        aria-label={`مشاهده تصویر: ${job.prompt}`}
                      >
                        {job.result_url ? (
                          <img
                            src={job.result_url}
                            alt={job.prompt}
                            loading="lazy"
                            className="absolute inset-0 h-full w-full object-cover transition-transform group-hover:scale-105"
                          />
                        ) : (
                          <span className="absolute inset-0 flex items-center justify-center text-xs text-neutral-400">
                            {JOB_STATUS_META[job.status]?.label ?? job.status}
                          </span>
                        )}
                      </button>
                      <p className="mt-1 line-clamp-1 px-1 text-xs text-neutral-600 dark:text-slate-400">
                        {job.prompt}
                      </p>
                    </li>
                  ))}
                </ul>
                {(history.data?.meta.total_pages ?? 1) > 1 && (
                  <div className="flex items-center justify-center gap-3">
                    <button
                      type="button"
                      onClick={() => setHistoryPage((p) => Math.max(1, p - 1))}
                      disabled={historyPage <= 1}
                      className="btn-secondary btn-sm"
                    >
                      قبلی
                    </button>
                    <span className="text-sm text-neutral-500">
                      صفحه {historyPage} از {history.data?.meta.total_pages}
                    </span>
                    <button
                      type="button"
                      onClick={() => setHistoryPage((p) => p + 1)}
                      disabled={historyPage >= (history.data?.meta.total_pages ?? 1)}
                      className="btn-secondary btn-sm"
                    >
                      بعدی
                    </button>
                  </div>
                )}
              </>
            )}
          </section>

          {/* Full-size viewer */}
          <Modal
            open={!!viewingJob}
            title="مشاهده تصویر"
            onClose={() => setViewingJob(null)}
          >
            {viewingJob?.result_url && (
              <div className="flex flex-col gap-3">
                <img
                  src={viewingJob.result_url}
                  alt={viewingJob.prompt}
                  className="max-h-[70vh] w-full rounded-xl object-contain bg-neutral-100 dark:bg-navy-800"
                />
                <p className="line-clamp-2 text-sm text-neutral-600 dark:text-slate-400">
                  {viewingJob.prompt}
                </p>
                <a
                  href={viewingJob.result_url}
                  download
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-primary w-full text-center"
                >
                  دانلود تصویر
                </a>
              </div>
            )}
          </Modal>
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
            <span>{formatDateTime(job.created_at)}</span>
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
