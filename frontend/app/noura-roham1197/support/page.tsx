/** Admin support messages: list, mark read, reply. */
'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '@/lib/api';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';

interface SupportMsg {
  id: string;
  platform: string;
  platform_user_id: number;
  platform_username: string | null;
  user_id: string | null;
  message: string;
  is_read: boolean;
  admin_reply: string | null;
  created_at: string | null;
}

interface SupportListResponse {
  items: SupportMsg[];
}

export default function SupportPage() {
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [replying, setReplying] = useState<string | null>(null);
  const [replyText, setReplyText] = useState('');
  const queryClient = useQueryClient();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['admin', 'support', unreadOnly],
    queryFn: () =>
      apiGet<SupportListResponse>(
        `/admin/support${unreadOnly ? '?unread_only=true' : ''}`
      ),
  });

  const markReadMutation = useMutation({
    mutationFn: (id: string) => apiPost(`/admin/support/${id}/read`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'support'] });
    },
  });

  const replyMutation = useMutation({
    mutationFn: ({ id, reply }: { id: string; reply: string }) =>
      apiPost(`/admin/support/${id}/reply`, { reply }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'support'] });
      setReplying(null);
      setReplyText('');
    },
  });

  const items = data?.items || [];

  const sendReply = (id: string) => {
    if (!replyText.trim()) return;
    replyMutation.mutate({ id, reply: replyText.trim() });
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-extrabold">پیام‌های پشتیبانی</h1>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={unreadOnly}
            onChange={(e) => setUnreadOnly(e.target.checked)}
          />
          فقط خوانده‌نشده‌ها
        </label>
      </div>

      {isLoading ? (
        <LoadingSpinner />
      ) : isError ? (
        <ErrorState message="خطا در بارگذاری پیام‌ها" onRetry={() => refetch()} />
      ) : items.length === 0 ? (
        <EmptyState title="پیامی نیست" />
      ) : (
        <div className="space-y-3">
          {items.map((m) => (
            <div
              key={m.id}
              className={`card ${m.is_read ? '' : 'border-warning'}`}
            >
              <div className="flex justify-between text-xs text-neutral-500 mb-2">
                <span dir="ltr">
                  {m.platform} / {m.platform_user_id}
                  {m.platform_username && ` / @${m.platform_username}`}
                </span>
                <span>
                  {m.created_at
                    ? new Date(m.created_at).toLocaleString('fa-IR')
                    : ''}
                </span>
              </div>
              <p className="mb-2">{m.message}</p>
              {m.admin_reply && (
                <p className="text-sm bg-success/10 text-success rounded p-2 mb-2">
                  پاسخ: {m.admin_reply}
                </p>
              )}
              <div className="flex gap-2">
                {!m.is_read && (
                  <button
                    onClick={() => markReadMutation.mutate(m.id)}
                    disabled={markReadMutation.isPending}
                    className="btn btn-sm btn-ghost"
                  >
                    خوانده شد
                  </button>
                )}
                {replying === m.id ? (
                  <div className="flex gap-2 flex-1">
                    <input
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                      placeholder="پاسخ..."
                      className="input input-sm flex-1"
                    />
                    <button
                      onClick={() => sendReply(m.id)}
                      disabled={replyMutation.isPending}
                      className="btn btn-sm btn-primary"
                    >
                      ارسال
                    </button>
                    <button
                      onClick={() => setReplying(null)}
                      className="btn btn-sm btn-ghost"
                    >
                      لغو
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => setReplying(m.id)}
                    className="btn btn-sm btn-ghost"
                  >
                    پاسخ
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
