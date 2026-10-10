'use client';

import { useEffect, useState } from 'react';
import { Send, X, Check } from 'lucide-react';
import { apiGet, apiPost } from '@/lib/api';
import { useToast } from '@/components/Toast';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';

interface QueueItem {
  id: string;
  content_type: 'gallery' | 'blog';
  content_id: string;
  status: string;
  caption: string | null;
  created_at: string | null;
  image_url?: string;
  prompt?: string;
  title?: string;
  description?: string;
  slug?: string;
}

export default function BaleQueuePage() {
  const { toast } = useToast();
  const [items, setItems] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionId, setActionId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await apiGet<{ items: QueueItem[] }>('/api/v1/admin/bale-queue?status=pending');
      setItems(res.items || []);
    } catch (e) {
      toast('خطا در بارگذاری صف', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const handleApprove = async (id: string) => {
    setActionId(id);
    try {
      await apiPost(`/api/v1/admin/bale-queue/${id}/approve`, {});
      toast('تایید و منتشر شد', 'success');
      load();
    } catch (e) {
      toast('خطا در تایید', 'error');
    } finally {
      setActionId(null);
    }
  };

  const handleReject = async (id: string) => {
    setActionId(id);
    try {
      await apiPost(`/api/v1/admin/bale-queue/${id}/reject`, {});
      toast('رد شد', 'success');
      load();
    } catch (e) {
      toast('خطا در رد', 'error');
    } finally {
      setActionId(null);
    }
  };

  if (loading) return <LoadingSpinner label="در حال بارگذاری…" />;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-extrabold flex items-center gap-2 mb-6">
        <Send className="h-6 w-6" />
        صف انتشار کانال بله
      </h1>

      {items.length === 0 ? (
        <EmptyState icon={Send} title="صف خالی است" description="آیتمی در انتظار تایید نیست." />
      ) : (
        <div className="flex flex-col gap-4">
          {items.map((item) => (
            <div key={item.id} className="card p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <span className="text-xs px-2 py-1 rounded bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200">
                    {item.content_type === 'gallery' ? 'گالری' : 'بلاگ'}
                  </span>
                  {item.content_type === 'gallery' && item.image_url && (
                    <div className="mt-3">
                      <img src={item.image_url} alt="" className="max-h-48 rounded-lg" />
                      {item.prompt && (
                        <p className="text-sm text-neutral-500 mt-2">{item.prompt}</p>
                      )}
                    </div>
                  )}
                  {item.content_type === 'blog' && (
                    <div className="mt-3">
                      <h3 className="font-bold">{item.title}</h3>
                      <p className="text-sm text-neutral-500">{item.description}</p>
                    </div>
                  )}
                  {item.created_at && (
                    <p className="text-xs text-neutral-400 mt-2">
                      {new Date(item.created_at).toLocaleDateString('fa-IR')} — {new Date(item.created_at).toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' })}
                    </p>
                  )}
                </div>
                <div className="flex flex-col gap-2">
                  <button
                    onClick={() => handleApprove(item.id)}
                    disabled={actionId === item.id}
                    className="btn-primary btn-sm flex items-center gap-1"
                  >
                    <Check className="h-4 w-4" />
                    تایید و انتشار
                  </button>
                  <button
                    onClick={() => handleReject(item.id)}
                    disabled={actionId === item.id}
                    className="btn-ghost btn-sm flex items-center gap-1"
                  >
                    <X className="h-4 w-4" />
                    رد
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
