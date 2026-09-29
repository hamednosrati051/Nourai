'use client';

import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAudioJob, useAudioJobs, useAssetDownloadUrl, useCreateAudioJob } from '@/features/voice/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { useToast } from '@/components/Toast';
import { formatDateTime, formatDuration } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { AudioJob } from '@/types/api';

const MAX_AUDIO_MB = 25;
const PAGE_SIZE = 50;

/** Chat-like voice interaction: mic recording / audio upload -> STT -> reply -> TTS. */
export default function VoicePage() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const [trackedJobId, setTrackedJobId] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);
  const [recSeconds, setRecSeconds] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const jobs = useAudioJobs(1, PAGE_SIZE);
  const createJob = useCreateAudioJob();
  const trackedJob = useAudioJob(trackedJobId);

  // Refresh the thread when the tracked job finishes.
  useEffect(() => {
    const status = trackedJob.data?.status;
    if (status === 'succeeded' || status === 'failed' || status === 'cancelled') {
      queryClient.invalidateQueries({ queryKey: ['audio', 'jobs'] });
      setTrackedJobId(null);
    }
  }, [trackedJob.data?.status, queryClient]);

  const items = [...(jobs.data?.items ?? [])].reverse(); // oldest first, chat order
  const trackedVisible =
    trackedJobId && trackedJob.data && !items.some((j) => j.id === trackedJobId)
      ? trackedJob.data
      : null;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [items.length, trackedVisible?.id, trackedVisible?.status]);

  // Recording timer.
  useEffect(() => {
    if (recording) {
      setRecSeconds(0);
      timerRef.current = setInterval(() => setRecSeconds((s) => s + 1), 1000);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [recording]);

  const uploadFile = (file: File) => {
    if (!file.type.startsWith('audio/')) {
      toast('فایل باید صوتی باشد.', 'error');
      return;
    }
    if (file.size > MAX_AUDIO_MB * 1024 * 1024) {
      toast(`حجم فایل نباید بیشتر از ${MAX_AUDIO_MB} مگابایت باشد.`, 'error');
      return;
    }
    createJob.mutate(
      { file },
      {
        onSuccess: (job) => {
          setTrackedJobId(job.id);
          toast('صوت ارسال شد؛ پردازش آغاز شد.', 'success');
        },
        onError: (err) => {
          if (err instanceof ApiError && err.code === 'INSUFFICIENT_BALANCE') {
            toast('موجودی کافی نیست؛ لطفاً کیف پول را شارژ کنید.', 'error');
          } else {
            toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'ارسال صوت ناموفق بود.', 'error');
          }
        },
      },
    );
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || 'audio/webm' });
        if (blob.size > 0) {
          uploadFile(new File([blob], `recording-${Date.now()}.webm`, { type: blob.type }));
        }
      };
      rec.start();
      mediaRecorderRef.current = rec;
      setRecording(true);
    } catch {
      toast('دسترسی به میکروفن ممکن نشد. لطفاً اجازه میکروفن را بدهید.', 'error');
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
    setRecording(false);
  };

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-extrabold">تبدیل صوت به متن</h1>

      {jobs.isLoading && <LoadingSpinner label="در حال بارگذاری گفتگو…" />}
      {jobs.isError && <ErrorState message="بارگذاری گفتگو ناموفق بود." onRetry={() => jobs.refetch()} />}

      {jobs.data && items.length === 0 && !trackedVisible && (
        <EmptyState
          icon="🎙️"
          title="هنوز گفتگویی ندارید"
          description="با دکمه میکروفن صحبت کنید یا یک فایل صوتی بفرستید؛ نورا گوش می‌دهد، جواب می‌دهد و جواب را می‌خواند."
        />
      )}

      {(items.length > 0 || trackedVisible) && (
        <div className="flex flex-col gap-5" aria-live="polite">
          {items.map((job) => (
            <VoiceExchange key={job.id} job={job} />
          ))}
          {trackedVisible && <VoiceExchange job={trackedVisible} />}
          <div ref={bottomRef} />
        </div>
      )}

      {/* Composer */}
      <div className="sticky bottom-0 -mx-2 border-t border-neutral-200 bg-white/90 p-4 backdrop-blur dark:border-white/10 dark:bg-slate-950/90">
        {recording ? (
          <div className="flex items-center justify-center gap-4" role="status" aria-label="در حال ضبط">
            <span className="relative flex h-3 w-3">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-500 opacity-75" />
              <span className="relative inline-flex h-3 w-3 rounded-full bg-red-600" />
            </span>
            <span className="font-bold tabular-nums">{formatDuration(recSeconds)}</span>
            <button type="button" onClick={stopRecording} className="btn-danger rounded-full px-8 py-3">
              ⏹ توقف و ارسال
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={startRecording}
              disabled={createJob.isPending}
              className="btn-primary rounded-full px-8 py-4 text-lg"
              aria-label="شروع ضبط صدا"
            >
              🎙️ شروع ضبط
            </button>
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={createJob.isPending}
              className="btn-secondary rounded-full px-6 py-4"
              aria-label="ارسال فایل صوتی"
            >
              📎 فایل صوتی
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="audio/*"
              className="hidden"
              aria-hidden="true"
              tabIndex={-1}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) uploadFile(f);
                e.target.value = '';
              }}
            />
          </div>
        )}
        {createJob.isPending && (
          <p className="mt-2 text-center text-sm text-neutral-500">در حال ارسال صوت…</p>
        )}
      </div>
    </div>
  );
}

/** One voice exchange: the user's audio bubble + Nourai's reply bubble. */
function VoiceExchange({ job }: { job: AudioJob }) {
  const processing = job.status === 'queued' || job.status === 'processing';
  return (
    <div className="flex flex-col gap-2">
      {/* User */}
      <div className="flex justify-end">
        <div className="max-w-[88%] rounded-2xl rounded-bl-md bg-brand-600 px-4 py-3 text-white dark:bg-brand-500">
          <JobAudio assetId={job.input_asset_id} label="صدای شما" />
          {processing && !job.transcript && (
            <p className="mt-2 text-sm opacity-90">در حال پردازش صدا…</p>
          )}
          {job.transcript && <p className="mt-2 text-sm leading-7">{job.transcript}</p>}
          <p className="mt-1 text-left text-[11px] opacity-70">{formatDateTime(job.created_at)}</p>
        </div>
      </div>
      {/* Nourai */}
      {!processing && (
        <div className="flex justify-start">
          <div className="card max-w-[88%] !p-4">
            {job.status === 'succeeded' ? (
              <>
                {job.reply_text && <p className="text-sm leading-7">{job.reply_text}</p>}
                <div className="mt-2">
                  <JobAudio assetId={job.output_asset_id} label="پاسخ صوتی نورا" />
                </div>
              </>
            ) : (
              <p className="text-sm text-red-600 dark:text-red-400">
                {job.status === 'cancelled'
                  ? 'این پردازش لغو شد.'
                  : job.error_message || 'پردازش صوت ناموفق بود.'}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/** Audio player backed by a signed asset download URL. */
function JobAudio({ assetId, label }: { assetId: string | null; label: string }) {
  const { data, isLoading } = useAssetDownloadUrl(assetId);
  if (!assetId) return null;
  if (isLoading) return <span className="text-xs opacity-80">در حال آماده‌سازی صوت…</span>;
  if (!data?.download_url) return null;
  return <audio controls src={data.download_url} className="w-full min-w-52" aria-label={label} />;
}
