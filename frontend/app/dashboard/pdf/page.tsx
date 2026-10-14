'use client';

import { useState } from 'react';
import { FileDown, Loader2, Lightbulb, Type } from 'lucide-react';
import { readCookie, apiUrl } from '@/lib/api';
import { useToast } from '@/components/Toast';

const LENGTHS = [
  { value: 'short', label: 'خلاصه', hint: 'حدود ۱-۲ صفحه' },
  { value: 'medium', label: 'متوسط', hint: 'حدود ۳-۵ صفحه' },
  { value: 'long', label: 'مفصل', hint: 'حدود ۶-۱۰ صفحه' },
] as const;

export default function PdfPage() {
  const { toast } = useToast();
  const [tab, setTab] = useState<'idea' | 'text'>('idea');
  const [content, setContent] = useState('');
  const [title, setTitle] = useState('');
  const [length, setLength] = useState<'short' | 'medium' | 'long'>('medium');
  const [loading, setLoading] = useState(false);

  const handleGenerate = async () => {
    if (!content.trim()) {
      toast('لطفاً موضوع یا متن را بنویسید', 'error');
      return;
    }
    setLoading(true);
    try {
      // Binary download: apiPost parses JSON, so use fetch directly with CSRF header
      const csrf = readCookie('nourai_csrf') ?? readCookie('nourai_admin_csrf');
      const res = await fetch(apiUrl('/pdf/generate'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': crypto.randomUUID(),
          ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
        },
        credentials: 'include',
        body: JSON.stringify({
          mode: tab,
          content: content.trim(),
          title: title.trim() || undefined,
          length,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.message || 'خطا در تولید PDF');
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `nourai-pdf-${Date.now()}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast('PDF ساخته و دانلود شد', 'success');
    } catch (e: any) {
      toast(e.message || 'خطا در تولید PDF', 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen">
      <main className="mx-auto w-full max-w-3xl px-4 pb-20 pt-28 sm:px-6">
        <div className="mb-8">
          <p className="badge badge-warning mb-3">ساخت PDF با هوش مصنوعی</p>
          <h1 className="text-3xl font-black">سند PDF بسازید</h1>
          <p className="mt-2 text-sm text-neutral-600 dark:text-slate-400">
            ایده یا موضوع را بدهید، هوش مصنوعی سند فارسی مرتب می‌نویسد و PDF تحویل می‌گیرید.
          </p>
        </div>

        {/* Tabs */}
        <div className="mb-6 flex gap-2">
          <button
            onClick={() => setTab('idea')}
            className={`flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-bold transition ${
              tab === 'idea'
                ? 'bg-brand-500 text-white shadow'
                : 'bg-neutral-100 text-neutral-600 dark:bg-slate-800 dark:text-slate-300'
            }`}
          >
            <Lightbulb className="h-4 w-4" />
            از ایده
          </button>
          <button
            onClick={() => setTab('text')}
            className={`flex items-center gap-2 rounded-xl px-5 py-2.5 text-sm font-bold transition ${
              tab === 'text'
                ? 'bg-brand-500 text-white shadow'
                : 'bg-neutral-100 text-neutral-600 dark:bg-slate-800 dark:text-slate-300'
            }`}
          >
            <Type className="h-4 w-4" />
            از متن آماده
          </button>
        </div>

        <div className="card space-y-5">
          <div>
            <label className="mb-2 block text-sm font-bold">
              {tab === 'idea' ? 'موضوع یا ایده سند' : 'متن آماده شما'}
            </label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={tab === 'idea' ? 4 : 10}
              placeholder={
                tab === 'idea'
                  ? 'مثلاً: گزارش درباره انرژی خورشیدی در ایران...'
                  : 'متن خود را اینجا بچسبانید تا قالب‌بندی و ساختاردهی شود...'
              }
              className="textarea w-full"
              maxLength={10000}
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-bold">عنوان سند (اختیاری)</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="مثلاً: گزارش انرژی خورشیدی"
              className="input w-full"
              maxLength={120}
            />
          </div>

          <div>
            <label className="mb-2 block text-sm font-bold">طول سند</label>
            <div className="grid grid-cols-3 gap-2">
              {LENGTHS.map((l) => (
                <button
                  key={l.value}
                  onClick={() => setLength(l.value)}
                  className={`rounded-xl border-2 px-3 py-3 text-center transition ${
                    length === l.value
                      ? 'border-brand-500 bg-brand-50 dark:bg-brand-500/10'
                      : 'border-neutral-200 dark:border-slate-700'
                  }`}
                >
                  <div className="text-sm font-extrabold">{l.label}</div>
                  <div className="mt-1 text-xs text-neutral-500">{l.hint}</div>
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={handleGenerate}
            disabled={loading || !content.trim()}
            className="btn-primary flex w-full items-center justify-center gap-2 py-3.5"
          >
            {loading ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                در حال ساخت PDF...
              </>
            ) : (
              <>
                <FileDown className="h-5 w-5" />
                ساخت و دانلود PDF
              </>
            )}
          </button>

          <p className="text-center text-xs text-neutral-500">
            هزینه بر اساس تعرفه گفت‌وگوی متنی از کیف پول شما کسر می‌شود.
          </p>
        </div>
      </main>
    </div>
  );
}
