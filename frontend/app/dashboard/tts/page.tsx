'use client';

import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { TTS_MAX_CHARS, useCreateTtsJob, useTtsJob, useTtsJobs } from '@/features/tts/hooks';
import { useAssetDownloadUrl } from '@/features/voice/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { Modal } from '@/components/Modal';
import { useToast } from '@/components/Toast';
import { formatDateTime } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { TtsJob } from '@/types/api';

const TTS_STATUS_LABEL: Record<string, string> = {
  queued: 'در صف',
  processing: 'در حال تبدیل…',
  succeeded: 'آماده',
  failed: 'ناموفق',
  cancelled: 'لغوشده',
};

/** Standalone text-to-speech: type text -> convert -> play + history. */
export default function TtsPage() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [text, setText] = useState('');
  const [trackedJobId, setTrackedJobId] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const resultRef = useRef<HTMLDivElement>(null);

  const jobs = useTtsJobs(1, 20);
  const createJob = useCreateTtsJob();
  const trackedJob = useTtsJob(trackedJobId);

  useEffect(() => {
    const status = trackedJob.data?.status;
    if (status === 'succeeded' || status === 'failed' || status === 'cancelled') {
      queryClient.invalidateQueries({ queryKey: ['tts', 'jobs'] });
      setTrackedJobId(null);
      resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [trackedJob.data?.status, queryClient]);

  const tracked = trackedJobId && trackedJob.data ? trackedJob.data : null;
  const items = jobs.data?.items ?? [];
  const latestDone = items.find((j) => j.status === 'succeeded');

  const submit = () => {
    const value = text.trim();
    if (!value) {
      toast('اول متن را بنویسید.', 'error');
      return;
    }
    if (value.length > TTS_MAX_CHARS) {
      toast(`متن نباید بیشتر از ${TTS_MAX_CHARS} کاراکتر باشد.`, 'error');
      return;
    }
    createJob.mutate(
      { text: value },
      {
        onSuccess: (job) => {
          setTrackedJobId(job.id);
          setText('');
        },
        onError: (err) => {
          if (err instanceof ApiError && err.code === 'INSUFFICIENT_BALANCE') {
            toast('موجودی کافی نیست؛ لطفاً کیف پول را شارژ کنید.', 'error');
          } else if (err instanceof ApiError && err.code === 'MODEL_UNAVAILABLE') {
            toast('مدل تبدیل متن به صوت فعالی تعریف نشده است.', 'error');
          } else if (err instanceof ApiError && err.code === 'PRICING_RULE_UNAVAILABLE') {
            toast('تعرفه مدل صوتی تعریف نشده است.', 'error');
          } else {
            toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'تبدیل ناموفق بود.', 'error');
          }
        },
      },
    );
  };

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold">تبدیل متن به صوت</h1>
        <button type="button" onClick={() => setHistoryOpen(true)} className="btn-secondary btn-sm">
          🕘 تاریخچه
        </button>
      </div>

      <div className="card !p-5">
        <label htmlFor="tts-text" className="label">
          متن ورودی
        </label>
        <textarea
          id="tts-text"
          className="input min-h-36"
          placeholder="متن خود را وارد کنید..."
          value={text}
          maxLength={TTS_MAX_CHARS + 100}
          onChange={(e) => setText(e.target.value)}
          aria-describedby="tts-count"
        />
        <p id="tts-count" className="mt-1 text-left text-xs text-neutral-500">
          {text.length} / {TTS_MAX_CHARS}
        </p>
        <button
          type="button"
          onClick={submit}
          disabled={createJob.isPending || !!tracked}
          className="btn-primary mt-3 w-full rounded-full py-4 text-lg"
        >
          {createJob.isPending ? 'در حال ارسال…' : tracked ? 'در حال تبدیل…' : '🔊 تبدیل به صوت'}
        </button>
      </div>

      {tracked && (
        <div ref={resultRef} className="card !p-5" aria-live="polite">
          <TtsResult job={tracked} />
        </div>
      )}

      {!tracked && latestDone && (
        <div className="card !p-5" aria-live="polite">
          <h2 className="mb-2 font-bold">آخرین تبدیل</h2>
          <TtsResult job={latestDone} />
        </div>
      )}

      <Modal open={historyOpen} title="تاریخچه تبدیل متن به صوت" onClose={() => setHistoryOpen(false)} maxWidth="max-w-2xl">
        <div className="flex max-h-[70vh] flex-col gap-3 overflow-y-auto">
        {jobs.isLoading && <LoadingSpinner label="در حال بارگذاری تاریخچه…" />}
        {jobs.isError && <ErrorState message="بارگذاری تاریخچه ناموفق بود." onRetry={() => jobs.refetch()} />}
        {jobs.data && items.length === 0 && (
          <EmptyState
            icon="🔊"
            title="هنوز متنی تبدیل نکرده‌اید"
            description="متن را بنویسید و دکمه تبدیل را بزنید."
          />
        )}
        {items.map((job) => (
          <div key={job.id} className="card flex flex-col gap-2 !p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="badge-neutral badge">{TTS_STATUS_LABEL[job.status] ?? job.status}</span>
              <span className="flex items-center gap-2">
                <span className="text-xs text-neutral-500">{formatDateTime(job.created_at)}</span>
              </span>
            </div>
            <p className="line-clamp-2 text-sm">{job.text}</p>
            <TtsAudio assetId={job.output_asset_id} />
            {job.status === 'failed' && (
              <p className="text-sm text-red-600 dark:text-red-400">
                {job.error_message || 'تبدیل ناموفق بود.'}
              </p>
            )}
          </div>
        ))}
        </div>
      </Modal>
    </div>
  );
}

function TtsResult({ job }: { job: TtsJob }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="line-clamp-3 text-sm">{job.text}</p>
      {job.status === 'succeeded' ? (
        <TtsAudio assetId={job.output_asset_id} />
      ) : job.status === 'failed' ? (
        <p className="text-sm text-red-600 dark:text-red-400">
          {job.error_message || 'تبدیل ناموفق بود.'}
        </p>
      ) : (
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm text-neutral-500">{TTS_STATUS_LABEL[job.status] ?? job.status}</p>
        </div>
      )}
    </div>
  );
}

function TtsAudio({ assetId }: { assetId: string | null }) {
  const { data, isLoading } = useAssetDownloadUrl(assetId);
  const [downloading, setDownloading] = useState(false);
  if (!assetId) return null;
  if (isLoading) return <span className="text-xs text-neutral-500">در حال آماده‌سازی صوت…</span>;
  if (!data?.download_url) return null;

  const download = async () => {
    setDownloading(true);
    try {
      const res = await fetch(data.download_url);
      if (!res.ok) throw new Error('fetch failed');
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `nourai-tts-${assetId.slice(0, 8)}.mp3`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(blobUrl), 5000);
    } catch {
      window.open(data.download_url, '_blank', 'noopener');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <audio controls src={data.download_url} className="w-full" aria-label="فایل صوتی" />
      <button
        type="button"
        onClick={download}
        disabled={downloading}
        className="btn-secondary btn-sm shrink-0"
        aria-label="دانلود فایل صوتی"
      >
        {downloading ? '…' : '⬇ دانلود'}
      </button>
    </div>
  );
}
