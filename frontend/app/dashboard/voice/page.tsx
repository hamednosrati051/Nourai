'use client';

import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useAudioJob, useAudioJobs, useAssetDownloadUrl, useCreateAudioJob } from '@/features/voice/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { useToast } from '@/components/Toast';
import { NouraiMascot } from '@/components/NouraiMascot';
import { formatDateTime, formatDuration } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { AudioJob } from '@/types/api';

const MAX_AUDIO_MB = 25;
const PAGE_SIZE = 50;

type Phase = 'idle' | 'listening' | 'thinking' | 'speaking';

const PHASE_LABEL: Record<Phase, string> = {
  idle: 'دکمه رو نگه دار و باهام حرف بزن',
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
  const [holding, setHolding] = useState(false);
  const [recSeconds, setRecSeconds] = useState(0);
  const [voiceReply, setVoiceReply] = useState(true);
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const holdingRef = useRef(false);

  const jobs = useAudioJobs(1, PAGE_SIZE);
  const createJob = useCreateAudioJob();
  const trackedJob = useAudioJob(trackedJobId);

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

  const items = [...(jobs.data?.items ?? [])].reverse(); // oldest first, chat order
  const trackedVisible =
    trackedJobId && trackedJob.data && !items.some((j) => j.id === trackedJobId)
      ? trackedJob.data
      : null;
  const trackedProcessing =
    !!trackedVisible && (trackedVisible.status === 'queued' || trackedVisible.status === 'processing');

  const phase: Phase = holding
    ? 'listening'
    : trackedProcessing
      ? 'thinking'
      : speakingId
        ? 'speaking'
        : 'idle';

  const lastDone = lastDoneId ? items.find((j) => j.id === lastDoneId) : undefined;

  // Recording timer.
  useEffect(() => {
    if (holding) {
      setRecSeconds(0);
      timerRef.current = setInterval(() => setRecSeconds((s) => s + 1), 1000);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [holding]);

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

  const beginCapture = async () => {
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
    } catch {
      holdingRef.current = false;
      setHolding(false);
      toast('دسترسی به میکروفن ممکن نشد. لطفاً اجازه میکروفن را بدهید.', 'error');
    }
  };

  const finishCapture = () => {
    mediaRecorderRef.current?.stop();
    mediaRecorderRef.current = null;
  };

  const onHoldStart = (e: React.PointerEvent) => {
    e.preventDefault();
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    if (createJob.isPending || trackedJobId || holdingRef.current) return;
    holdingRef.current = true;
    setHolding(true);
    beginCapture();
  };

  const onHoldEnd = () => {
    if (!holdingRef.current) return;
    holdingRef.current = false;
    setHolding(false);
    finishCapture();
  };

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      <h1 className="text-center text-2xl font-extrabold">تعامل صوتی</h1>

      {/* Hero: Nourai mascot + hold-to-talk */}
      <div className="flex flex-col items-center gap-4 py-2">
        <NouraiMascot mood={phase} className="h-52 w-52 drop-shadow-xl" />

        <p className="flex h-6 items-center gap-2 text-sm font-medium text-neutral-600 dark:text-slate-300" aria-live="polite">
          {phase === 'listening' && (
            <span className="font-bold tabular-nums text-red-500">{formatDuration(recSeconds)}</span>
          )}
          {PHASE_LABEL[phase]}
        </p>

        <button
          type="button"
          onPointerDown={onHoldStart}
          onPointerUp={onHoldEnd}
          onPointerLeave={onHoldEnd}
          onPointerCancel={onHoldEnd}
          onContextMenu={(e) => e.preventDefault()}
          disabled={createJob.isPending || !!trackedJobId}
          aria-label="نگه دار و صحبت کن"
          className={`relative flex h-24 w-24 touch-none select-none items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-amber-500 text-white shadow-xl shadow-brand-500/40 transition-transform duration-150 ${holding ? 'scale-110' : 'hover:scale-105 active:scale-105'} disabled:opacity-50 disabled:hover:scale-100`}
        >
          {holding && <span className="absolute inset-0 animate-ping rounded-full bg-red-500/40" />}
          <MicIcon className="h-10 w-10" />
        </button>
        <p className="-mt-3 text-xs text-neutral-500">نگه دار، حرف بزن، ول کن</p>

        <div className="flex items-center gap-5">
          <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
            <input
              type="checkbox"
              checked={voiceReply}
              onChange={(e) => setVoiceReply(e.target.checked)}
              className="peer sr-only"
            />
            <span className="relative h-6 w-11 shrink-0 rounded-full bg-neutral-300 transition peer-checked:bg-brand-500 dark:bg-neutral-700 after:absolute after:right-0.5 after:top-0.5 after:h-5 after:w-5 after:rounded-full after:bg-white after:shadow after:transition peer-checked:after:-translate-x-5" />
            پاسخ صوتی نورا
          </label>
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={createJob.isPending || !!trackedJobId}
            className="btn-secondary rounded-full px-5 py-2.5 text-sm font-bold disabled:opacity-50"
          >
            📎 ارسال فایل صوتی
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

function MicIcon({ className = 'h-14 w-14 text-white' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <rect x="9" y="2" width="6" height="12" rx="3" />
      <path d="M5 10a7 7 0 0 0 14 0" />
      <path d="M12 17v4" />
      <path d="M8 21h8" />
    </svg>
  );
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

/** Pretty custom audio player: play/pause, seekable progress, time, download. */
function VoicePlayer({
  assetId,
  label,
  tone,
}: {
  assetId: string | null;
  label: string;
  tone: 'dark' | 'light';
}) {
  const { data, isLoading } = useAssetDownloadUrl(assetId);
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [downloading, setDownloading] = useState(false);
  const url = data?.download_url;

  const toggle = () => {
    const a = audioRef.current;
    if (!a) return;
    if (playing) a.pause();
    else a.play().catch(() => {});
  };

  const seek = (e: React.MouseEvent<HTMLDivElement>) => {
    const a = audioRef.current;
    if (!a || !duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    a.currentTime = ratio * duration;
    setCurrent(a.currentTime);
  };

  const download = async () => {
    if (!url || !assetId || downloading) return;
    setDownloading(true);
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error('fetch failed');
      const blob = await res.blob();
      const ext = blob.type.includes('webm') ? 'webm' : 'mp3';
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `nourai-voice-${assetId.slice(0, 8)}.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 5000);
    } catch {
      window.open(url, '_blank', 'noopener');
    } finally {
      setDownloading(false);
    }
  };

  if (!assetId) return null;
  if (isLoading || !url) {
    return <span className="text-xs opacity-80">در حال آماده‌سازی صوت…</span>;
  }

  const dark = tone === 'dark';
  const pct = duration > 0 ? (current / duration) * 100 : 0;

  return (
    <div className="flex items-center gap-2" dir="ltr">
      <audio
        ref={audioRef}
        src={url}
        preload="metadata"
        aria-label={label}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => {
          setPlaying(false);
          setCurrent(0);
        }}
        onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration || 0)}
      />
      <button
        type="button"
        onClick={toggle}
        aria-label={playing ? 'توقف' : 'پخش'}
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white shadow transition hover:scale-105 active:scale-95 ${
          dark ? 'bg-white/25 hover:bg-white/35' : 'bg-gradient-to-br from-brand-500 to-amber-500 shadow-brand-500/30'
        }`}
      >
        {playing ? (
          <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4" aria-hidden="true">
            <rect x="6" y="5" width="4" height="14" rx="1.5" />
            <rect x="14" y="5" width="4" height="14" rx="1.5" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="currentColor" className="ml-0.5 h-4 w-4" aria-hidden="true">
            <path d="M8 5.5v13a1.5 1.5 0 0 0 2.3 1.27l10-6.5a1.5 1.5 0 0 0 0-2.54l-10-6.5A1.5 1.5 0 0 0 8 5.5Z" />
          </svg>
        )}
      </button>
      <div
        role="slider"
        aria-label="پیشرفت پخش"
        aria-valuemin={0}
        aria-valuemax={Math.round(duration)}
        aria-valuenow={Math.round(current)}
        onClick={seek}
        className={`relative h-1.5 flex-1 cursor-pointer rounded-full ${dark ? 'bg-white/25' : 'bg-neutral-200 dark:bg-white/15'}`}
      >
        <div
          className={`absolute inset-y-0 left-0 rounded-full ${dark ? 'bg-white' : 'bg-gradient-to-r from-brand-500 to-amber-500'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`shrink-0 text-[11px] tabular-nums ${dark ? 'text-white/85' : 'text-neutral-500 dark:text-slate-400'}`}>
        {fmtTime(current)} / {fmtTime(duration)}
      </span>
      <button
        type="button"
        onClick={download}
        disabled={downloading}
        aria-label="دانلود فایل صوتی"
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition hover:scale-105 active:scale-95 disabled:opacity-50 ${
          dark ? 'bg-white/20 text-white hover:bg-white/30' : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200 dark:bg-white/10 dark:text-slate-200 dark:hover:bg-white/20'
        }`}
      >
        {downloading ? (
          <span className="text-xs">…</span>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
            <path d="M12 3v12" />
            <path d="m7 11 5 5 5-5" />
            <path d="M4 21h16" />
          </svg>
        )}
      </button>
    </div>
  );
}

function fmtTime(s: number): string {
  if (!isFinite(s) || s < 0) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}
