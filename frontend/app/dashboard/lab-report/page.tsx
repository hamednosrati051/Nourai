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
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
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

  const onFile = (f: File | undefined) => {
    if (!f) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(f.type)) {
      toast('فقط JPG، PNG یا WebP', 'error');
      return;
    }
    if (f.size > 10 * 1024 * 1024) {
      toast('حداکثر ۱۰ مگابایت', 'error');
      return;
    }
    setImage(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
  };

  const onAnalyze = async () => {
    if (!image) {
      toast('اول تصویر برگه آزمایش رو انتخاب کن', 'error');
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append('image', image);
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
          className="hidden"
          onChange={(e) => onFile(e.target.files?.[0])}
        />
        {preview ? (
          <img src={preview} alt="preview" className="max-h-64 mx-auto rounded-xl" />
        ) : (
          <div className="flex flex-col items-center gap-2 text-neutral-500">
            <Upload className="h-10 w-10" />
            <p>تصویر برگه آزمایش رو انتخاب کنید</p>
            <p className="text-xs">JPG، PNG یا WebP — حداکثر ۱۰ مگابایت</p>
          </div>
        )}
      </div>

      <button
        onClick={onAnalyze}
        disabled={loading || !image}
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
              setImage(null);
              setPreview(null);
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
