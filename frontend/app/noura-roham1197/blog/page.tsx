'use client';

import { Newspaper, Pencil, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import {
  useAdminBlogPosts,
  useCreateBlogPost,
  useDeleteBlogPost,
  useUpdateBlogPost,
  type AdminBlogPost,
} from '@/features/admin/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { useToast } from '@/components/Toast';
import { formatDateTime } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';

const EMPTY_FORM = { slug: '', title: '', description: '', content: '', is_published: false };

/** Admin blog management: list, create, edit, publish, delete. */
export default function BlogAdminPage() {
  const { toast } = useToast();
  const posts = useAdminBlogPosts();
  const createPost = useCreateBlogPost();
  const updatePost = useUpdateBlogPost();
  const deletePost = useDeleteBlogPost();

  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<AdminBlogPost | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);

  const errMsg = (err: unknown, fallback: string) =>
    toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : fallback, 'error');

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
  };

  const openEdit = (p: AdminBlogPost) => {
    setEditing(p);
    setForm({
      slug: p.slug,
      title: p.title,
      description: p.description,
      content: p.content.join('\n\n'),
      is_published: p.is_published,
    });
    setShowForm(true);
  };

  const onSubmit = () => {
    const payload = {
      slug: form.slug.trim(),
      title: form.title.trim(),
      description: form.description.trim(),
      content: form.content.split(/\n\s*\n/).map((s) => s.trim()).filter(Boolean),
      is_published: form.is_published,
    };
    if (!payload.slug || !payload.title) {
      toast('نامک و عنوان الزامی است.', 'error');
      return;
    }
    if (editing) {
      updatePost.mutate(
        { id: editing.id, patch: payload },
        {
          onSuccess: () => { setShowForm(false); toast('پست به‌روز شد.', 'success'); },
          onError: (err) => errMsg(err, 'به‌روزرسانی ناموفق بود.'),
        },
      );
    } else {
      createPost.mutate(payload, {
        onSuccess: () => { setShowForm(false); toast('پست ساخته شد.', 'success'); },
        onError: (err) => errMsg(err, 'ساخت پست ناموفق بود.'),
      });
    }
  };

  const onDelete = (p: AdminBlogPost) => {
    if (!confirm(`«${p.title}» حذف شود؟`)) return;
    deletePost.mutate(p.id, {
      onSuccess: () => toast('پست حذف شد.', 'success'),
      onError: (err) => errMsg(err, 'حذف ناموفق بود.'),
    });
  };

  const onTogglePublish = (p: AdminBlogPost) => {
    updatePost.mutate(
      { id: p.id, patch: { is_published: !p.is_published } },
      {
        onSuccess: () => toast(p.is_published ? 'پست از انتشار خارج شد.' : 'پست منتشر شد.', 'success'),
        onError: (err) => errMsg(err, 'تغییر وضعیت ناموفق بود.'),
      },
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-extrabold">مدیریت بلاگ</h1>
        <button type="button" onClick={openCreate} className="btn-primary btn-sm">
          <Plus className="h-4 w-4" /> پست جدید
        </button>
      </div>

      {posts.isLoading && <LoadingSpinner label="در حال بارگذاری…" />}
      {posts.isError && <ErrorState message="بارگذاری ناموفق بود." onRetry={() => posts.refetch()} />}
      {posts.data && posts.data.length === 0 && (
        <EmptyState icon={Newspaper} title="پستی نیست" description="اولین پست بلاگ را بسازید." />
      )}

      {posts.data && posts.data.length > 0 && (
        <div className="flex flex-col gap-3">
          {posts.data.map((p) => (
            <div key={p.id} className="card flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="font-bold truncate">{p.title}</p>
                <p className="mt-1 text-xs text-neutral-500">
                  /blog/{p.slug} · {formatDateTime(p.created_at)}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className={`badge ${p.is_published ? 'badge-success' : 'badge-warning'}`}>
                  {p.is_published ? 'منتشرشده' : 'پیش‌نویس'}
                </span>
                <button
                  type="button"
                  onClick={() => onTogglePublish(p)}
                  className="btn-secondary btn-sm"
                >
                  {p.is_published ? 'لغو انتشار' : 'انتشار'}
                </button>
                <button
                  type="button"
                  onClick={() => openEdit(p)}
                  className="btn-secondary btn-sm"
                  aria-label="ویرایش"
                >
                  <Pencil className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(p)}
                  className="btn-danger btn-sm"
                  aria-label="حذف"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setShowForm(false)}>
          <div className="card max-h-[90vh] w-full max-w-2xl overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h2 className="mb-4 text-lg font-extrabold">{editing ? 'ویرایش پست' : 'پست جدید'}</h2>
            <div className="flex flex-col gap-4">
              <div>
                <label className="label">نامک (slug)</label>
                <input
                  className="input"
                  value={form.slug}
                  onChange={(e) => setForm({ ...form, slug: e.target.value })}
                  placeholder="what-is-ai"
                  dir="ltr"
                />
              </div>
              <div>
                <label className="label">عنوان</label>
                <input
                  className="input"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                />
              </div>
              <div>
                <label className="label">توضیح کوتاه</label>
                <input
                  className="input"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                />
              </div>
              <div>
                <label className="label">متن (هر پاراگراف با یک خط خالی جدا شود)</label>
                <textarea
                  className="input min-h-48"
                  value={form.content}
                  onChange={(e) => setForm({ ...form, content: e.target.value })}
                  rows={10}
                />
              </div>
              <label className="flex cursor-pointer items-center gap-2 text-sm font-bold">
                <input
                  type="checkbox"
                  checked={form.is_published}
                  onChange={(e) => setForm({ ...form, is_published: e.target.checked })}
                  className="h-4 w-4"
                />
                منتشر شود
              </label>
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setShowForm(false)} className="btn-secondary">
                  انصراف
                </button>
                <button
                  type="button"
                  onClick={onSubmit}
                  className="btn-primary"
                  disabled={createPost.isPending || updatePost.isPending}
                >
                  {editing ? 'ذخیره' : 'ساخت'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
