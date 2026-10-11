'use client';

import { Clapperboard, Film } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  useVideoConfig,
  useCreateVideoJob,
  useVideoJob,
  useVideoJobs,
} from '@/features/video/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { NouraAvatar } from '@/components/NouraAvatar';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { Modal } from '@/components/Modal';
import { PromptBox } from '@/components/PromptBox';
import { useToast } from '@/components/Toast';
import { formatDateTime } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { VideoJob, VideoJobStatus } from '@/types/api';

const formSchema = z.object({
  prompt: z.string().trim().min(1, 'توضیح ویدیو (prompt) را بنویسید.').max(2000, 'متن بیش از حد طولانی است.'),
  seconds: z.number().int(),
  size: z.string().min(1),
});
type VideoForm = z.infer<typeof formSchema>;

const JOB_STATUS_META: Record<VideoJobStatus, { label: string; badge: string }> = {
  queued: { label: 'در صف', badge: 'badge-neutral' },
  processing: { label: 'در حال تولید', badge: 'badge-info' },
  succeeded: { label: 'آماده', badge: 'badge-success' },
  failed: { label: 'ناموفق', badge: 'badge-danger' },
  cancelled: { label: 'لغوشده', badge: 'badge-neutral' },
};

const SIZE_LABELS: Record<string, string> = {
  landscape: 'افقی (۱۶:۹)',
  portrait: 'عمودی (۹:۱۶)',
  square: 'مربع (۱:۱)',
};

/** Video studio: text-to-video with duration/size selection, preview, polling. */
export default function VideoPage() {
  const { toast } = useToast();
  const [trackedJobId, setTrackedJobId] = useState<string | null>(null);
  const [historyPage, setHistoryPage] = useState(1);
  const [viewingJob, setViewingJob] = useState<VideoJob | null>(null);
  const [imageBase64, setImageBase64] = useState<string | null>(null);

  const config = useVideoConfig();
  const createJob = useCreateVideoJob();
  const trackedJob = useVideoJob(trackedJobId);
  const history = useVideoJobs(historyPage);
  const doneVideos = (history.data?.items ?? []).filter(
    (job) => job.status === 'succeeded' && job.result_url,
  );

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) {
      setImageBase64(null);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      // Remove data URL prefix, keep only base64
      const base64 = result.split(',')[1] || result;
      setImageBase64(base64);
    };
    reader.readAsDataURL(file);
  };

  const cfg = config.data;
  const durations = cfg?.durations ?? [4, 8, 12];
  const sizes = cfg?.sizes ?? [];

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<VideoForm>({
    resolver: zodResolver(formSchema),
    defaultValues: { seconds: 4, size: 'landscape' },
  });

  const onSubmit = handleSubmit((values) => {
    createJob.mutate(
      {
        prompt: values.prompt,
        seconds: values.seconds,
        size: values.size,
        // No model_id: the backend picks the active video model automatically.
        ...(imageBase64 ? { image_base64: imageBase64 } : {}),
      },
      {
        onSuccess: (job) => {
          setTrackedJobId(job.id);
          toast('درخواست ثبت شد؛ تولید ویدیو آغاز شد (چند دقیقه طول می‌کشد).', 'success');
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
      <div className="flex items-center gap-3">
        <NouraAvatar working={!!trackedJobId} variant="playing" />
        <h1 className="text-2xl font-extrabold">تولید ویدیو</h1>
      </div>

      {config.isLoading && <LoadingSpinner label="در حال بارگذاری تنظیمات…" />}
      {config.isError && (
        <ErrorState message="بارگذاری تنظیمات ویدیو ناموفق بود." onRetry={() => config.refetch()} />
      )}

      {cfg && (
        <>
          {!cfg.model_available && (
            <ErrorState message="مدل تولید ویدیو فعال نیست. لطفاً بعداً تلاش کنید." />
          )}
          <form onSubmit={onSubmit} className="card flex flex-col gap-5" noValidate>
            {/* Prompt */}
            <div>
              <label htmlFor="vid-prompt" className="label">
                توضیح ویدیو (prompt)
              </label>
              <textarea
                id="vid-prompt"
                rows={3}
                placeholder="مثلاً: موج‌های اقیانوس در غروب آفتاب، نمای سینمایی"
                className={`input resize-none ${errors.prompt ? 'input-error' : ''}`}
                {...register('prompt')}
              />
              {errors.prompt && (
                <p role="alert" className="field-error">
                  {errors.prompt.message}
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4">
              {/* Duration */}
              <div>
                <label htmlFor="vid-seconds" className="label">
                  مدت ویدیو
                </label>
                <select id="vid-seconds" className="input" {...register('seconds', { valueAsNumber: true })}>
                  {durations.map((d) => (
                    <option key={d} value={d}>
                      {d.toLocaleString('fa-IR')} ثانیه
                    </option>
                  ))}
                </select>
              </div>

              {/* Aspect ratio */}
              <div>
                <label htmlFor="vid-size" className="label">
                  ابعاد
                </label>
                <select id="vid-size" className="input" {...register('size')}>
                  {sizes.map((s) => (
                    <option key={s.key} value={s.key}>
                      {SIZE_LABELS[s.key] ?? s.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Optional image for image-to-video */}
            <div>
              <label htmlFor="vid-image" className="label">
                تصویر (اختیاری - برای تولید ویدیو از روی تصویر)
              </label>
              <input
                id="vid-image"
                type="file"
                accept="image/*"
                onChange={handleImageChange}
                className="input"
              />
              {imageBase64 && (
                <p className="mt-1 text-xs text-green-600">تصویر انتخاب شد ✓</p>
              )}
            </div>

            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                type="submit"
                disabled={isSubmitting || createJob.isPending || !cfg.model_available}
                className="btn-primary flex-1"
              >
                {isSubmitting || createJob.isPending ? 'در حال ثبت…' : 'ثبت و تولید ویدیو'}
              </button>
            </div>
          </form>

          {/* Tracked job */}
          {trackedJobId && (
            <section aria-labelledby="vid-job-heading" aria-live="polite" className="card">
              <h2 id="vid-job-heading" className="text-lg font-bold">
                نتیجه تولید
              </h2>
              {trackedJob.isLoading && <LoadingSpinner label="در حال بررسی وضعیت…" />}
              {trackedJob.data && <VideoJobResult job={trackedJob.data} />}
            </section>
          )}

          {/* User's video history */}
          <section aria-label="ویدیوهای شما" className="flex flex-col gap-3">
            <h2 className="text-lg font-extrabold">ویدیوهای شما</h2>
            {history.isLoading && <LoadingSpinner label="در حال بارگذاری ویدیوها…" />}
            {history.isError && (
              <ErrorState message="بارگذاری ویدیوها ناموفق بود." onRetry={() => history.refetch()} />
            )}
            {history.data && doneVideos.length === 0 && (
              <EmptyState
                icon={Film}
                title="هنوز ویدیویی تولید نکرده‌اید"
                description="از فرم بالا اولین ویدیویتان را بسازید."
              />
            )}
            {doneVideos.length > 0 && (
              <>
                <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {doneVideos.map((job) => (
                    <li key={job.id} className="card group !p-2">
                      <button
                        type="button"
                        onClick={() => setViewingJob(job)}
                        className="relative block w-full overflow-hidden rounded-lg bg-neutral-100 dark:bg-navy-800"
                        style={{ aspectRatio: '16 / 9' }}
                        aria-label={`مشاهده ویدیو: ${job.prompt}`}
                      >
                        {job.result_url ? (
                          <video
                            src={job.result_url}
                            preload="metadata"
                            className="absolute inset-0 h-full w-full object-cover"
                          />
                        ) : (
                          <span className="absolute inset-0 flex items-center justify-center text-xs text-neutral-400">
                            {JOB_STATUS_META[job.status]?.label ?? job.status}
                          </span>
                        )}
                        {job.seconds != null && (
                          <span className="absolute bottom-2 right-2 rounded-full bg-black/60 px-2 py-0.5 text-xs text-white">
                            {Number(job.seconds).toLocaleString('fa-IR')} ثانیه
                          </span>
                        )}
                      </button>
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
            title="مشاهده ویدیو"
            onClose={() => setViewingJob(null)}
          >
            {viewingJob?.result_url && (
              <div className="flex flex-col gap-3">
                <video
                  src={viewingJob.result_url}
                  controls
                  playsInline
                  className="max-h-[70vh] w-full rounded-xl bg-neutral-100 dark:bg-navy-800"
                />
                <div className="rounded-xl bg-neutral-100 px-4 py-3 dark:bg-navy-800">
                  <PromptBox prompt={viewingJob.prompt} />
                </div>
                <a
                  href={viewingJob.result_url}
                  download
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn-primary w-full text-center"
                >
                  دانلود ویدیو
                </a>
              </div>
            )}
          </Modal>
        </>
      )}
    </div>
  );
}

function VideoJobResult({ job }: { job: VideoJob }) {
  const meta = JOB_STATUS_META[job.status];

  return (
    <div className="mt-3 flex flex-col gap-3">
      <p>
        وضعیت: <span className={meta.badge}>{meta.label}</span>
      </p>
      {(job.status === 'queued' || job.status === 'processing') && (
        <LoadingSpinner label="ویدیو در حال تولید است… این کار چند دقیقه طول می‌کشد." />
      )}
      {job.status === 'failed' && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          تولید ویدیو ناموفق بود. مبلغ رزروشده به کیف پول برگشت.
        </p>
      )}
      {job.status === 'succeeded' && job.result_url && (
        <>
          <div className="w-full overflow-hidden rounded-xl border border-neutral-200 dark:border-white/15">
            <video
              src={job.result_url}
              controls
              playsInline
              className="w-full bg-neutral-100 dark:bg-navy-800"
              style={{ aspectRatio: '16 / 9' }}
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-neutral-500 dark:text-slate-400">
            <span>{formatDateTime(job.created_at)}</span>
            <a href={job.result_url} download className="btn-secondary btn-sm" target="_blank" rel="noopener noreferrer">
              دانلود ویدیو
            </a>
          </div>
        </>
      )}
      {job.status === 'succeeded' && !job.result_url && (
        <EmptyState icon={Clapperboard} title="نتیجه‌ای ثبت نشده" description="ویدیویی برای این درخواست یافت نشد." />
      )}
    </div>
  );
}
