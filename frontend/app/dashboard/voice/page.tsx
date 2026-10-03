'use client';

import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAudioJob, useAudioJobs, useAssetDownloadUrl, useCreateAudioJob } from '@/features/voice/hooks';
import { useRecorder } from '@/features/voice/useRecorder';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { useToast } from '@/components/Toast';
import { NouraiMascot } from '@/components/NouraiMascot';
import { VoicePlayer } from '@/components/VoicePlayer';
import { ListeningVisualizer } from '@/components/ListeningVisualizer';
import { MicIcon } from '@/components/MicIcon';
import { formatDateTime, formatDuration } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { AudioJob } from '@/types/api';

const MAX_AUDIO_MB = 25;
const PAGE_SIZE = 50;

type Phase = 'idle' | 'listening' | 'thinking' | 'speaking';

const PHASE_LABEL: Record<Phase, string> = {
  idle: 'بزن و باهام حرف بزن',
  listening: 'گوش می‌دهم…',
  thinking: 'دارم فکر می‌کنم…',
  speaking: 'نورا داره جواب می‌ده…',
};

/** Interactive voice assistant: hold to talk -> STT -> reply -> TTS. */
export default function VoicePage() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);

  const [trackedJobId, setTrackedJobId] = useState<string | null>(null);
  const [lastDoneId, setLastDoneId] = useState<string | null>(null);
  const [voiceReply, setVoiceReply] = useState(true);
  const [speakingId, setSpeakingId] = useState<string | null>(null);

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
      { file },
      {
        onSuccess: (job) => {
          setLastDoneId(null);
          setTrackedJobId(job.id);
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

  const { recording, analyser, recSeconds, toggleRecording } = useRecorder(uploadFile);

  // Refresh the thread when the tracked job finishes; remember it for auto-play.
  useEffect(() => {
    const job = trackedJob.data;
    const status = job?.status;
    if (status === 'succeeded' || status === 'failed' || status === 'cancelled') {
      queryClient.invalidateQueries({ queryKey: ['audio', 'jobs'] });
      if (status === 'succeeded' && job) setLastDoneId(job.id);
      setTrackedJobId(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trackedJob.data?.status, queryClient]);

  // Assistant-mode jobs only: transcribe jobs live on the /dashboard/stt page.
  const items = [...(jobs.data?.items ?? [])].filter((j) => j.mode === 'assistant').reverse(); // oldest first, chat order
  const trackedVisible =
    trackedJobId && trackedJob.data && !items.some((j) => j.id === trackedJobId)
      ? trackedJob.data
      : null;
  const trackedProcessing =
    !!trackedVisible && (trackedVisible.status === 'queued' || trackedVisible.status === 'processing');

  const phase: Phase = recording
    ? 'listening'
    : trackedProcessing
      ? 'thinking'
      : speakingId
        ? 'speaking'
        : 'idle';

  const lastDone = lastDoneId ? items.find((j) => j.id === lastDoneId) : undefined;


  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold">نورا</h1>
        <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
          پاسخ صوتی
          <input
            type="checkbox"
            checked={voiceReply}
            onChange={(e) => setVoiceReply(e.target.checked)}
            className="peer sr-only"
          />
          <span className="relative h-6 w-11 shrink-0 rounded-full bg-neutral-300 transition peer-checked:bg-brand-500 dark:bg-neutral-700 after:absolute after:right-0.5 after:top-0.5 after:h-5 after:w-5 after:rounded-full after:bg-white after:shadow after:transition peer-checked:after:-translate-x-5" />
        </label>
      </div>

      {/* Hero: Nourai mascot + tap-to-talk */}
      <div className="flex flex-col items-center gap-4 py-2">
        <NouraiMascot mood={phase} className="h-52 w-52 drop-shadow-xl" />

        <p className="flex h-6 items-center gap-2 text-sm font-medium text-neutral-600 dark:text-slate-300" aria-live="polite">
          {phase === 'listening' && (
            <span className="font-bold tabular-nums text-red-500">{formatDuration(recSeconds)}</span>
          )}
          {PHASE_LABEL[phase]}
        </p>

        <div className="flex items-center justify-center gap-5">
          <button
            type="button"
            onClick={toggleRecording}
          disabled={createJob.isPending || !!trackedJobId}
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
            disabled={createJob.isPending || !!trackedJobId}
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
        <p className="-mt-3 text-xs text-neutral-500">
          {recording ? 'دوباره بزن تا بفرستم' : 'بزن و حرف بزن'}
        </p>
        {recording && analyser && (
          <div className="-mt-1 flex flex-col items-center gap-1" aria-hidden="true">
            <ListeningVisualizer analyser={analyser} />
            <p className="text-xs font-medium text-amber-600 dark:text-amber-400">دارم گوش می‌دهم…</p>
          </div>
        )}

      </div>

      {/* Auto-play this session's reply */}
      <ReplyAutoPlayer
        assetId={lastDone?.output_asset_id ?? null}
        jobId={lastDone?.id ?? null}
        enabled={voiceReply}
        onPlaying={setSpeakingId}
      />

      {/* Thread */}
      {jobs.isLoading && <LoadingSpinner label="در حال بارگذاری گفتگو…" />}
      {jobs.isError && <ErrorState message="بارگذاری گفتگو ناموفق بود." onRetry={() => jobs.refetch()} />}

      {jobs.data && items.length === 0 && !trackedVisible && phase === 'idle' && (
        <EmptyState
          icon="🎙️"
          title="هنوز گفتگویی ندارید"
          description="دکمه رو نگه دارید و با نورا حرف بزنید."
        />
      )}

      {(items.length > 0 || trackedVisible) && (
        <div className="flex flex-col gap-5" aria-live="polite">
          {items.map((job) => (
            <VoiceExchange key={job.id} job={job} />
          ))}
          {trackedVisible && <VoiceExchange job={trackedVisible} />}
        </div>
      )}
    </div>
  );
}

/** Auto-plays the reply audio of a freshly completed job (this session only). */
function ReplyAutoPlayer({
  assetId,
  jobId,
  enabled,
  onPlaying,
}: {
  assetId: string | null;
  jobId: string | null;
  enabled: boolean;
  onPlaying: (id: string | null) => void;
}) {
  const { data } = useAssetDownloadUrl(enabled ? assetId : null);
  const playedFor = useRef<string | null>(null);

  useEffect(() => {
    const url = data?.download_url;
    if (!enabled || !jobId || !url || playedFor.current === jobId) return;
    playedFor.current = jobId;
    const audio = new Audio(url);
    audio.onplay = () => onPlaying(jobId);
    const done = () => onPlaying(null);
    audio.onended = done;
    audio.onerror = done;
    audio.play().catch(() => onPlaying(null));
    return () => {
      audio.pause();
    };
  }, [data?.download_url, enabled, jobId, onPlaying]);

  return null;
}

/** One voice exchange: the user's audio bubble + Nourai's reply bubble. */
function VoiceExchange({ job }: { job: AudioJob }) {
  const processing = job.status === 'queued' || job.status === 'processing';
  return (
    <div className="flex flex-col gap-2">
      {/* User */}
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-bl-md bg-brand-600 px-4 py-3 text-white dark:bg-brand-500">
          <VoicePlayer assetId={job.input_asset_id} label="صدای شما" tone="dark" />
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
          <div className="card max-w-[75%] !p-4">
            {job.status === 'succeeded' ? (
              <>
                {job.reply_text && <p className="text-sm leading-7">{job.reply_text}</p>}
                <div className="mt-2">
                  <VoicePlayer assetId={job.output_asset_id} label="پاسخ صوتی نورا" tone="light" />
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
