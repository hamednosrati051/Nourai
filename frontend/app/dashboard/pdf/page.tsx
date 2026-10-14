'use client';

import { useEffect, useState } from 'react';
import { apiPost, apiGet, readCookie, apiUrl } from '@/lib/api';
import { Loader2, FileText, Download, Sparkles, ArrowLeft, History } from 'lucide-react';

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
      <div className="flex items-center gap-3 mb-6">
        <FileText className="w-7 h-7 text-primary" />
        <h1 className="text-2xl font-bold">ساخت PDF با هوش مصنوعی</h1>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-600 dark:text-red-400 text-sm">
          {error}
        </div>
      )}

      {step === 1 ? (
        <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
          {/* tabs */}
          <div className="flex gap-2 mb-5">
            <button
              onClick={() => setTab('idea')}
              className={`flex-1 py-2.5 rounded-xl text-sm font-medium transition ${
                tab === 'idea'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/80'
              }`}
            >
              <Sparkles className="w-4 h-4 inline ml-1" />
              از ایده / موضوع
            </button>
            <button
              onClick={() => setTab('text')}
              className={`flex-1 py-2.5 rounded-xl text-sm font-medium transition ${
                tab === 'text'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/80'
              }`}
            >
              <FileText className="w-4 h-4 inline ml-1" />
              از متن آماده
            </button>
          </div>

          <label className="block text-sm font-medium mb-1.5">
            عنوان سند <span className="text-muted-foreground font-normal">(اختیاری)</span>
          </label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="مثلاً: گزارش فروش تابستان"
            className="w-full mb-4 px-4 py-2.5 rounded-xl border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />

          <label className="block text-sm font-medium mb-1.5">
            {tab === 'idea' ? 'موضوع یا ایده' : 'متن آماده'}
          </label>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={6}
            placeholder={
              tab === 'idea'
                ? 'مثلاً: راهنمای نگهداری گیاهان آپارتمانی'
                : 'متن خود را اینجا بچسبانید...'
            }
            className="w-full mb-4 px-4 py-3 rounded-xl border border-border bg-background text-sm leading-7 focus:outline-none focus:ring-2 focus:ring-primary/50 resize-y"
          />

          <label className="block text-sm font-medium mb-1.5">طول سند</label>
          <div className="flex gap-2 mb-6">
            {LENGTHS.map((l) => (
              <button
                key={l.value}
                onClick={() => setLength(l.value)}
                className={`px-4 py-2 rounded-xl text-sm transition ${
                  length === l.value
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80'
                }`}
              >
                {l.label}
              </button>
            ))}
          </div>

          <button
            onClick={handlePrepare}
            disabled={loading}
            className="w-full py-3 rounded-xl bg-primary text-primary-foreground font-medium text-sm hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
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
          <p className="text-xs text-muted-foreground mt-3 text-center">
            هزینه فقط در این مرحله از کیف پول کم می‌شود. ساخت PDF رایگان است.
          </p>
        </div>
      ) : (
        <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
          <button
            onClick={backToStep1}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-4"
          >
            <ArrowLeft className="w-4 h-4 rotate-180" />
            بازگشت و تغییر ورودی
          </button>

          <h2 className="text-lg font-semibold mb-1">پیش‌نمایش و ویرایش متن</h2>
          <p className="text-sm text-muted-foreground mb-4">
            متن تولیدشده را بررسی و در صورت نیاز ویرایش کنید، سپس PDF بسازید.
          </p>

          <label className="block text-sm font-medium mb-1.5">عنوان سند</label>
          <input
            value={draftTitle}
            onChange={(e) => setDraftTitle(e.target.value)}
            className="w-full mb-4 px-4 py-2.5 rounded-xl border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
          />

          <label className="block text-sm font-medium mb-1.5">متن سند</label>
          <textarea
            value={draftText}
            onChange={(e) => setDraftText(e.target.value)}
            rows={16}
            dir="rtl"
            className="w-full mb-4 px-4 py-3 rounded-xl border border-border bg-background text-sm leading-8 focus:outline-none focus:ring-2 focus:ring-primary/50 resize-y"
          />

          <button
            onClick={handleRender}
            disabled={rendering}
            className="w-full py-3 rounded-xl bg-primary text-primary-foreground font-medium text-sm hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
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

      {/* history */}
      <div className="mt-10">
        <div className="flex items-center gap-2 mb-4">
          <History className="w-5 h-5 text-muted-foreground" />
          <h2 className="text-lg font-semibold">تاریخچه</h2>
        </div>
        {history.length === 0 ? (
          <p className="text-sm text-muted-foreground">هنوز سندی نساخته‌اید.</p>
        ) : (
          <div className="space-y-2">
            {history.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{item.title}</p>
                  {item.created_at && (
                    <p className="text-xs text-muted-foreground">
                      {new Date(item.created_at).toLocaleString('fa-IR')}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => handleDownloadHistory(item)}
                  disabled={downloadingId === item.id}
                  className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-muted text-sm hover:bg-muted/80 disabled:opacity-50"
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
  );
}
