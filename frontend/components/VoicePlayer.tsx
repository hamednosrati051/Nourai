'use client';

import { useRef, useState } from 'react';
import { useAssetDownloadUrl } from '@/features/voice/hooks';

/** Pretty custom audio player: play/pause, seekable progress, time, download. */
export function VoicePlayer({
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
