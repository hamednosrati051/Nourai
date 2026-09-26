'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  useAdminModels,
  useCreateAdminModel,
  useCreatePricingRule,
  useUpdateAdminModel,
} from '@/features/admin/hooks';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { ResponsiveTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { useToast } from '@/components/Toast';
import { formatDateTime } from '@/lib/format';
import { tomanToIrr } from '@/lib/currency';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { AiModel, ModelCapability } from '@/types/api';

const CAPABILITY_LABELS: Record<ModelCapability, string> = {
  text: 'متن',
  speech_to_text: 'گفتار → متن',
  text_to_speech: 'متن → گفتار',
  image: 'تصویر',
};

const CAPABILITIES = Object.keys(CAPABILITY_LABELS) as ModelCapability[];

/** Optional toman amount (quick pricing). Empty => no rule created. */
const optionalToman = z
  .union([z.number(), z.string()])
  .optional()
  .transform((v) => {
    if (v === undefined || v === '' || v === null) return undefined;
    const n = typeof v === 'string' ? Number(v) : v;
    return Number.isFinite(n) && n >= 0 ? n : undefined;
  });

const slugPattern = /^[a-z0-9][a-z0-9-_]*$/;

const modelSchema = z.object({
  display_name: z.string().trim().min(1, 'نام نمایشی مدل را وارد کنید.'),
  capability: z.enum(['text', 'speech_to_text', 'text_to_speech', 'image']),
  provider_model_name: z.string().trim().min(1, 'نام مدل در سمت provider را وارد کنید.'),
  base_url: z.string().trim().optional(),
  api_key: z.string().trim().optional(),
  // Quick pricing (toman) — create only. Empty = skip.
  input_price_toman: optionalToman,
  output_price_toman: optionalToman,
  audio_price_toman: optionalToman,
  image_price_toman: optionalToman,
  // Advanced (auto-filled when empty).
  slug: z
    .string()
    .trim()
    .optional()
    .refine((v) => !v || slugPattern.test(v), 'فقط حروف کوچک انگلیسی، عدد، خط تیره و زیرخط.'),
  provider_key: z.string().trim().optional(),
  tokenizer_encoding: z.string().trim().optional(),
  description: z.string().trim().optional(),
  is_active: z.boolean(),
});
type ModelForm = z.infer<typeof modelSchema>;

function slugify(value: string): string {
  return (
    value
      .toLowerCase()
      .trim()
      .replace(/[\s_]+/g, '-')
      .replace(/[^a-z0-9-]/g, '')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, 60)
  );
}

/** Admin model catalog: enable/disable, edit, create. */
export default function AdminModelsPage() {
  const { toast } = useToast();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<AiModel | null>(null);

  const models = useAdminModels();
  const createModel = useCreateAdminModel();
  const updateModel = useUpdateAdminModel();
  const createRule = useCreatePricingRule();

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<ModelForm>({ resolver: zodResolver(modelSchema) });
  const capability = watch('capability');

  const openCreate = () => {
    setEditing(null);
    reset({
      display_name: '',
      capability: 'text',
      provider_model_name: '',
      base_url: '',
      api_key: '',
      input_price_toman: undefined,
      output_price_toman: undefined,
      audio_price_toman: undefined,
      image_price_toman: undefined,
      slug: '',
      provider_key: '',
      tokenizer_encoding: '',
      description: '',
      is_active: true,
    });
    setModalOpen(true);
  };

  const openEdit = (m: AiModel) => {
    setEditing(m);
    reset({
      display_name: m.display_name,
      capability: m.capability,
      provider_model_name: m.provider_model_name,
      base_url: '',
      api_key: '',
      slug: m.slug,
      provider_key: m.provider_key,
      tokenizer_encoding: m.tokenizer_encoding ?? '',
      description: m.description ?? '',
      is_active: m.is_active,
    });
    setModalOpen(true);
  };

  const createPricingRules = async (modelId: string, values: ModelForm) => {
    const rules: Record<string, unknown>[] = [];
    if (values.capability === 'text') {
      if (values.input_price_toman != null)
        rules.push({
          model_id: modelId,
          billing_unit: 'input_token',
          unit_size: 1000000,
          unit_price_irr: tomanToIrr(values.input_price_toman),
          rounding_mode: 'up',
        });
      if (values.output_price_toman != null)
        rules.push({
          model_id: modelId,
          billing_unit: 'output_token',
          unit_size: 1000000,
          unit_price_irr: tomanToIrr(values.output_price_toman),
          rounding_mode: 'up',
        });
    } else if (values.capability === 'speech_to_text' || values.capability === 'text_to_speech') {
      if (values.audio_price_toman != null)
        rules.push({
          model_id: modelId,
          billing_unit: 'audio_second',
          unit_size: 1,
          unit_price_irr: tomanToIrr(values.audio_price_toman),
          rounding_mode: 'up',
        });
    } else if (values.capability === 'image') {
      if (values.image_price_toman != null)
        rules.push({
          model_id: modelId,
          billing_unit: 'image_count',
          unit_size: 1,
          unit_price_irr: tomanToIrr(values.image_price_toman),
          rounding_mode: 'up',
        });
    }
    for (const rule of rules) {
      await createRule.mutateAsync(rule);
    }
    return rules.length;
  };

  const onSubmit = (values: ModelForm) => {
    const err = (e: unknown) =>
      toast(e instanceof ApiError ? getErrorMessage(e.code, e.message) : 'خطایی رخ داد.', 'error');

    if (editing) {
      // PATCH only accepts: display_name, provider_model_name, pricing_type,
      // tokenizer_encoding, config_json, description, is_active (+ credentials).
      updateModel.mutate(
        {
          id: editing.id,
          patch: {
            display_name: values.display_name.trim(),
            provider_model_name: values.provider_model_name.trim(),
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
        {
          onSuccess: () => {
            setModalOpen(false);
            toast('مدل به‌روزرسانی شد.', 'success');
          },
          onError: err,
        },
      );
      return;
    }

    const autoSlug = slugify(values.provider_model_name) || slugify(values.display_name);
    createModel.mutate(
      {
        ...(values.slug?.trim() ? { slug: values.slug.trim() } : autoSlug ? { slug: autoSlug } : {}),
        display_name: values.display_name.trim(),
        capability: values.capability,
        ...(values.provider_key?.trim() ? { provider_key: values.provider_key.trim() } : {}),
        provider_model_name: values.provider_model_name.trim(),
        ...(values.capability === 'text'
          ? { tokenizer_encoding: values.tokenizer_encoding?.trim() || 'cl100k_base' }
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
      {
        onSuccess: async (model) => {
          try {
            const n = await createPricingRules(model.id, values);
            setModalOpen(false);
            toast(
              n > 0 ? `مدل ثبت شد و ${n === 1 ? 'تعرفه‌اش' : `${n} تعرفه`} ساخته شد.` : 'مدل جدید ثبت شد.',
              'success',
            );
          } catch (e) {
            setModalOpen(false);
            toast('مدل ساخته شد ولی ثبت تعرفه ناموفق بود؛ از صفحه تعرفه‌ها اضافه کنید.', 'error');
            console.error('quick pricing failed', e);
          }
        },
        onError: err,
      },
    );
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
        <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5" noValidate>
          {/* ۱. مشخصات */}
          <section>
            <h3 className="mb-3 text-sm font-bold text-neutral-700 dark:text-slate-300">مشخصات مدل</h3>
            <div className="flex flex-col gap-4">
              <div>
                <label htmlFor="model-display-name" className="label">نام نمایشی</label>
                <input
                  id="model-display-name"
                  placeholder="مثلاً: آروان GPT-4o Transcribe"
                  className={`input ${errors.display_name ? 'input-error' : ''}`}
                  {...register('display_name')}
                />
                {errors.display_name && <p role="alert" className="field-error">{errors.display_name.message}</p>}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="model-capability" className="label">قابلیت</label>
                  <select id="model-capability" className="input" disabled={!!editing} {...register('capability')}>
                    {CAPABILITIES.map((c) => (
                      <option key={c} value={c}>{CAPABILITY_LABELS[c]}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor="model-provider-name" className="label">نام مدل در provider</label>
                  <input
                    id="model-provider-name"
                    dir="ltr"
                    placeholder="gpt-4o-transcribe"
                    className={`input text-left ${errors.provider_model_name ? 'input-error' : ''}`}
                    {...register('provider_model_name')}
                  />
                  {errors.provider_model_name && (
                    <p role="alert" className="field-error">{errors.provider_model_name.message}</p>
                  )}
                </div>
              </div>
            </div>
          </section>

          {/* ۲. اتصال */}
          <section className="rounded-lg border border-neutral-200 p-4 dark:border-slate-700">
            <h3 className="mb-3 text-sm font-bold">اتصال provider</h3>
            <div className="flex flex-col gap-4">
              <div>
                <label htmlFor="model-base-url" className="label">آدرس endpoint</label>
                <input
                  id="model-base-url"
                  dir="ltr"
                  placeholder="https://api.example.com/v1"
                  className="input text-left"
                  {...register('base_url')}
                />
              </div>
              <div>
                <label htmlFor="model-api-key" className="label">توکن / کلید API</label>
                <input
                  id="model-api-key"
                  type="password"
                  dir="ltr"
                  autoComplete="off"
                  placeholder={editing?.has_credentials ? '•••••••• (ذخیره شده)' : ''}
                  className="input text-left"
                  {...register('api_key')}
                />
                {editing?.has_credentials && (
                  <p className="field-hint">کلید قبلاً ذخیره شده؛ فقط برای تغییر، مقدار جدید وارد کنید.</p>
                )}
              </div>
            </div>
          </section>

          {/* ۳. قیمت‌گذاری سریع (فقط ساخت) */}
          {!editing && (
            <section className="rounded-lg border border-neutral-200 p-4 dark:border-slate-700">
              <h3 className="mb-1 text-sm font-bold">قیمت‌گذاری سریع</h3>
              <p className="mb-3 text-xs text-neutral-500 dark:text-slate-400">
                اختیاری — مبالغ به تومان. خالی بگذارید تا بعداً از صفحه تعرفه‌ها ثبت کنید.
              </p>
              {capability === 'text' && (
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="model-in-price" className="label">هر ۱ میلیون توکن ورودی (تومان)</label>
                    <input id="model-in-price" type="number" min={0} step="any" dir="ltr" className="input text-left" {...register('input_price_toman')} />
                  </div>
                  <div>
                    <label htmlFor="model-out-price" className="label">هر ۱ میلیون توکن خروجی (تومان)</label>
                    <input id="model-out-price" type="number" min={0} step="any" dir="ltr" className="input text-left" {...register('output_price_toman')} />
                  </div>
                </div>
              )}
              {(capability === 'speech_to_text' || capability === 'text_to_speech') && (
                <div>
                  <label htmlFor="model-audio-price" className="label">قیمت هر ثانیه صوت (تومان)</label>
                  <input id="model-audio-price" type="number" min={0} step="any" dir="ltr" className="input text-left" {...register('audio_price_toman')} />
                </div>
              )}
              {capability === 'image' && (
                <div>
                  <label htmlFor="model-image-price" className="label">قیمت هر تصویر (تومان)</label>
                  <input id="model-image-price" type="number" min={0} step="any" dir="ltr" className="input text-left" {...register('image_price_toman')} />
                </div>
              )}
            </section>
          )}

          {/* ۴. پیشرفته */}
          <details className="rounded-lg border border-neutral-200 dark:border-slate-700">
            <summary className="cursor-pointer px-4 py-3 text-sm font-bold text-neutral-600 dark:text-slate-400">
              تنظیمات پیشرفته
            </summary>
            <div className="flex flex-col gap-4 border-t border-neutral-200 px-4 py-4 dark:border-slate-700">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="model-slug" className="label">شناسه یکتا (slug)</label>
                  <input
                    id="model-slug"
                    dir="ltr"
                    placeholder="خودکار از نام مدل"
                    disabled={!!editing}
                    className={`input text-left ${errors.slug ? 'input-error' : ''}`}
                    {...register('slug')}
                  />
                  {errors.slug && <p role="alert" className="field-error">{errors.slug.message}</p>}
                  {!editing && <p className="field-hint">خالی = خودکار ساخته می‌شود.</p>}
                </div>
                <div>
                  <label htmlFor="model-provider-key" className="label">کلید provider</label>
                  <input
                    id="model-provider-key"
                    dir="ltr"
                    placeholder="خودکار = شناسه یکتا"
                    disabled={!!editing}
                    className="input text-left"
                    {...register('provider_key')}
                  />
                  {!editing && <p className="field-hint">فقط برای خواندن از env لازم است.</p>}
                </div>
              </div>
              {capability === 'text' && (
                <div>
                  <label htmlFor="model-encoding" className="label">encoding توکنایزر (tiktoken)</label>
                  <input
                    id="model-encoding"
                    dir="ltr"
                    placeholder="cl100k_base"
                    className="input text-left"
                    {...register('tokenizer_encoding')}
                  />
                  <p className="field-hint">خالی = cl100k_base</p>
                </div>
              )}
              <div>
                <label htmlFor="model-description" className="label">توضیحات</label>
                <textarea id="model-description" rows={2} className="input" {...register('description')} />
              </div>
            </div>
          </details>

          <label className="flex items-center gap-2 text-sm font-medium">
            <input type="checkbox" className="h-5 w-5 accent-amber-600" {...register('is_active')} />
            مدل فعال باشد
          </label>

          <div className="flex gap-2">
            <button type="submit" disabled={createModel.isPending || updateModel.isPending} className="btn-primary flex-1">
              {createModel.isPending || updateModel.isPending ? 'در حال ذخیره…' : editing ? 'ذخیره' : 'اتصال مدل'}
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
