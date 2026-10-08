'use client';

import { Paperclip } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAudioJob, useAudioJobs, useAssetDownloadUrl, useCreateAudioJob, assetStreamUrl } from '@/features/voice/hooks';
import { useRecorder } from '@/features/voice/useRecorder';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { ErrorState } from '@/components/ErrorState';
import { useToast } from '@/components/Toast';
import { NouraAvatar } from '@/components/NouraAvatar';
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
  const composerFileRef = useRef<HTMLInputElement>(null);

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

  // Once the conversation starts the big hero collapses into a slim sticky bar.
  const hasThread = items.length > 0 || !!trackedVisible;

  // Keep the latest exchange in view as the thread grows.
  // The sticky bottom composer would cover the last item, so we add
  // bottom padding (via scroll-margin) and scroll the window to the
  // absolute bottom instead of relying on scrollIntoView.
  const threadEndRef = useRef<HTMLDivElement>(null);
  const prevThreadCount = useRef(0);
  useEffect(() => {
    const count = items.length + (trackedVisible ? 1 : 0);
    if (count > prevThreadCount.current) {
      // Wait for the new DOM to paint, then scroll to the very bottom.
      requestAnimationFrame(() => {
        window.scrollTo({
          top: document.documentElement.scrollHeight,
          behavior: 'smooth',
        });
      });
    }
    prevThreadCount.current = count;
  }, [items.length, trackedVisible]);

  const phase: Phase = recording
    ? 'listening'
    : trackedProcessing
      ? 'thinking'
      : speakingId
        ? 'speaking'
        : 'idle';

  const lastDone = lastDoneId ? items.find((j) => j.id === lastDoneId) : undefined;


  return (
    <div className="mx-auto flex min-h-[calc(100dvh-7rem)] w-full max-w-2xl flex-col">
      {/* Slim top bar once the conversation starts */}
      {hasThread && (
        <div className="sticky top-16 z-30 -mx-4 border-b border-neutral-200/70 bg-white/90 px-4 py-2 backdrop-blur sm:-mx-6 sm:px-6 dark:border-white/10 dark:bg-navy-950/90">
          <div className="flex items-center gap-3">
            <NouraAvatar working={phase === 'thinking'} className="h-10 w-10 shrink-0" />
            <p className="flex min-w-0 flex-1 items-center gap-2 text-sm font-medium text-neutral-600 dark:text-slate-300" aria-live="polite">
              {phase === 'listening' && (
                <span className="shrink-0 font-bold tabular-nums text-red-500">{formatDuration(recSeconds)}</span>
              )}
              <span className="truncate">{PHASE_LABEL[phase]}</span>
            </p>
            <label className="flex shrink-0 cursor-pointer items-center gap-2 text-xs font-medium text-neutral-500 dark:text-slate-400">
              پاسخ صوتی
              <input
                type="checkbox"
                checked={voiceReply}
                onChange={(e) => setVoiceReply(e.target.checked)}
                className="peer sr-only"
              />
              <span className="relative h-5 w-9 shrink-0 rounded-full bg-neutral-300 transition peer-checked:bg-brand-500 dark:bg-neutral-700 after:absolute after:right-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:bg-white after:shadow after:transition peer-checked:after:-translate-x-4" />
            </label>
          </div>
        </div>
      )}

      {/* Auto-play this session's reply */}
      <ReplyAutoPlayer
        assetId={lastDone?.output_asset_id ?? null}
        jobId={lastDone?.id ?? null}
        enabled={voiceReply}
        onPlaying={setSpeakingId}
      />

      {/* Thread */}
      <div className="flex flex-1 flex-col gap-5 py-4 pb-40" aria-live="polite">
        {jobs.isLoading && <LoadingSpinner label="در حال بارگذاری گفتگو…" />}
        {jobs.isError && <ErrorState message="بارگذاری گفتگو ناموفق بود." onRetry={() => jobs.refetch()} />}

        {jobs.data && items.length === 0 && !trackedVisible && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 py-10 text-center">
            <div className="relative">
              <span className="absolute -inset-6 rounded-full bg-amber-300/30 blur-2xl dark:bg-amber-400/15" aria-hidden="true" />
              <NouraAvatar working={false} className="relative h-40 w-40 shadow-xl" />
            </div>
            <p className="text-sm font-medium text-neutral-600 dark:text-slate-300" aria-live="polite">
              {PHASE_LABEL[phase]}
            </p>
            <p className="max-w-xs text-xs leading-6 text-neutral-500">
              دکمه میکروفون پایین رو بزن و با نورا حرف بزن؛ یا یه فایل صوتی پیوست کن.
            </p>
          </div>
        )}

        {items.map((job) => (
          <VoiceExchange key={job.id} job={job} />
        ))}
        {trackedVisible && <VoiceExchange job={trackedVisible} />}
        <div ref={threadEndRef} aria-hidden="true" />
      </div>

      {/* Bottom composer, ChatGPT-style */}
      <div className="sticky bottom-0 z-30 -mx-4 border-t border-neutral-200/70 bg-white/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6 dark:border-white/10 dark:bg-navy-950/95">
        {recording && analyser && (
          <div className="mb-2 flex justify-center" aria-hidden="true">
            <ListeningVisualizer analyser={analyser} />
          </div>
        )}
        <div className="flex items-center justify-center gap-4">
          <button
            type="button"
            onClick={() => composerFileRef.current?.click()}
            disabled={createJob.isPending || !!trackedJobId}
            aria-label="پیوست فایل صوتی"
            title="پیوست فایل صوتی"
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-neutral-300 bg-white text-neutral-800 shadow-md transition hover:scale-105 hover:bg-neutral-100 active:scale-95 disabled:opacity-50 dark:border-white/15 dark:bg-navy-800 dark:text-slate-100 dark:hover:bg-navy-700"
          >
            <Paperclip className="h-6 w-6" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={toggleRecording}
            disabled={createJob.isPending || !!trackedJobId}
            aria-label={recording ? 'توقف و ارسال' : 'شروع ضبط'}
            className={`relative flex h-16 w-16 select-none items-center justify-center rounded-full text-white shadow-xl transition-transform duration-150 ${
              recording
                ? 'scale-105 bg-gradient-to-br from-red-500 to-rose-600 shadow-red-500/40'
                : 'bg-gradient-to-br from-brand-500 to-amber-500 shadow-brand-500/40 hover:scale-105 active:scale-95'
            } disabled:opacity-50 disabled:hover:scale-100`}
          >
            {recording && <span className="absolute inset-0 animate-ping rounded-full bg-red-500/40" />}
            {recording ? (
              <svg viewBox="0 0 24 24" fill="currentColor" className="h-6 w-6" aria-hidden="true">
                <rect x="6" y="6" width="12" height="12" rx="3" />
              </svg>
            ) : (
              <MicIcon className="h-7 w-7" />
            )}
          </button>
          <span className="h-12 w-12 shrink-0" aria-hidden="true" />
        </div>
        <p className="mt-2 text-center text-xs text-neutral-500">
          {recording ? (
            <>
              در حال ضبط <span className="font-bold tabular-nums text-red-500">{formatDuration(recSeconds)}</span>
              {' '}— دوباره بزن تا بفرستم
            </>
          ) : (
            'بزن و حرف بزن'
          )}
        </p>
        <input
          ref={composerFileRef}
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
    const url = assetId ? assetStreamUrl(assetId) : data?.download_url;
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
