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
  
  // Image analysis state (multi-image: up to 10)
  const [images, setImages] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatSessionId, setChatSessionId] = useState<string | null>(null);
  const [chatHistory, setChatHistory] = useState<{ id: string; title: string; created_at: string }[]>([]);
  const [chatHistoryOpen, setChatHistoryOpen] = useState(false);
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
      toast('اول تصویر قرارداد رو انتخاب کن', 'error');
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const form = new FormData();
      images.forEach((img) => form.append('images', img));
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
    const newMessages: ChatMessage[] = [...messages, { role: 'user', content: userMsg }];
    setMessages(newMessages);
    setChatLoading(true);
    try {
      const res = await apiPost<{ reply: string; session_id: string }>('/vision/contract-chat', {
        message: userMsg,
        history: messages.map((m) => ({ role: m.role, content: m.content })),
        session_id: chatSessionId,
      }, undefined, {
        'Idempotency-Key': crypto.randomUUID(),
      });
      setMessages([...newMessages, { role: 'assistant', content: res.reply }]);
      if (res.session_id) setChatSessionId(res.session_id);
    } catch (err: any) {
      toast(err?.message || 'خطا در ارسال', 'error');
    } finally {
      setChatLoading(false);
    }
  };

  const loadChatHistory = async () => {
    try {
      const res = await apiGet<{ items: { id: string; title: string; created_at: string }[] }>('/vision/contract-chat/history');
      setChatHistory(res.items);
    } catch {}
    setChatHistoryOpen(true);
  };

  const loadChatSession = async (sessionId: string) => {
    try {
      const res = await apiGet<{ messages: ChatMessage[] }>('/vision/contract-chat/history/' + sessionId);
      setMessages(res.messages);
      setChatSessionId(sessionId);
      setChatHistoryOpen(false);
    } catch (err: any) {
      toast(err?.message || 'خطا در بارگذاری', 'error');
    }
  };

  const startNewChat = () => {
    setMessages([]);
    setChatSessionId(null);
  };

  return (
    <div className="flex flex-col gap-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-extrabold flex items-center gap-2">
        <FileText className="h-6 w-6" />
        قراردادهای حقوقی
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
              multiple
              className="hidden"
              onChange={(e) => onFiles(e.target.files)}
            />
            {previews.length > 0 ? (
              <div className="flex flex-wrap justify-center gap-3">
                {previews.map((src, i) => (
                  <div key={i} className="relative">
                    <img src={src} alt={`صفحه ${i + 1}`} className="h-32 w-32 rounded-xl object-cover" />
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
                <p>تصاویر قرارداد رو انتخاب کنید (چند صفحه)</p>
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
              'تحلیل قرارداد'
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
          <div className="flex gap-2 justify-start">
            <button onClick={loadChatHistory} className="btn-ghost text-sm flex items-center gap-1">
              <History className="h-4 w-4" />
              تاریخچه گفتگو
            </button>
            {messages.length > 0 && (
              <button onClick={startNewChat} className="btn-ghost text-sm">
                گفتگوی جدید
              </button>
            )}
          </div>
          <Modal open={chatHistoryOpen} title="تاریخچه گفتگو" onClose={() => setChatHistoryOpen(false)} maxWidth="max-w-2xl">
            <div className="flex max-h-[70vh] flex-col gap-2 overflow-y-auto">
              {chatHistory.length === 0 && (
                <p className="text-center text-neutral-500 py-8">هنوز گفتگویی انجام نشده</p>
              )}
              {chatHistory.map((h) => (
                <button
                  key={h.id}
                  onClick={() => loadChatSession(h.id)}
                  className="text-right p-3 rounded-lg bg-neutral-100 dark:bg-white/5 hover:bg-neutral-200 dark:hover:bg-white/10 transition-colors block w-full"
                >
                  <p className="text-sm line-clamp-1 mb-1">{h.title || 'گفتگو'}</p>
                  {h.created_at && (
                    <p className="text-xs text-neutral-500">
                      {new Date(h.created_at).toLocaleDateString('fa-IR')} — {new Date(h.created_at).toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' })}
                    </p>
                  )}
                </button>
              ))}
            </div>
          </Modal>
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
