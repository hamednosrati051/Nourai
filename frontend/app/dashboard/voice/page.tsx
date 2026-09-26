'use client';

import { useRef, useState } from 'react';
import { useCreateAudioJob, useAudioJob, useAudioJobs } from '@/features/voice/hooks';
import { useModels } from '@/features/models/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { Pagination } from '@/components/Pagination';
import { useToast } from '@/components/Toast';
import { formatDateTime, formatDuration } from '@/lib/format';
import { formatBytes } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { AudioJob, AudioJobStatus } from '@/types/api';

const MAX_AUDIO_MB = 25;

const STATUS_META: Record<AudioJobStatus, { label: string; badge: string }> = {
  queued: { label: 'در صف', badge: 'badge-neutral' },
  processing: { label: 'در حال پردازش', badge: 'badge-info' },
  succeeded: { label: 'موفق', badge: 'badge-success' },
  failed: { label: 'ناموفق', badge: 'badge-danger' },
};

/** Voice interaction: upload audio -> STT -> text model -> TTS reply, with job polling. */
export default function VoicePage() {
  const { toast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [trackedJobId, setTrackedJobId] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const models = useModels();
  const createJob = useCreateAudioJob();
  const trackedJob = useAudioJob(trackedJobId);
  const jobs = useAudioJobs(page);

  const audioModels = (models.data ?? []).filter(
    (m) => m.capability === 'speech_to_text' || m.capability === 'text_to_speech',
  );
  const [modelId, setModelId] = useState('');

  const onFileChange = (f: File | null) => {
    setFileError(null);
    if (!f) {
      setFile(null);
      return;
    }
    if (!f.type.startsWith('audio/')) {
      setFileError('فایل باید صوتی باشد.');
      setFile(null);
      return;
    }
    if (f.size > MAX_AUDIO_MB * 1024 * 1024) {
      setFileError(`حجم فایل نباید بیشتر از ${MAX_AUDIO_MB} مگابایت باشد.`);
      setFile(null);
      return;
    }
    setFile(f);
  };

  const submit = () => {
    if (!file) {
      setFileError('یک فایل صوتی انتخاب کنید.');
      return;
    }
    createJob.mutate(
      { file, modelId: modelId || undefined },
      {
        onSuccess: (job) => {
          setTrackedJobId(job.id);
          setFile(null);
          if (fileRef.current) fileRef.current.value = '';
          toast('فایل ارسال شد؛ پردازش آغاز شد.', 'success');
        },
        onError: (err) => {
          if (err instanceof ApiError && err.code === 'INSUFFICIENT_BALANCE') {
            toast('موجودی کافی نیست؛ لطفاً کیف پول را شارژ کنید.', 'error');
          } else {
            toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'ارسال فایل ناموفق بود.', 'error');
          }
        },
      },
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">تعامل صوتی</h1>

      {/* Upload card */}
      <section aria-labelledby="upload-heading" className="card">
        <h2 id="upload-heading" className="text-lg font-bold">
          ارسال صوت جدید
        </h2>
        <p className="mt-1 text-sm text-neutral-600 dark:text-slate-400">
          صدای شما به متن تبدیل می‌شود، مدل پاسخ می‌دهد و پاسخ به‌صورت صوتی برمی‌گردد.
        </p>

        <div className="mt-4 flex flex-col gap-4">
          <div>
            <label htmlFor="audio-file" className="label">
              فایل صوتی
            </label>
            <input
              id="audio-file"
              ref={fileRef}
              type="file"
              accept="audio/*"
              onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
              className="input cursor-pointer"
              aria-describedby="audio-hint"
            />
            <p id="audio-hint" className="field-hint">
              فرمت‌های صوتی رایج؛ حداکثر {MAX_AUDIO_MB} مگابایت.
            </p>
            {file && (
              <p className="mt-2 text-sm text-neutral-700 dark:text-slate-300">
                انتخاب‌شده: <span className="font-semibold">{file.name}</span> ({formatBytes(file.size)})
              </p>
            )}
            {fileError && (
              <p role="alert" className="field-error">
                {fileError}
              </p>
            )}
          </div>

          {audioModels.length > 0 && (
            <div>
              <label htmlFor="voice-model" className="label">
                مدل (اختیاری)
              </label>
              <select
                id="voice-model"
                className="input"
                value={modelId}
                onChange={(e) => setModelId(e.target.value)}
              >
                <option value="">پیش‌فرض</option>
                {audioModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.display_name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <button type="button" onClick={submit} disabled={createJob.isPending || !file} className="btn-primary w-full sm:w-auto">
            {createJob.isPending ? 'در حال ارسال…' : 'ارسال و پردازش'}
          </button>
        </div>
      </section>

      {/* Tracked job */}
      {trackedJobId && (
        <section aria-labelledby="job-heading" aria-live="polite" className="card">
          <h2 id="job-heading" className="text-lg font-bold">
            نتیجه پردازش
          </h2>
          {trackedJob.isLoading && <LoadingSpinner label="در حال بررسی وضعیت…" />}
          {trackedJob.data && <AudioJobResult job={trackedJob.data} />}
        </section>
      )}

      {/* History */}
      <section aria-labelledby="history-heading">
        <h2 id="history-heading" className="mb-3 text-lg font-bold">
          سوابق صوتی
        </h2>
        {jobs.isLoading && <LoadingSpinner />}
        {jobs.isError && <ErrorState message="بارگذاری سوابق ناموفق بود." onRetry={() => jobs.refetch()} />}
        {jobs.data && jobs.data.items.length === 0 && (
          <EmptyState icon="🎙️" title="سابقه‌ای نیست" description="هنوز فایل صوتی ارسال نکرده‌اید." />
        )}
        {jobs.data && jobs.data.items.length > 0 && (
          <>
            <ul className="flex flex-col gap-3">
              {jobs.data.items.map((job) => {
                const meta = STATUS_META[job.status];
                return (
                  <li key={job.id} className="card !p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className={meta.badge}>{meta.label}</span>
                      <span className="text-xs text-neutral-500 dark:text-slate-400">
                        {formatDateTime(job.created_at)}
                      </span>
                    </div>
                    {job.transcript && (
                      <p className="mt-2 text-sm">
                        <span className="font-semibold">متن استخراج‌شده: </span>
                        {job.transcript}
                      </p>
                    )}
                    {job.reply_text && (
                      <p className="mt-1 text-sm text-neutral-600 dark:text-slate-400">
                        <span className="font-semibold">پاسخ متنی: </span>
                        {job.reply_text}
                      </p>
                    )}
                    {job.reply_audio_url && (
                      <audio controls src={job.reply_audio_url} className="mt-3 w-full" aria-label="پاسخ صوتی" />
                    )}
                    {job.duration_seconds != null && (
                      <p className="mt-1 text-xs text-neutral-500">مدت: {formatDuration(job.duration_seconds)}</p>
                    )}
                    <button
                      type="button"
                      onClick={() => setTrackedJobId(job.id)}
                      className="inline-link mt-2 text-sm font-semibold text-brand-700 hover:underline dark:text-brand-400"
                    >
                      مشاهده جزئیات
                    </button>
                  </li>
                );
              })}
            </ul>
            <Pagination page={page} totalPages={jobs.data.meta.total_pages} totalItems={jobs.data.meta.total_items} onPageChange={setPage} />
          </>
        )}
      </section>
    </div>
  );
}

function AudioJobResult({ job }: { job: AudioJob }) {
  const meta = STATUS_META[job.status];

  return (
    <div className="mt-3 flex flex-col gap-3">
      <p>
        وضعیت: <span className={meta.badge}>{meta.label}</span>
      </p>
      {(job.status === 'queued' || job.status === 'processing') && (
        <LoadingSpinner label="در حال پردازش صوت… لطفاً صبر کنید." />
      )}
      {job.status === 'failed' && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          پردازش ناموفق بود. مبلغ رزروشده به کیف پول برگشت.
        </p>
      )}
      {job.status === 'succeeded' && (
        <>
          {job.transcript && (
            <div>
              <h3 className="text-sm font-bold">متن استخراج‌شده</h3>
              <p className="mt-1 rounded-xl bg-neutral-100 p-3 text-sm dark:bg-navy-800">{job.transcript}</p>
            </div>
          )}
          {job.reply_text && (
            <div>
              <h3 className="text-sm font-bold">پاسخ متنی</h3>
              <p className="mt-1 rounded-xl bg-neutral-100 p-3 text-sm dark:bg-navy-800">{job.reply_text}</p>
            </div>
          )}
          {job.reply_audio_url && (
            <div>
              <h3 className="text-sm font-bold">پاسخ صوتی</h3>
              <audio controls src={job.reply_audio_url} className="mt-2 w-full" aria-label="پاسخ صوتی" />
            </div>
          )}
        </>
      )}
    </div>
  );
}
