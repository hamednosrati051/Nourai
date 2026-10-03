'use client';

import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAudioJob, useAudioJobs, useCreateAudioJob } from '@/features/voice/hooks';
import { useRecorder } from '@/features/voice/useRecorder';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { ListeningVisualizer } from '@/components/ListeningVisualizer';
import { MicIcon } from '@/components/MicIcon';
import { VoicePlayer } from '@/components/VoicePlayer';
import { Modal } from '@/components/Modal';
import { useToast } from '@/components/Toast';
import { formatDateTime, formatDuration } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { AudioJob } from '@/types/api';

const MAX_AUDIO_MB = 25;
const PAGE_SIZE = 50;

/** Standalone speech-to-text: record/upload -> transcript only (no reply, no TTS). */
export default function SttPage() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [trackedJobId, setTrackedJobId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);

  const jobs = useAudioJobs(1, PAGE_SIZE);
  const createJob = useCreateAudioJob();
  const trackedJob = useAudioJob(trackedJobId);

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
      { file, mode: 'transcribe' },
      {
        onSuccess: (job) => setTrackedJobId(job.id),
        onError: (err) => {
          if (err instanceof ApiError && err.code === 'INSUFFICIENT_BALANCE') {
            toast('موجودی کافی نیست؛ لطفاً کیف پول را شارژ کنید.', 'error');
          } else if (err instanceof ApiError && err.code === 'MODEL_UNAVAILABLE') {
            toast('مدل صوت‌به‌متن فعالی تعریف نشده است.', 'error');
          } else if (err instanceof ApiError && err.code === 'PRICING_RULE_UNAVAILABLE') {
            toast('تعرفه مدل صوتی تعریف نشده است.', 'error');
          } else {
            toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'ارسال صوت ناموفق بود.', 'error');
          }
        },
      },
    );
  };

  const { recording, analyser, recSeconds, toggleRecording } = useRecorder(uploadFile);

  // Refresh the list when the tracked job finishes.
  useEffect(() => {
    const status = trackedJob.data?.status;
    if (status === 'succeeded' || status === 'failed' || status === 'cancelled') {
      queryClient.invalidateQueries({ queryKey: ['audio', 'jobs'] });
      setTrackedJobId(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trackedJob.data?.status, queryClient]);

  // Newest first; only transcribe-mode jobs belong to this page.
  const items = (jobs.data?.items ?? []).filter((j) => j.mode === 'transcribe');
  const tracked = trackedJobId && trackedJob.data ? trackedJob.data : null;
  const trackedProcessing =
    !!tracked && (tracked.status === 'queued' || tracked.status === 'processing');
  const latestDone = items.find((j) => j.status === 'succeeded');

  const copyTranscript = async (job: AudioJob) => {
    if (!job.transcript) return;
    try {
      await navigator.clipboard.writeText(job.transcript);
      setCopiedId(job.id);
      setTimeout(() => setCopiedId((id) => (id === job.id ? null : id)), 1500);
    } catch {
      toast('کپی ناموفق بود.', 'error');
    }
  };

  const busy = createJob.isPending || !!trackedJobId;

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold">تبدیل صوت به متن</h1>
        <button type="button" onClick={() => setHistoryOpen(true)} className="btn-secondary btn-sm">
          🕘 تاریخچه
        </button>
      </div>

      {/* Recorder */}
      <div className="flex flex-col items-center gap-4 py-2">
        <div className="flex items-center justify-center gap-5">
          <button
            type="button"
            onClick={toggleRecording}
            disabled={busy}
            aria-label={recording ? 'توقف و ارسال' : 'شروع ضبط'}
            className={`relative flex h-24 w-24 select-none items-center justify-center rounded-full text-white shadow-xl transition-transform duration-150 ${
              recording
                ? 'scale-105 bg-gradient-to-br from-red-500 to-rose-600 shadow-red-500/40'
                : 'bg-gradient-to-br from-brand-500 to-amber-500 shadow-brand-500/40 hover:scale-105 active:scale-105'
            } disabled:opacity-50 disabled:hover:scale-100`}
          >
            {recording && <span className="absolute inset-0 animate-ping rounded-full bg-red-500/40" />}
            {recording ? (
              <svg viewBox="0 0 24 24" fill="currentColor" className="h-9 w-9" aria-hidden="true">
                <rect x="6" y="6" width="12" height="12" rx="3" />
              </svg>
            ) : (
              <MicIcon className="h-10 w-10" />
            )}
          </button>
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            aria-label="ارسال فایل صوتی"
            title="ارسال فایل صوتی"
            className="btn-secondary flex h-14 w-14 shrink-0 items-center justify-center rounded-full text-xl shadow-md transition hover:scale-105 active:scale-95 disabled:opacity-50"
          >
            📎
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
        <p className="-mt-3 flex h-6 items-center gap-2 text-xs text-neutral-500" aria-live="polite">
          {recording && (
            <span className="font-bold tabular-nums text-red-500">{formatDuration(recSeconds)}</span>
          )}
          {recording ? 'دوباره بزن تا بفرستم' : 'بزن و حرف بزن، یا فایل صوتی بفرست'}
        </p>
        {recording && analyser && (
          <div className="-mt-1 flex flex-col items-center gap-1" aria-hidden="true">
            <ListeningVisualizer analyser={analyser} />
            <p className="text-xs font-medium text-amber-600 dark:text-amber-400">دارم گوش می‌دهم…</p>
          </div>
        )}
        {createJob.isPending && (
          <p className="text-sm text-neutral-500">در حال ارسال صوت…</p>
        )}
      </div>

      {/* Live status */}
      {trackedProcessing && <LoadingSpinner label="در حال رونویسی…" />}
      {tracked && tracked.status === 'failed' && (
        <p className="card !p-4 text-sm text-red-600 dark:text-red-400">
          {tracked.error_message || 'رونویسی ناموفق بود.'}
        </p>
      )}

      {/* Latest transcript */}
      {!tracked && latestDone && (
        <div className="card !p-5" aria-live="polite">
          <h2 className="mb-2 font-bold">آخرین رونویسی</h2>
          <SttResult job={latestDone} copiedId={copiedId} onCopy={copyTranscript} />
        </div>
      )}

      {/* History */}
      <Modal open={historyOpen} title="تاریخچه تبدیل صوت به متن" onClose={() => setHistoryOpen(false)} maxWidth="max-w-2xl">
        <div className="flex max-h-[70vh] flex-col gap-3 overflow-y-auto">
          {jobs.isLoading && <LoadingSpinner label="در حال بارگذاری تاریخچه…" />}
          {jobs.isError && <ErrorState message="بارگذاری تاریخچه ناموفق بود." onRetry={() => jobs.refetch()} />}
          {jobs.data && items.length === 0 && (
            <EmptyState
              icon="📝"
              title="هنوز رونویسی ندارید"
              description="با دکمه میکروفن ضبط کنید یا یک فایل صوتی بفرستید."
            />
          )}
          {items.map((job) => (
            <div key={job.id} className="card flex flex-col gap-2 !p-4">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs text-neutral-500">{formatDateTime(job.created_at)}</span>
                {job.transcript && (
                  <button
                    type="button"
                    onClick={() => copyTranscript(job)}
                    className="btn-secondary btn-sm"
                  >
                    {copiedId === job.id ? '✓ کپی شد' : '📋 کپی متن'}
                  </button>
                )}
              </div>
              {job.status === 'succeeded' ? (
                <>
                  <p className="text-sm leading-7">{job.transcript || '—'}</p>
                  <VoicePlayer assetId={job.input_asset_id} label="صدای ارسالی" tone="light" />
                </>
              ) : job.status === 'failed' || job.status === 'cancelled' ? (
                <p className="text-sm text-red-600 dark:text-red-400">
                  {job.status === 'cancelled' ? 'لغو شد.' : job.error_message || 'رونویسی ناموفق بود.'}
                </p>
              ) : (
                <p className="text-sm text-neutral-500">در حال رونویسی…</p>
              )}
            </div>
          ))}
        </div>
      </Modal>
    </div>
  );
}

function SttResult({
  job,
  copiedId,
  onCopy,
}: {
  job: AudioJob;
  copiedId: string | null;
  onCopy: (job: AudioJob) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm leading-7">{job.transcript || '—'}</p>
        {job.transcript && (
          <button type="button" onClick={() => onCopy(job)} className="btn-secondary btn-sm shrink-0">
            {copiedId === job.id ? '✓ کپی شد' : '📋 کپی متن'}
          </button>
        )}
      </div>
      <VoicePlayer assetId={job.input_asset_id} label="صدای ارسالی" tone="light" />
    </div>
  );
}
