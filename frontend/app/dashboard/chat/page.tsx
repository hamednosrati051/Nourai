'use client';

import { useEffect, useRef, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  useConversations,
  useConversationMessages,
  useCreateConversation,
  useDeleteConversation,
  useSendMessage,
} from '@/features/chat/hooks';
import { useModels } from '@/features/models/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { useToast } from '@/components/Toast';
import { formatDateTime } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';

const messageSchema = z.object({
  content: z.string().trim().min(1, 'متن پیام را بنویسید.').max(8000, 'پیام بیش از حد طولانی است.'),
});
type MessageForm = z.infer<typeof messageSchema>;

/** Text chat: conversation list + message thread + composer. */
export default function ChatPage() {
  const { toast } = useToast();
  const [activeId, setActiveId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const conversations = useConversations();
  const models = useModels();
  const messages = useConversationMessages(activeId);
  const createConversation = useCreateConversation();
  const deleteConversation = useDeleteConversation();
  const sendMessage = useSendMessage();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<MessageForm>({ resolver: zodResolver(messageSchema) });

  // Auto-select the first conversation when none is chosen.
  useEffect(() => {
    if (!activeId && conversations.data && conversations.data.length > 0) {
      setActiveId(conversations.data[0]!.id);
    }
  }, [activeId, conversations.data]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.data]);

  const textModels = (models.data ?? []).filter((m) => m.capability === 'text');

  const startConversation = (modelId: string) => {
    createConversation.mutate(
      { model_id: modelId },
      {
        onSuccess: (conv) => setActiveId(conv.id),
        onError: (err) =>
          toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'خطایی رخ داد.', 'error'),
      },
    );
  };

  const onSend = (values: MessageForm) => {
    if (!activeId) return;
    sendMessage.mutate(
      { conversationId: activeId, content: values.content },
      {
        onSuccess: () => reset(),
        onError: (err) => {
          if (err instanceof ApiError && err.code === 'INSUFFICIENT_BALANCE') {
            toast('موجودی کافی نیست؛ لطفاً کیف پول را شارژ کنید.', 'error');
          } else {
            toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'ارسال پیام ناموفق بود.', 'error');
          }
        },
      },
    );
  };

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-extrabold">گفت‌وگوی متنی</h1>

      {conversations.isLoading ? (
        <LoadingSpinner />
      ) : conversations.isError ? (
        <ErrorState message="بارگذاری گفت‌وگوها ناموفق بود." onRetry={() => conversations.refetch()} />
      ) : (
        <div className="flex flex-col gap-4 lg:flex-row">
          {/* Conversation list */}
          <aside aria-label="فهرست گفت‌وگوها" className="lg:w-72 lg:shrink-0">
            <div className="card !p-3">
              <div className="mb-2 flex items-center justify-between px-1">
                <h2 className="text-sm font-bold">گفت‌وگوها</h2>
              </div>
              {models.isLoading ? (
                <p className="px-1 text-xs text-neutral-500">در حال بارگذاری مدل‌ها…</p>
              ) : textModels.length === 0 ? (
                <p className="px-1 text-xs text-neutral-500">مدل فعالی در دسترس نیست.</p>
              ) : (
                <label className="mb-2 block px-1">
                  <span className="label">گفت‌وگوی جدید با</span>
                  <select
                    className="input"
                    defaultValue=""
                    disabled={createConversation.isPending}
                    onChange={(e) => {
                      if (e.target.value) startConversation(e.target.value);
                      e.target.value = '';
                    }}
                    aria-label="انتخاب مدل برای گفت‌وگوی جدید"
                  >
                    <option value="">انتخاب مدل…</option>
                    {textModels.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.display_name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <ul className="flex max-h-48 flex-col gap-1 overflow-y-auto lg:max-h-[60vh]">
                {(conversations.data ?? []).map((c) => (
                  <li key={c.id} className="group flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => setActiveId(c.id)}
                      aria-current={activeId === c.id ? 'true' : undefined}
                      className={`w-full rounded-xl px-3 py-2.5 text-start text-sm transition-colors ${
                        activeId === c.id
                          ? 'bg-brand-100 font-semibold text-brand-800 dark:bg-brand-900/40 dark:text-brand-300'
                          : 'hover:bg-neutral-100 dark:hover:bg-neutral-800'
                      }`}
                    >
                      <span className="block truncate">{c.title || 'گفت‌وگوی بدون عنوان'}</span>
                      <span className="block text-xs text-neutral-500 dark:text-slate-400">
                        {formatDateTime(c.updated_at)}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm('این گفت‌وگو حذف شود؟')) {
                          deleteConversation.mutate(c.id, {
                            onSuccess: () => {
                              if (activeId === c.id) setActiveId(null);
                            },
                            onError: () => toast('حذف گفت‌وگو ناموفق بود.', 'error'),
                          });
                        }
                      }}
                      aria-label={`حذف ${c.title || 'گفت‌وگو'}`}
                      className="shrink-0 rounded-lg px-2 py-2 text-neutral-400 opacity-0 transition-opacity hover:bg-red-50 hover:text-red-600 group-hover:opacity-100 dark:hover:bg-red-900/20"
                    >
                      🗑️
                    </button>
                  </li>
                ))}
              </ul>
              {(conversations.data ?? []).length === 0 && (
                <p className="px-1 py-3 text-xs text-neutral-500">هنوز گفت‌وگویی ندارید؛ از بالا یکی بسازید.</p>
              )}
            </div>
          </aside>

          {/* Thread */}
          <section aria-label="متن گفت‌وگو" className="card flex min-h-[50vh] flex-1 flex-col !p-0">
            {!activeId ? (
              <div className="p-6">
                <EmptyState icon="💬" title="گفت‌وگویی انتخاب نشده" description="یک گفت‌وگو را انتخاب کنید یا گفت‌وگوی جدیدی بسازید." />
              </div>
            ) : messages.isLoading ? (
              <LoadingSpinner />
            ) : messages.isError ? (
              <div className="p-6">
                <ErrorState message="بارگذاری پیام‌ها ناموفق بود." onRetry={() => messages.refetch()} />
              </div>
            ) : (
              <>
                <div className="flex-1 space-y-3 overflow-y-auto p-4" role="log" aria-live="polite" aria-label="پیام‌ها">
                  {(messages.data ?? []).length === 0 && (
                    <p className="py-8 text-center text-sm text-neutral-500">اولین پیام را بنویسید.</p>
                  )}
                  {(messages.data ?? []).map((m) => (
                    <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-start' : 'justify-end'}`}>
                      <div
                        className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-7 ${
                          m.role === 'user'
                            ? 'bg-brand-600 text-white dark:bg-brand-500 dark:text-navy-950'
                            : 'bg-neutral-100 text-neutral-900 dark:bg-navy-800 dark:text-slate-100'
                        }`}
                      >
                        <p className="whitespace-pre-wrap">{m.content}</p>
                        <p className={`mt-1 text-[11px] ${m.role === 'user' ? 'text-white/70 dark:text-navy-950/70' : 'text-neutral-400'}`}>
                          {formatDateTime(m.created_at)}
                        </p>
                      </div>
                    </div>
                  ))}
                  <div ref={bottomRef} />
                </div>

                <form onSubmit={handleSubmit(onSend)} className="border-t border-neutral-200 p-3 dark:border-white/10">
                  <div className="flex items-end gap-2">
                    <label htmlFor="chat-input" className="sr-only">
                      متن پیام
                    </label>
                    <textarea
                      id="chat-input"
                      rows={2}
                      placeholder="پیام خود را بنویسید…"
                      className="input flex-1 resize-none"
                      aria-invalid={!!errors.content}
                      {...register('content')}
                    />
                    <button
                      type="submit"
                      disabled={isSubmitting || sendMessage.isPending}
                      className="btn-primary shrink-0"
                      aria-label="ارسال پیام"
                    >
                      {isSubmitting || sendMessage.isPending ? '…' : 'ارسال'}
                    </button>
                  </div>
                  {errors.content && (
                    <p role="alert" className="field-error">
                      {errors.content.message}
                    </p>
                  )}
                </form>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}