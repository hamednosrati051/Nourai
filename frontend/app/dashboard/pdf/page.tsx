'use client';

import { useEffect, useRef, useState } from 'react';
import { apiPost, apiGet, readCookie, apiUrl } from '@/lib/api';
import { Loader2, FileText, Download, Sparkles, ArrowLeft, History, X } from 'lucide-react';

type Tab = 'idea' | 'text';
type LengthChoice = 'short' | 'medium' | 'long';

interface HistoryItem {
  id: string;
  title: string;
  created_at: string | null;
}

const LENGTHS: { value: LengthChoice; label: string }[] = [
  { value: 'short', label: 'کوتاه' },
  { value: 'medium', label: 'متوسط' },
  { value: 'long', label: 'بلند' },
];

export default function PdfPage() {
  const [tab, setTab] = useState<Tab>('idea');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [length, setLength] = useState<LengthChoice>('medium');
  const [step, setStep] = useState<1 | 2>(1);
  const [draftText, setDraftText] = useState('');
  const [draftTitle, setDraftTitle] = useState('');
  const [loading, setLoading] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const contentRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    // autofocus the main input box whenever the tab changes
    if (step === 1) contentRef.current?.focus();
  }, [tab, step]);

  const loadHistory = async () => {
    try {
      const res = await apiGet<{ items: HistoryItem[] }>('/pdf/history');
      setHistory(res.items ?? []);
    } catch {
      // history is optional; ignore failures
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  const downloadBlob = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const binaryPost = async (path: string, body: object): Promise<Blob> => {
    const csrf = readCookie('nourai_csrf') ?? readCookie('nourai_admin_csrf');
    const res = await fetch(apiUrl(path), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': crypto.randomUUID(),
        ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
      },
      credentials: 'include',
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      let msg = 'خطایی رخ داد.';
      try {
        const j = await res.json();
        msg = j?.error?.message || msg;
      } catch {}
      throw new Error(msg);
    }
    return res.blob();
  };

  const handlePrepare = async () => {
    if (!content.trim()) {
      setError('لطفاً متن یا موضوع را وارد کنید.');
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await apiPost<{ text: string; title: string }>(
        '/pdf/prepare',
        {
          mode: tab,
          content: content.trim(),
          title: title.trim() || undefined,
          length,
        },
        undefined,
        { 'Idempotency-Key': crypto.randomUUID() }
      );
      setDraftText(res.text);
      setDraftTitle(res.title);
      setStep(2);
    } catch (e: any) {
      setError(e?.message || 'تولید متن ناموفق بود.');
    } finally {
      setLoading(false);
    }
  };

  const handleRender = async () => {
    if (!draftText.trim()) {
      setError('متن سند خالی است.');
      return;
    }
    setError(null);
    setRendering(true);
    try {
      const blob = await binaryPost('/pdf/render', {
        text: draftText.trim(),
        title: draftTitle.trim() || undefined,
      });
      downloadBlob(blob, `nourai-pdf-${Date.now().toString(36)}.pdf`);
      loadHistory();
    } catch (e: any) {
      setError(e?.message || 'ساخت PDF ناموفق بود.');
    } finally {
      setRendering(false);
    }
  };

  const handleDownloadHistory = async (item: HistoryItem) => {
    setDownloadingId(item.id);
    try {
      const csrf = readCookie('nourai_csrf') ?? readCookie('nourai_admin_csrf');
      const res = await fetch(apiUrl(`/pdf/${item.id}/download`), {
        credentials: 'include',
        headers: csrf ? { 'X-CSRF-Token': csrf } : {},
      });
      if (!res.ok) throw new Error('دانلود ناموفق بود.');
      const blob = await res.blob();
      downloadBlob(blob, `nourai-pdf-${item.id.slice(0, 8)}.pdf`);
    } catch (e: any) {
      setError(e?.message || 'دانلود ناموفق بود.');
    } finally {
      setDownloadingId(null);
    }
  };

  const backToStep1 = () => {
    setStep(1);
    setError(null);
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-8" dir="rtl">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <FileText className="w-7 h-7 text-primary" />
          <h1 className="text-2xl font-bold">ساخت PDF با هوش مصنوعی</h1>
        </div>
        <button
          onClick={() => setHistoryOpen(true)}
          className="btn-ghost btn-sm flex items-center gap-1.5"
        >
          <History className="w-4 h-4" />
          تاریخچه
        </button>
      </div>

      {/* history modal */}
      {historyOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
          onClick={() => setHistoryOpen(false)}
        >
          <div
            className="card w-full max-w-lg max-h-[80vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
            dir="rtl"
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">تاریخچه PDFها</h2>
              <button
                onClick={() => setHistoryOpen(false)}
                className="btn-ghost btn-sm p-1.5"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            {history.length === 0 ? (
              <p className="text-sm text-neutral-500">هنوز سندی نساخته‌اید.</p>
            ) : (
              <div className="space-y-2">
                {history.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between gap-3 rounded-xl border border-neutral-200 dark:border-white/10 px-4 py-3"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{item.title}</p>
                      {item.created_at && (
                        <p className="text-xs text-neutral-500">
                          {new Date(item.created_at).toLocaleString('fa-IR')}
                        </p>
                      )}
                    </div>
                    <button
                      onClick={() => handleDownloadHistory(item)}
                      disabled={downloadingId === item.id}
                      className="btn-ghost btn-sm shrink-0 flex items-center gap-1.5 disabled:opacity-50"
                    >
                      {downloadingId === item.id ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Download className="w-4 h-4" />
                      )}
                      دانلود
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-600 dark:text-red-400 text-sm">
          {error}
        </div>
      )}

      {step === 1 ? (
        <div className="card">
          {/* tabs */}
          <div className="flex gap-2 mb-5">
            <button
              onClick={() => setTab('idea')}
              className={`flex-1 py-2.5 rounded-xl text-sm font-medium transition ${
                tab === 'idea'
                  ? 'bg-white dark:bg-white/10 shadow-sm ring-1 ring-brand-400'
                  : 'bg-neutral-100 dark:bg-white/5 text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'
              }`}
            >
              <Sparkles className="w-4 h-4 inline ml-1" />
              از ایده / موضوع
            </button>
            <button
              onClick={() => setTab('text')}
              className={`flex-1 py-2.5 rounded-xl text-sm font-medium transition ${
                tab === 'text'
                  ? 'bg-white dark:bg-white/10 shadow-sm ring-1 ring-brand-400'
                  : 'bg-neutral-100 dark:bg-white/5 text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'
              }`}
            >
              <FileText className="w-4 h-4 inline ml-1" />
              از متن آماده
            </button>
          </div>

          <label className="block text-sm font-medium mb-1.5">
            عنوان سند <span className="text-neutral-500 font-normal">(اختیاری)</span>
          </label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="مثلاً: گزارش فروش تابستان"
            className="input w-full mb-4"
          />

          <label className="block text-sm font-medium mb-1.5">
            {tab === 'idea' ? 'موضوع یا ایده' : 'متن آماده'}
          </label>
          <textarea
            ref={contentRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={6}
            placeholder={
              tab === 'idea'
                ? 'مثلاً: راهنمای نگهداری گیاهان آپارتمانی'
                : 'متن خود را اینجا بچسبانید...'
            }
            className="input w-full mb-4 resize-y leading-7"
          />

          <label className="block text-sm font-medium mb-1.5">طول سند</label>
          <div className="flex gap-2 mb-6">
            {LENGTHS.map((l) => (
              <button
                key={l.value}
                onClick={() => setLength(l.value)}
                className={`px-4 py-2 rounded-xl text-sm transition ${
                  length === l.value
                    ? 'bg-white dark:bg-white/10 shadow-sm ring-1 ring-brand-400'
                    : 'bg-neutral-100 dark:bg-white/5 text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300'
                }`}
              >
                {l.label}
              </button>
            ))}
          </div>

          <button
            onClick={handlePrepare}
            disabled={loading}
            className="btn-primary w-full disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                در حال تولید متن...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                تولید متن با هوش مصنوعی
              </>
            )}
          </button>
          <p className="text-xs text-neutral-500 mt-3 text-center">
            هزینه فقط در این مرحله از کیف پول کم می‌شود. ساخت PDF رایگان است.
          </p>
        </div>
      ) : (
        <div className="card">
          <button
            onClick={backToStep1}
            className="flex items-center gap-1 text-sm text-neutral-500 hover:text-foreground mb-4"
          >
            <ArrowLeft className="w-4 h-4 rotate-180" />
            بازگشت و تغییر ورودی
          </button>

          <h2 className="text-lg font-semibold mb-1">پیش‌نمایش و ویرایش متن</h2>
          <p className="text-sm text-neutral-500 mb-4">
            متن تولیدشده را بررسی و در صورت نیاز ویرایش کنید، سپس PDF بسازید.
          </p>

          <label className="block text-sm font-medium mb-1.5">عنوان سند</label>
          <input
            value={draftTitle}
            onChange={(e) => setDraftTitle(e.target.value)}
            className="input w-full mb-4"
          />

          <label className="block text-sm font-medium mb-1.5">متن سند</label>
          <textarea
            value={draftText}
            onChange={(e) => setDraftText(e.target.value)}
            rows={16}
            dir="rtl"
            className="input w-full mb-4 resize-y leading-8"
          />

          <button
            onClick={handleRender}
            disabled={rendering}
            className="btn-primary w-full disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {rendering ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                در حال ساخت PDF...
              </>
            ) : (
              <>
                <Download className="w-4 h-4" />
                ساخت و دانلود PDF
              </>
            )}
          </button>
        </div>
      )}

    </div>
  );
}
