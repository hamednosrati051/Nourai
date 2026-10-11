'use client';

import { useEffect, useRef, useState } from 'react';
import { FileText, Upload, Loader2, AlertTriangle, Copy, Check, History, MessageSquare, Send } from 'lucide-react';
import { apiGet, apiPostForm, apiPost } from '@/lib/api';
import { useToast } from '@/components/Toast';
import { Modal } from '@/components/Modal';

interface HistoryItem {
  id: string;
  result_text: string;
  created_at: string | null;
}

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

const CONTRACT_DISCLAIMER = 'این تحلیل صرفاً جهت اطلاع است و مشاوره حقوقی محسوب نمی‌شود. برای تصمیم‌گیری حقوقی حتماً با وکیل مشورت کنید.';

export default function ContractsPage() {
  const { toast } = useToast();
  const [tab, setTab] = useState<'image' | 'chat'>('image');
  
  // Image analysis state
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const loadHistory = async () => {
    try {
      const res = await apiGet<{ items: HistoryItem[] }>('/vision/history?mode=contract');
      setHistory(res.items);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    loadHistory();
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

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
      toast('اول تصویر قرارداد رو انتخاب کن', 'error');
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const form = new FormData();
      form.append('image', image);
      form.append('mode', 'contract');
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

  const onCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast('کپی شد', 'success');
    } catch {
      toast('کپی نشد', 'error');
    }
  };

  const onSendChat = async () => {
    if (!input.trim() || chatLoading) return;
    const userMsg = input.trim();
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: userMsg }]);
    setChatLoading(true);
    try {
      const systemPrompt = `شما یک دستیار حقوقی برای قراردادهای ایرانی هستید. به کاربر کمک کنید قرارداد بنویسد یا قراردادش را اصلاح کند. ${CONTRACT_DISCLAIMER}`;
      const res = await apiPost<{ reply: string }>('/chat', {
        messages: [
          { role: 'system', content: systemPrompt },
          ...messages.map((m) => ({ role: m.role, content: m.content })),
          { role: 'user', content: userMsg },
        ],
      }, {
        'Idempotency-Key': crypto.randomUUID(),
      });
      setMessages((prev) => [...prev, { role: 'assistant', content: res.reply }]);
    } catch (err: any) {
      toast(err?.message || 'خطا در ارسال', 'error');
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-extrabold flex items-center gap-2">
        <FileText className="h-6 w-6" />
        قراردادها
      </h1>

      {/* Tabs */}
      <div className="flex gap-2 p-1 bg-neutral-100 dark:bg-white/5 rounded-xl">
        <button
          onClick={() => setTab('image')}
          className={`flex-1 py-2 px-4 rounded-lg text-sm font-bold transition-colors ${
            tab === 'image'
              ? 'bg-white dark:bg-white/10 shadow'
              : 'text-neutral-500 hover:text-neutral-700'
          }`}
        >
          تحلیل تصویر
        </button>
        <button
          onClick={() => setTab('chat')}
          className={`flex-1 py-2 px-4 rounded-lg text-sm font-bold transition-colors ${
            tab === 'chat'
              ? 'bg-white dark:bg-white/10 shadow'
              : 'text-neutral-500 hover:text-neutral-700'
          }`}
        >
          دستیار متنی
        </button>
      </div>

      {/* Disclaimer */}
      <div className="card border-amber-300 bg-amber-50 dark:bg-amber-950/20 flex gap-3">
        <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600" />
        <p className="text-sm text-amber-800 dark:text-amber-200">{CONTRACT_DISCLAIMER}</p>
      </div>

      {tab === 'image' && (
        <>
          <div className="flex items-center justify-between">
            <span className="text-sm text-neutral-500">تصویر قرارداد را آپلود کنید</span>
            <button
              onClick={() => setHistoryOpen(true)}
              className="btn-ghost btn-sm flex items-center gap-1"
            >
              <History className="h-4 w-4" />
              تاریخچه
            </button>
          </div>

          <Modal open={historyOpen} title="تاریخچه تحلیل قرارداد" onClose={() => setHistoryOpen(false)} maxWidth="max-w-2xl">
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
                <p>تصویر قرارداد رو انتخاب کنید</p>
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
              'تحلیل قرارداد'
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
                    onClick={() => onCopy(result)}
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
        </>
      )}

      {tab === 'chat' && (
        <div className="flex flex-col gap-4">
          <div className="card min-h-[300px] max-h-[400px] overflow-y-auto flex flex-col gap-3 p-4">
            {messages.length === 0 && (
              <p className="text-center text-neutral-500 py-8 text-sm">
                بگید چه قراردادی می‌خواید یا متنتون رو بفرستید تا اصلاح کنم
                <br />
                <span className="text-xs">مثلاً: «یه قولنامه برای فروش آپارتمان می‌خوام»</span>
              </p>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={`p-3 rounded-xl max-w-[85%] ${
                  m.role === 'user'
                    ? 'bg-brand-500 text-white self-start'
                    : 'bg-neutral-100 dark:bg-white/5 self-end'
                }`}
              >
                <div className="whitespace-pre-wrap text-sm leading-7">{m.content}</div>
              </div>
            ))}
            {chatLoading && (
              <div className="self-end p-3 rounded-xl bg-neutral-100 dark:bg-white/5">
                <Loader2 className="h-4 w-4 animate-spin" />
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
          <div className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && onSendChat()}
              placeholder="پیامتون رو بنویسید…"
              className="input flex-1"
              disabled={chatLoading}
            />
            <button
              onClick={onSendChat}
              disabled={chatLoading || !input.trim()}
              className="btn-primary px-4 disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
