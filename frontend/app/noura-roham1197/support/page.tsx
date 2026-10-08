/** Admin support messages: list, mark read, reply. */
'use client';

import { useEffect, useState } from 'react';

interface SupportMsg {
  id: string;
  platform: string;
  platform_user_id: number;
  user_id: string | null;
  message: string;
  is_read: boolean;
  admin_reply: string | null;
  created_at: string | null;
}

export default function SupportPage() {
  const [items, setItems] = useState<SupportMsg[]>([]);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [replying, setReplying] = useState<string | null>(null);
  const [replyText, setReplyText] = useState('');

  const load = async () => {
    const res = await fetch(`/api/v1/admin/support?unread_only=${unreadOnly}`, { credentials: 'include' });
    const data = await res.json();
    if (data.ok) setItems(data.data || []);
  };

  useEffect(() => { load(); }, [unreadOnly]);

  const markRead = async (id: string) => {
    await fetch(`/api/v1/admin/support/${id}/read`, { method: 'POST', credentials: 'include' });
    load();
  };

  const sendReply = async (id: string) => {
    if (!replyText.trim()) return;
    await fetch(`/api/v1/admin/support/${id}/reply`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reply: replyText.trim() }),
    });
    setReplying(null);
    setReplyText('');
    load();
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold">پیام‌های پشتیبانی</h1>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={unreadOnly} onChange={e => setUnreadOnly(e.target.checked)} />
          فقط خوانده‌نشده‌ها
        </label>
      </div>
      <div className="space-y-3">
        {items.map(m => (
          <div key={m.id} className={`border rounded-lg p-4 ${m.is_read ? 'bg-gray-50' : 'bg-yellow-50 border-yellow-300'}`}>
            <div className="flex justify-between text-xs text-gray-500 mb-2">
              <span>{m.platform} / {m.platform_user_id}</span>
              <span>{m.created_at ? new Date(m.created_at).toLocaleString('fa-IR') : ''}</span>
            </div>
            <p className="mb-2">{m.message}</p>
            {m.admin_reply && (
              <p className="text-sm text-green-700 bg-green-50 rounded p-2 mb-2">پاسخ: {m.admin_reply}</p>
            )}
            <div className="flex gap-2">
              {!m.is_read && (
                <button onClick={() => markRead(m.id)} className="text-xs bg-gray-200 rounded px-3 py-1">
                  خوانده شد
                </button>
              )}
              {replying === m.id ? (
                <div className="flex gap-2 flex-1">
                  <input
                    value={replyText}
                    onChange={e => setReplyText(e.target.value)}
                    placeholder="پاسخ..."
                    className="flex-1 border rounded px-2 py-1 text-sm"
                  />
                  <button onClick={() => sendReply(m.id)} className="text-xs bg-blue-600 text-white rounded px-3 py-1">
                    ارسال
                  </button>
                  <button onClick={() => setReplying(null)} className="text-xs bg-gray-200 rounded px-3 py-1">
                    لغو
                  </button>
                </div>
              ) : (
                <button onClick={() => setReplying(m.id)} className="text-xs bg-blue-100 rounded px-3 py-1">
                  پاسخ
                </button>
              )}
            </div>
          </div>
        ))}
        {items.length === 0 && <p className="text-gray-500 text-center py-8">پیامی نیست.</p>}
      </div>
    </div>
  );
}
