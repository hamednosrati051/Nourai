'use client';

import { useRef, useState } from 'react';
import { FlaskConical, Upload, Loader2, AlertTriangle } from 'lucide-react';
import { apiPostForm } from '@/lib/api';
import { useToast } from '@/components/Toast';

export default function LabReportPage() {
  const { toast } = useToast();
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

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
    } catch (err: any) {
      toast(err?.message || 'تحلیل ناموفق بود', 'error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-extrabold flex items-center gap-2">
        <FlaskConical className="h-6 w-6" />
        تحلیل برگه آزمایش
      </h1>

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
        <div className="card whitespace-pre-wrap leading-7">{result}</div>
      )}
    </div>
  );
}
