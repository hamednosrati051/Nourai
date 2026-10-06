'use client';

import { ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import {
  useBlocklistWords,
  useCreateBlocklistWord,
  useDeleteBlocklistWord,
  usePromptFilter,
  useSetPromptFilter,
  useUpdateBlocklistWord,
  type PromptBlocklistWord,
} from '@/features/admin/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { Pagination } from '@/components/Pagination';
import { useToast } from '@/components/Toast';
import { formatDateTime } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';

/** Admin prompt filter: global kill switch + blocklist word management. */
export default function PromptFilterPage() {
  const { toast } = useToast();
  const filter = usePromptFilter();
  const setFilter = useSetPromptFilter();
  const createWord = useCreateBlocklistWord();
  const updateWord = useUpdateBlocklistWord();
  const deleteWord = useDeleteBlocklistWord();

  const [phrase, setPhrase] = useState('');
  const [category, setCategory] = useState('');
  const [page, setPage] = useState(1);
  const words = useBlocklistWords(page, 20);
  const [editing, setEditing] = useState<PromptBlocklistWord | null>(null);
  const [editPhrase, setEditPhrase] = useState('');
  const [editCategory, setEditCategory] = useState('');

  const errMsg = (err: unknown, fallback: string) =>
    toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : fallback, 'error');

  const onToggleEnabled = () => {
    const next = !(filter.data?.enabled ?? true);
    setFilter.mutate(next, {
      onSuccess: () => toast(next ? 'فیلتر پرامت فعال شد.' : 'فیلتر پرامت غیرفعال شد.', 'success'),
      onError: (err) => errMsg(err, 'تغییر وضعیت ناموفق بود.'),
    });
  };

  const onAdd = () => {
    const p = phrase.trim();
    if (!p) return;
    createWord.mutate(
      { phrase: p, category: category.trim() || undefined },
      {
        onSuccess: () => {
          setPhrase('');
          setCategory('');
          toast('عبارت اضافه شد.', 'success');
        },
        onError: (err) => errMsg(err, 'افزودن ناموفق بود.'),
      },
    );
  };

  const startEdit = (w: PromptBlocklistWord) => {
    setEditing(w);
    setEditPhrase(w.phrase);
    setEditCategory(w.category ?? '');
  };

  const onSaveEdit = () => {
    if (!editing) return;
    const p = editPhrase.trim();
    if (!p) return;
    updateWord.mutate(
      { id: editing.id, patch: { phrase: p, category: editCategory.trim() || null } },
      {
        onSuccess: () => {
          setEditing(null);
          toast('ویرایش شد.', 'success');
        },
        onError: (err) => errMsg(err, 'ویرایش ناموفق بود.'),
      },
    );
  };

  const onToggleActive = (w: PromptBlocklistWord) => {
    updateWord.mutate(
      { id: w.id, patch: { is_active: !w.is_active } },
      { onError: (err) => errMsg(err, 'تغییر وضعیت ناموفق بود.') },
    );
  };

  const onDelete = (w: PromptBlocklistWord) => {
    if (!window.confirm(`عبارت «${w.phrase}» حذف شود؟`)) return;
    deleteWord.mutate(w.id, {
      onSuccess: () => toast('حذف شد.', 'success'),
      onError: (err) => errMsg(err, 'حذف ناموفق بود.'),
    });
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-extrabold">فیلتر پرامت</h1>
        <p className="mt-1 text-sm text-neutral-600 dark:text-slate-400">
          پرامت‌هایی که شامل عبارات این لیست باشند، قبل از ساخت جاب رد می‌شوند — بدون hold کیف پول و بدون هزینه provider.
        </p>
      </div>

      {/* Global kill switch */}
      <section className="card flex items-center justify-between gap-4" aria-label="وضعیت کلی فیلتر">
        <div>
          <h2 className="font-bold">فیلتر پرامت</h2>
          <p className="text-xs text-neutral-500 dark:text-slate-400">
            {filter.data?.enabled ? 'فعال است — پرامت‌ها بررسی می‌شوند.' : 'غیرفعال است — هیچ پرامتی بررسی نمی‌شود.'}
          </p>
        </div>
        <button
          type="button"
          onClick={onToggleEnabled}
          disabled={filter.isLoading || setFilter.isPending}
          aria-pressed={!!filter.data?.enabled}
          className={`btn-sm rounded-full px-5 font-bold transition-colors ${
            filter.data?.enabled ? 'btn-primary' : 'btn-secondary'
          }`}
        >
          {filter.data?.enabled ? 'فعال' : 'غیرفعال'}
        </button>
      </section>

      {/* Add form */}
      <section className="card" aria-label="افزودن عبارت">
        <h2 className="mb-3 font-bold">افزودن عبارت جدید</h2>
        <div className="flex flex-col gap-2 sm:flex-row">
          <input
            className="input flex-1"
            placeholder="عبارت (فارسی یا انگلیسی)…"
            value={phrase}
            onChange={(e) => setPhrase(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && onAdd()}
          />
          <input
            className="input sm:w-44"
            placeholder="دسته‌بندی (اختیاری)"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && onAdd()}
          />
          <button
            type="button"
            onClick={onAdd}
            disabled={createWord.isPending || !phrase.trim()}
            className="btn-primary btn-sm shrink-0"
          >
            ＋ افزودن
          </button>
        </div>
      </section>

      {/* Word list */}
      <section aria-label="فهرست عبارات">
        {words.isLoading && <LoadingSpinner />}
        {words.isError && <ErrorState message="بارگذاری فهرست ناموفق بود." onRetry={() => words.refetch()} />}
        {words.data && words.data.items.length === 0 && (
          <EmptyState icon={ShieldCheck} title="لیستی خالی است" description="هنوز عبارتی ثبت نشده است." />
        )}
        {words.data && words.data.items.length > 0 && (
          <>
          <ul className="flex flex-col gap-2">
            {words.data.items.map((w) => (
              <li key={w.id} className="card flex flex-wrap items-center gap-3 !p-3">
                {editing?.id === w.id ? (
                  <>
                    <input
                      className="input min-w-40 flex-1"
                      value={editPhrase}
                      onChange={(e) => setEditPhrase(e.target.value)}
                    />
                    <input
                      className="input w-36"
                      placeholder="دسته‌بندی"
                      value={editCategory}
                      onChange={(e) => setEditCategory(e.target.value)}
                    />
                    <button
                      type="button"
                      onClick={onSaveEdit}
                      disabled={updateWord.isPending || !editPhrase.trim()}
                      className="btn-primary btn-sm"
                    >
                      ذخیره
                    </button>
                    <button type="button" onClick={() => setEditing(null)} className="btn-secondary btn-sm">
                      انصراف
                    </button>
                  </>
                ) : (
                  <>
                    <span className="min-w-40 flex-1 font-semibold" dir="auto">
                      {w.phrase}
                    </span>
                    {w.category && (
                      <span className="badge badge-info">{w.category}</span>
                    )}
                    <span className="text-xs text-neutral-500 dark:text-slate-400">
                      {formatDateTime(w.created_at)}
                    </span>
                    <button
                      type="button"
                      onClick={() => onToggleActive(w)}
                      aria-pressed={w.is_active}
                      title={w.is_active ? 'غیرفعال کردن' : 'فعال کردن'}
                      className={`btn-sm rounded-full px-4 font-bold ${
                        w.is_active ? 'btn-primary' : 'btn-secondary'
                      }`}
                    >
                      {w.is_active ? 'فعال' : 'غیرفعال'}
                    </button>
                    <button type="button" onClick={() => startEdit(w)} className="btn-secondary btn-sm">
                      ویرایش
                    </button>
                    <button type="button" onClick={() => onDelete(w)} className="btn-danger btn-sm">
                      حذف
                    </button>
                  </>
                )}
              </li>
            ))}
          </ul>
          <Pagination
            page={page}
            totalPages={words.data.meta.total_pages}
            onPageChange={setPage}
          />
          </>
        )}
      </section>
    </div>
  );
}
