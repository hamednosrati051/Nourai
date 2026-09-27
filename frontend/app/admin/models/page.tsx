'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  useAdminModels,
  useCreateAdminModel,
  useCreatePricingRule,
  usePricingRules,
  useUpdateAdminModel,
} from '@/features/admin/hooks';
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

/** Adapter families. Extend when new provider types are added. */
const PROVIDER_TYPE_LABELS: Record<string, string> = {
  openai_compat: 'OpenAI Compatible',
};
const PROVIDER_TYPES = Object.keys(PROVIDER_TYPE_LABELS);

const modelSchema = z.object({
  display_name: z.string().trim().min(1, 'نام نمایشی مدل را وارد کنید.'),
  capability: z.enum(['text', 'speech_to_text', 'text_to_speech', 'image']),
  provider_type: z.enum(['openai_compat' as const]),
  provider_model_name: z.string().trim().min(1, 'نام مدل در سمت provider را وارد کنید.'),
  base_url: z.string().trim().optional(),
  api_key: z.string().trim().optional(),
  // Pricing: IRR per 1000 tokens (text models only).
  input_price_per_1k: z.coerce.number().min(0, 'مبلغ باید مثبت باشد.').default(0),
  output_price_per_1k: z.coerce.number().min(0, 'مبلغ باید مثبت باشد.').default(0),
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
  const createPricingRule = useCreatePricingRule();
  const pricingRules = usePricingRules();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ModelForm>({ resolver: zodResolver(modelSchema) });

  const openCreate = () => {
    setEditing(null);
    reset({
      display_name: '',
      capability: 'text',
      provider_type: 'openai_compat',
      provider_model_name: '',
      base_url: '',
      api_key: '',
      input_price_per_1k: 0,
      output_price_per_1k: 0,
      is_active: true,
    });
    setModalOpen(true);
  };

  const openEdit = (m: AiModel) => {
    setEditing(m);
    // Load existing pricing rules (IRR per 1000 tokens -> تومان in the form).
    const rules = (pricingRules.data ?? []).filter((r) => r.model_id === m.id);
    const inputRule = rules.find((r) => r.billing_unit === 'input_token');
    const outputRule = rules.find((r) => r.billing_unit === 'output_token');
    reset({
      display_name: m.display_name,
      capability: m.capability,
      provider_type: (m.provider_type as 'openai_compat') ?? 'openai_compat',
      provider_model_name: m.provider_model_name,
      base_url: m.base_url || '',
      api_key: '',
      input_price_per_1k: inputRule ? inputRule.unit_price_irr / 10 / inputRule.unit_size * 1000 : 0,
      output_price_per_1k: outputRule ? outputRule.unit_price_irr / 10 / outputRule.unit_size * 1000 : 0,
      is_active: m.is_active,
    });
    setModalOpen(true);
  };

  const onSubmit = (values: ModelForm) => {
    const err = (e: unknown) =>
      toast(e instanceof ApiError ? getErrorMessage(e.code, e.message) : 'خطایی رخ داد.', 'error');

    if (editing) {
      // TEMP (model testing): simplified form — PATCH accepts display_name,
      // provider_model_name, provider_type, is_active (+ credentials).
      updateModel.mutate(
        {
          id: editing.id,
          patch: {
            display_name: values.display_name.trim(),
            provider_model_name: values.provider_model_name.trim(),
            provider_type: values.provider_type,
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
            // Save pricing rules (new version) for text models.
            if (values.capability === 'text') {
              const rules = [];
              if (values.input_price_per_1k > 0) {
                rules.push({ model_id: editing.id, billing_unit: 'input_token', unit_size: 1000, unit_price_irr: Math.round(values.input_price_per_1k * 10), rounding_mode: 'up' as const });
              }
              if (values.output_price_per_1k > 0) {
                rules.push({ model_id: editing.id, billing_unit: 'output_token', unit_size: 1000, unit_price_irr: Math.round(values.output_price_per_1k * 10), rounding_mode: 'up' as const });
              }
              Promise.all(rules.map((r) => createPricingRule.mutateAsync(r))).catch(() =>
                toast('مدل به‌روزرسانی شد ولی ثبت تعرفه ناموفق بود.', 'error'),
              );
            }
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
        ...(autoSlug ? { slug: autoSlug } : {}),
        display_name: values.display_name.trim(),
        capability: values.capability,
        provider_type: values.provider_type,
        provider_model_name: values.provider_model_name.trim(),
        // TEMP (model testing): pricing + advanced removed; encoding defaults.
        ...(values.capability === 'text' ? { tokenizer_encoding: 'cl100k_base' } : {}),
        ...(values.base_url?.trim() || values.api_key?.trim()
          ? {
              base_url: values.base_url?.trim() || '',
              api_key: values.api_key?.trim() || '',
            }
          : {}),
        is_active: values.is_active,
      },
      {
        onSuccess: (model) => {
          // Create pricing rules for text models (input/output per 1000 tokens).
          if (values.capability === 'text' && (values.input_price_per_1k > 0 || values.output_price_per_1k > 0)) {
            const rules = [];
            if (values.input_price_per_1k > 0) {
              rules.push({ model_id: model.id, billing_unit: 'input_token', unit_size: 1000, unit_price_irr: Math.round(values.input_price_per_1k * 10), rounding_mode: 'up' as const });
            }
            if (values.output_price_per_1k > 0) {
              rules.push({ model_id: model.id, billing_unit: 'output_token', unit_size: 1000, unit_price_irr: Math.round(values.output_price_per_1k * 10), rounding_mode: 'up' as const });
            }
            // Prices are in تومان in the form, stored as IRR (x10).
            Promise.all(rules.map((r) => createPricingRule.mutateAsync(r))).catch(() =>
              toast('مدل ساخته شد ولی ثبت تعرفه ناموفق بود.', 'error'),
            );
          }
          setModalOpen(false);
          toast('مدل جدید ثبت شد.', 'success');
        },
        onError: err,
      },
    );
  };

  const toggleActive = (m: AiModel) => {
    updateModel.mutate(
      { id: m.id, patch: { is_active: !m.is_active } },
      {
        onSuccess: () =>
          toast(
            m.is_active
              ? 'مدل غیرفعال شد.'
              : `مدل فعال شد؛ سایر مدل‌های «${CAPABILITY_LABELS[m.capability] ?? m.capability}» غیرفعال شدند.`,
            'success',
          ),
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
            { header: 'نوع', render: (m) => PROVIDER_TYPE_LABELS[m.provider_type] ?? m.provider_type, hideOnCard: true },
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
                  <label htmlFor="model-provider-type" className="label">نوع</label>
                  <select id="model-provider-type" className="input" {...register('provider_type')}>
                    {PROVIDER_TYPES.map((t) => (
                      <option key={t} value={t}>{PROVIDER_TYPE_LABELS[t]}</option>
                    ))}
                  </select>
                  <p className="field-hint">نوع‌های دیگر بعداً اضافه می‌شوند.</p>
                </div>
                <div className="sm:col-span-2">
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

          <section aria-label="تعرفه">
            <h3 className="mb-3 text-sm font-bold">تعرفه (تومان به ازای هر ۱۰۰۰ توکن)</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="model-input-price" className="label">
                  توکن ورودی
                </label>
                <input
                  id="model-input-price"
                  type="number"
                  min={0}
                  dir="ltr"
                  className="input text-left"
                  {...register('input_price_per_1k')}
                />
              </div>
              <div>
                <label htmlFor="model-output-price" className="label">
                  توکن خروجی
                </label>
                <input
                  id="model-output-price"
                  type="number"
                  min={0}
                  dir="ltr"
                  className="input text-left"
                  {...register('output_price_per_1k')}
                />
              </div>
            </div>
            <p className="field-hint">مثلاً ورودی ۱۰۰ و خروجی ۲۰۰ یعنی هر ۱۰۰۰ توکن ورودی ۱۰۰ تومان.</p>
          </section>

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