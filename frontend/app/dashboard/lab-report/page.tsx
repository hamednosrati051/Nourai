'use client';

import { useEffect, useRef, useState } from 'react';
import { FlaskConical, Upload, Loader2, AlertTriangle, Copy, Check, History } from 'lucide-react';
import { apiGet, apiPostForm } from '@/lib/api';
import { useToast } from '@/components/Toast';
import { Modal } from '@/components/Modal';

interface HistoryItem {
  id: string;
  result_text: string;
  created_at: string | null;
}

export default function LabReportPage() {
  const { toast } = useToast();
  const [images, setImages] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadHistory = async () => {
    try {
      const res = await apiGet<{ items: HistoryItem[] }>('/vision/history?mode=lab_report');
      setHistory(res.items);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const onFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const valid: File[] = [];
    for (const f of Array.from(files)) {
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(f.type)) {
        toast('فقط JPG، PNG یا WebP', 'error');
        continue;
      }
      if (f.size > 10 * 1024 * 1024) {
        toast('حداکثر ۱۰ مگابایت برای هر تصویر', 'error');
        continue;
      }
      valid.push(f);
    }
    const next = [...images, ...valid].slice(0, 10);
    setImages(next);
    setPreviews(next.map((f) => URL.createObjectURL(f)));
    setResult(null);
  };

  const removeImage = (idx: number) => {
    const next = images.filter((_, i) => i !== idx);
    setImages(next);
    setPreviews(next.map((f) => URL.createObjectURL(f)));
  };

  const onAnalyze = async () => {
    if (images.length === 0) {
      toast('اول تصویر برگه آزمایش رو انتخاب کن', 'error');
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const form = new FormData();
      images.forEach((img) => form.append('images', img));
      form.append('mode', 'lab_report');
      const res = await apiPostForm<{ analysis: string }>('/vision/analyze', form, undefined, {
        'Idempotency-Key': crypto.randomUUID(),
      });
      setResult(res.analysis);
      loadHistory();
    } catch (err: any) {
      toast(err?.message || 'تحلیل ناموفق بود', 'error');
    } finally {
      setLoading(false);
    }
  };

  const onCopy = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast('کپی شد', 'success');
    } catch {
      toast('کپی نشد', 'error');
    }
  };

  return (
    <div className="flex flex-col gap-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-extrabold flex items-center gap-2">
          <FlaskConical className="h-6 w-6" />
          تحلیل برگه آزمایش
        </h1>
        <button
          onClick={() => setHistoryOpen(true)}
          className="btn-ghost btn-sm flex items-center gap-1"
        >
          <History className="h-4 w-4" />
          تاریخچه
        </button>
      </div>

      <Modal open={historyOpen} title="تاریخچه تحلیل برگه آزمایش" onClose={() => setHistoryOpen(false)} maxWidth="max-w-2xl">
        <div className="flex max-h-[70vh] flex-col gap-2 overflow-y-auto">
          {history.length === 0 && (
            <p className="text-center text-neutral-500 py-8">هنوز تحلیلی انجام نشده</p>
          )}
          {history.map((h) => (
            <button
              key={h.id}
              onClick={() => {
                setResult(h.result_text);
                setHistoryOpen(false);
              }}
              className="text-right p-3 rounded-lg bg-neutral-100 dark:bg-white/5 hover:bg-neutral-200 dark:hover:bg-white/10 transition-colors block w-full"
            >
              <p className="text-sm line-clamp-1 mb-1">{h.result_text.slice(0, 80)}…</p>
              {h.created_at && (
                <p className="text-xs text-neutral-500">
                  {new Date(h.created_at).toLocaleDateString('fa-IR')} — {new Date(h.created_at).toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' })}
                </p>
              )}
            </button>
          ))}
        </div>
      </Modal>

      <div className="card border-amber-300 bg-amber-50 dark:bg-amber-950/20 flex gap-3">
        <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600" />
        <p className="text-sm text-amber-800 dark:text-amber-200">
          این تحلیل صرفاً جهت اطلاع است و <strong>جایگزین نظر پزشک نیست</strong>.
          حتماً با پزشک خود مشورت کنید.
        </p>
      </div>

      <div
        onClick={() => fileRef.current?.click()}
        className="card cursor-pointer border-dashed text-center py-10 hover:border-brand-400 transition-colors"
      >
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          className="hidden"
          onChange={(e) => onFiles(e.target.files)}
        />
        {previews.length > 0 ? (
          <div className="flex flex-wrap justify-center gap-3">
            {previews.map((src, i) => (
              <div key={i} className="relative">
                <img src={src} alt={`برگه ${i + 1}`} className="h-32 w-32 rounded-xl object-cover" />
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeImage(i);
                  }}
                  aria-label={`حذف تصویر ${i + 1}`}
                  className="absolute -top-2 -right-2 flex h-6 w-6 items-center justify-center rounded-full bg-red-600 text-xs text-white"
                >
                  ✕
                </button>
                <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1.5 text-[10px] text-white">
                  {i + 1}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2 text-neutral-500">
            <Upload className="h-10 w-10" />
            <p>تصاویر برگه آزمایش رو انتخاب کنید (چند برگه)</p>
            <p className="text-xs">JPG، PNG یا WebP — حداکثر ۱۰ مگابایت برای هر تصویر</p>
          </div>
        )}
      </div>

      <button
        onClick={onAnalyze}
        disabled={loading || images.length === 0}
        className="btn-primary disabled:opacity-50"
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            در حال تحلیل…
          </span>
        ) : (
          'تحلیل برگه آزمایش'
        )}
      </button>

      {result && (
        <>
          <button
            onClick={() => {
              setImages([]);
              setPreviews([]);
              setResult(null);
            }}
            className="btn-primary"
          >
            تحلیل جدید
          </button>
          <div className="card">
            <div className="flex justify-between items-center mb-3">
              <span className="font-bold text-sm">نتیجه تحلیل</span>
              <button
                onClick={onCopy}
                className="btn-ghost btn-sm flex items-center gap-1"
              >
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {copied ? 'کپی شد' : 'کپی'}
              </button>
            </div>
            <div className="whitespace-pre-wrap leading-7 select-text">{result}</div>
          </div>
        </>
      )}
    </div>
  );
}
