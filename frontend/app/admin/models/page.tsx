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
import type { AiModel, ModelCapability } from '@/types/api';

const CAPABILITY_LABELS: Record<ModelCapability, string> = {
  text: 'متن',
  speech_to_text: 'گفتار → متن',
  text_to_speech: 'متن → گفتار',
  image: 'تصویر',
};

const CAPABILITIES = Object.keys(CAPABILITY_LABELS) as ModelCapability[];

const modelSchema = z.object({
  slug: z
    .string()
    .trim()
    .min(1, 'شناسه یکتا (slug) را وارد کنید.')
    .regex(/^[a-z0-9][a-z0-9-_]*$/, 'فقط حروف کوچک انگلیسی، عدد، خط تیره و زیرخط.'),
  display_name: z.string().trim().min(1, 'نام نمایشی مدل را وارد کنید.'),
  capability: z.enum(['text', 'speech_to_text', 'text_to_speech', 'image']),
  provider_key: z.string().trim().min(1, 'کلید provider را وارد کنید (مثلاً: metis).'),
  provider_model_name: z.string().trim().min(1, 'نام مدل در سمت provider را وارد کنید.'),
  pricing_type: z.string().trim().min(1, 'نوع قیمت‌گذاری را وارد کنید.'),
  tokenizer_encoding: z.string().trim().optional(),
  description: z.string().trim().optional(),
  base_url: z.string().trim().optional(),
  api_key: z.string().trim().optional(),
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
    reset({
      slug: '',
      display_name: '',
      capability: 'text',
      provider_key: '',
      provider_model_name: '',
      pricing_type: 'token',
      tokenizer_encoding: '',
      description: '',
      base_url: '',
      api_key: '',
      is_active: true,
    });
    setModalOpen(true);
  };

  const openEdit = (m: AiModel) => {
    setEditing(m);
    reset({
      slug: m.slug,
      display_name: m.display_name,
      capability: m.capability,
      provider_key: m.provider_key,
      provider_model_name: m.provider_model_name,
      pricing_type: m.pricing_type,
      tokenizer_encoding: m.tokenizer_encoding ?? '',
      description: m.description ?? '',
      base_url: '',
      api_key: '',
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
    if (editing) {
      // PATCH only accepts: display_name, provider_model_name, pricing_type,
      // tokenizer_encoding, config_json, description, is_active (+ credentials).
      updateModel.mutate(
        {
          id: editing.id,
          patch: {
            display_name: values.display_name.trim(),
            provider_model_name: values.provider_model_name.trim(),
            pricing_type: values.pricing_type.trim(),
            ...(values.tokenizer_encoding?.trim()
              ? { tokenizer_encoding: values.tokenizer_encoding.trim() }
              : {}),
            ...(values.description?.trim() ? { description: values.description.trim() } : {}),
            ...(values.base_url?.trim() || values.api_key?.trim()
              ? {
                  base_url: values.base_url?.trim() || '',
                  api_key: values.api_key?.trim() || '',
                }
              : {}),
            is_active: values.is_active,
          },
        },
        done,
      );
    } else {
      createModel.mutate(
        {
          slug: values.slug.trim(),
          display_name: values.display_name.trim(),
          capability: values.capability,
          provider_key: values.provider_key.trim(),
          provider_model_name: values.provider_model_name.trim(),
          pricing_type: values.pricing_type.trim(),
          ...(values.tokenizer_encoding?.trim()
            ? { tokenizer_encoding: values.tokenizer_encoding.trim() }
            : {}),
          ...(values.description?.trim() ? { description: values.description.trim() } : {}),
          ...(values.base_url?.trim() || values.api_key?.trim()
            ? {
                base_url: values.base_url?.trim() || '',
                api_key: values.api_key?.trim() || '',
              }
            : {}),
          is_active: values.is_active,
        },
        done,
      );
    }
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
          cardHeader={(m) => m.display_name}
          columns={[
            { header: 'نام نمایشی', render: (m) => <span className="font-semibold">{m.display_name}</span> },
            { header: 'قابلیت', render: (m) => CAPABILITY_LABELS[m.capability] ?? m.capability },
            { header: 'provider', render: (m) => <span dir="ltr">{m.provider_key}</span>, hideOnCard: true },
            {
              header: 'نام مدل در provider',
              render: (m) => <span dir="ltr" className="text-xs">{m.provider_model_name}</span>,
              hideOnCard: true,
            },
            {
              header: 'وضعیت',
              render: (m) => (m.is_active ? <span className="badge-success">فعال</span> : <span className="badge-neutral">غیرفعال</span>),
            },
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
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="model-slug" className="label">شناسه یکتا (slug)</label>
              <input
                id="model-slug"
                dir="ltr"
                placeholder="gpt-4-1-mini"
                disabled={!!editing}
                className={`input text-left ${errors.slug ? 'input-error' : ''}`}
                {...register('slug')}
              />
              {errors.slug && <p role="alert" className="field-error">{errors.slug.message}</p>}
              {editing && <p className="field-hint">شناسه یکتا پس از ثبت قابل تغییر نیست.</p>}
            </div>
            <div>
              <label htmlFor="model-display-name" className="label">نام نمایشی</label>
              <input
                id="model-display-name"
                className={`input ${errors.display_name ? 'input-error' : ''}`}
                {...register('display_name')}
              />
              {errors.display_name && <p role="alert" className="field-error">{errors.display_name.message}</p>}
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="model-capability" className="label">قابلیت</label>
              <select id="model-capability" className="input" disabled={!!editing} {...register('capability')}>
                {CAPABILITIES.map((c) => (
                  <option key={c} value={c}>
                    {CAPABILITY_LABELS[c]}
                  </option>
                ))}
              </select>
              {editing && <p className="field-hint">قابلیت پس از ثبت قابل تغییر نیست.</p>}
            </div>
            <div>
              <label htmlFor="model-provider-key" className="label">کلید provider</label>
              <input
                id="model-provider-key"
                dir="ltr"
                placeholder="metis"
                disabled={!!editing}
                className={`input text-left ${errors.provider_key ? 'input-error' : ''}`}
                {...register('provider_key')}
              />
              {errors.provider_key && <p role="alert" className="field-error">{errors.provider_key.message}</p>}
              {editing && <p className="field-hint">کلید provider پس از ثبت قابل تغییر نیست.</p>}
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="model-provider-name" className="label">نام مدل در provider</label>
              <input
                id="model-provider-name"
                dir="ltr"
                placeholder="gpt-4.1-mini"
                className={`input text-left ${errors.provider_model_name ? 'input-error' : ''}`}
                {...register('provider_model_name')}
              />
              {errors.provider_model_name && <p role="alert" className="field-error">{errors.provider_model_name.message}</p>}
              <p className="field-hint">دقیقاً همان نامی که provider می‌شناسد.</p>
            </div>
            <div>
              <label htmlFor="model-pricing-type" className="label">نوع قیمت‌گذاری</label>
              <input
                id="model-pricing-type"
                dir="ltr"
                className={`input text-left ${errors.pricing_type ? 'input-error' : ''}`}
                {...register('pricing_type')}
              />
              {errors.pricing_type && <p role="alert" className="field-error">{errors.pricing_type.message}</p>}
            </div>
          </div>
          <div>
            <label htmlFor="model-encoding" className="label">encoding توکنایزر (tiktoken)</label>
            <input
              id="model-encoding"
              dir="ltr"
              className="input text-left"
              placeholder="مثلاً: o200k_base"
              {...register('tokenizer_encoding')}
            />
            <p className="field-hint">باید با tiktoken.get_encoding() معتبر باشد؛ برای مدل‌های متنی لازم است.</p>
          </div>
          <div>
            <label htmlFor="model-description" className="label">توضیحات</label>
            <textarea id="model-description" rows={2} className="input" {...register('description')} />
          </div>
          <div className="rounded-lg border border-neutral-200 p-4 dark:border-slate-700">
            <h3 className="mb-3 text-sm font-bold">اتصال provider</h3>
            <div className="flex flex-col gap-4">
              <div>
                <label htmlFor="model-base-url" className="label">آدرس endpoint (base URL)</label>
                <input
                  id="model-base-url"
                  dir="ltr"
                  placeholder="https://api.example.com/v1"
                  className="input text-left"
                  {...register('base_url')}
                />
                <p className="field-hint">اگر خالی باشد، از متغیر محیطی AI_PROVIDER_&lt;KEY&gt;_BASE_URL استفاده می‌شود.</p>
              </div>
              <div>
                <label htmlFor="model-api-key" className="label">کلید API</label>
                <input
                  id="model-api-key"
                  type="password"
                  dir="ltr"
                  autoComplete="off"
                  placeholder={editing?.has_credentials ? '•••••••• (ذخیره شده)' : ''}
                  className="input text-left"
                  {...register('api_key')}
                />
                {editing?.has_credentials ? (
                  <p className="field-hint">کلید قبلاً ذخیره شده؛ فقط برای تغییر، مقدار جدید وارد کنید.</p>
                ) : (
                  <p className="field-hint">اگر خالی باشد، از متغیر محیطی AI_PROVIDER_&lt;KEY&gt;_API_KEY استفاده می‌شود.</p>
                )}
              </div>
            </div>
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
