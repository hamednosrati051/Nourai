'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useAdminModels, useCreateAdminModel, useUpdateAdminModel } from '@/features/admin/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { ResponsiveTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { useToast } from '@/components/Toast';
import { formatDateTime } from '@/lib/format';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { AiModel, ModelService } from '@/types/api';

const SERVICE_LABELS: Record<ModelService, string> = { text: 'متن', audio: 'صوت', image: 'تصویر' };

const modelSchema = z.object({
  name: z.string().trim().min(1, 'نام مدل را وارد کنید.'),
  service: z.enum(['text', 'audio', 'image']),
  provider: z.string().trim().min(1, 'نام provider را وارد کنید.'),
  pricing_hint: z.string().trim().optional(),
  tokenizer_encoding: z.string().trim().optional(),
  is_active: z.boolean(),
});
type ModelForm = z.infer<typeof modelSchema>;

/** Admin model catalog: enable/disable, edit, create. */
export default function AdminModelsPage() {
  const { toast } = useToast();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<AiModel | null>(null);

  const models = useAdminModels();
  const createModel = useCreateAdminModel();
  const updateModel = useUpdateAdminModel();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ModelForm>({ resolver: zodResolver(modelSchema) });

  const openCreate = () => {
    setEditing(null);
    reset({ name: '', service: 'text', provider: '', pricing_hint: '', tokenizer_encoding: '', is_active: true });
    setModalOpen(true);
  };

  const openEdit = (m: AiModel) => {
    setEditing(m);
    reset({
      name: m.name,
      service: m.service,
      provider: m.provider,
      pricing_hint: m.pricing_hint ?? '',
      tokenizer_encoding: m.tokenizer_encoding ?? '',
      is_active: m.is_active,
    });
    setModalOpen(true);
  };

  const onSubmit = (values: ModelForm) => {
    const done = {
      onSuccess: () => {
        setModalOpen(false);
        toast(editing ? 'مدل به‌روزرسانی شد.' : 'مدل جدید ثبت شد.', 'success');
      },
      onError: (err: unknown) =>
        toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'خطایی رخ داد.', 'error'),
    };
    if (editing) updateModel.mutate({ id: editing.id, patch: values }, done);
    else createModel.mutate(values, done);
  };

  const toggleActive = (m: AiModel) => {
    updateModel.mutate(
      { id: m.id, patch: { is_active: !m.is_active } },
      {
        onSuccess: () => toast(m.is_active ? 'مدل غیرفعال شد.' : 'مدل فعال شد.', 'success'),
        onError: (err) =>
          toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'خطایی رخ داد.', 'error'),
      },
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold">مدل‌ها</h1>
        <button type="button" onClick={openCreate} className="btn-primary btn-sm">
          مدل جدید
        </button>
      </div>

      {models.isLoading && <LoadingSpinner />}
      {models.isError && <ErrorState message="بارگذاری مدل‌ها ناموفق بود." onRetry={() => models.refetch()} />}
      {models.data && models.data.length === 0 && (
        <EmptyState icon="🤖" title="مدلی ثبت نشده" description="هنوز مدلی در کاتالوگ ثبت نشده است." />
      )}
      {models.data && models.data.length > 0 && (
        <ResponsiveTable
          ariaLabel="فهرست مدل‌ها"
          keyOf={(m) => m.id}
          rows={models.data}
          cardHeader={(m) => m.name}
          columns={[
            { header: 'نام', render: (m) => <span className="font-semibold">{m.name}</span> },
            { header: 'سرویس', render: (m) => SERVICE_LABELS[m.service] },
            { header: 'provider', render: (m) => <span dir="ltr">{m.provider}</span>, hideOnCard: true },
            {
              header: 'وضعیت',
              render: (m) => (m.is_active ? <span className="badge-success">فعال</span> : <span className="badge-neutral">غیرفعال</span>),
            },
            { header: 'راهنمای قیمت', render: (m) => m.pricing_hint ?? '—', hideOnCard: true },
            { header: 'به‌روزرسانی', render: (m) => formatDateTime(m.updated_at), hideOnCard: true },
            {
              header: 'اقدام',
              render: (m) => (
                <div className="flex gap-2">
                  <button type="button" onClick={() => toggleActive(m)} className="btn-secondary btn-sm" disabled={updateModel.isPending}>
                    {m.is_active ? 'غیرفعال' : 'فعال'}
                  </button>
                  <button type="button" onClick={() => openEdit(m)} className="btn-ghost btn-sm">
                    ویرایش
                  </button>
                </div>
              ),
            },
          ]}
        />
      )}

      <Modal open={modalOpen} title={editing ? 'ویرایش مدل' : 'مدل جدید'} onClose={() => setModalOpen(false)}>
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-4" noValidate>
          <div>
            <label htmlFor="model-name" className="label">نام مدل</label>
            <input id="model-name" className={`input ${errors.name ? 'input-error' : ''}`} {...register('name')} />
            {errors.name && <p role="alert" className="field-error">{errors.name.message}</p>}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="model-service" className="label">سرویس</label>
              <select id="model-service" className="input" {...register('service')}>
                <option value="text">متن</option>
                <option value="audio">صوت</option>
                <option value="image">تصویر</option>
              </select>
            </div>
            <div>
              <label htmlFor="model-provider" className="label">provider</label>
              <input id="model-provider" dir="ltr" className={`input text-left ${errors.provider ? 'input-error' : ''}`} {...register('provider')} />
              {errors.provider && <p role="alert" className="field-error">{errors.provider.message}</p>}
            </div>
          </div>
          <div>
            <label htmlFor="model-pricing" className="label">راهنمای قیمت (نمایشی برای کاربر)</label>
            <input id="model-pricing" className="input" placeholder="مثلاً: هر ۱۰۰۰ توکن ۵۰۰ تومان" {...register('pricing_hint')} />
          </div>
          <div>
            <label htmlFor="model-encoding" className="label">encoding توکنایزر (tiktoken)</label>
            <input id="model-encoding" dir="ltr" className="input text-left" placeholder="مثلاً: cl100k_base" {...register('tokenizer_encoding')} />
            <p className="field-hint">باید با tiktoken.get_encoding() معتبر باشد؛ در runtime fallback وجود ندارد.</p>
          </div>
          <label className="flex items-center gap-2 text-sm font-medium">
            <input type="checkbox" className="h-5 w-5 accent-amber-600" {...register('is_active')} />
            مدل فعال باشد
          </label>
          <div className="flex gap-2">
            <button type="submit" disabled={isSubmitting} className="btn-primary flex-1">
              {isSubmitting ? 'در حال ثبت…' : 'ذخیره'}
            </button>
            <button type="button" onClick={() => setModalOpen(false)} className="btn-secondary flex-1">
              انصراف
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
