'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  useAdminModels,
  useCreatePricingRule,
  usePricingEstimate,
  usePricingRules,
  useUpdatePricingRule,
} from '@/features/admin/hooks';
import { formatToman } from '@/lib/currency';
import { formatDateTime, formatNumber } from '@/lib/format';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { ResponsiveTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { useToast } from '@/components/Toast';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { ModelService, PricingRule } from '@/types/api';

const SERVICE_LABELS: Record<ModelService, string> = { text: 'متن', audio: 'صوت', image: 'تصویر' };

const ruleSchema = z.object({
  model_id: z.string().min(1, 'مدل را انتخاب کنید.'),
  rounding: z.enum(['up', 'down', 'nearest']),
  is_active: z.boolean(),
  /** JSON object of numeric params, e.g. {"input_per_1k_irr": 500}. */
  params_json: z
    .string()
    .trim()
    .min(1, 'پارامترهای تعرفه را وارد کنید.')
    .refine(
      (v) => {
        try {
          const parsed: unknown = JSON.parse(v);
          return (
            typeof parsed === 'object' &&
            parsed !== null &&
            Object.values(parsed).every((x) => typeof x === 'number' && Number.isFinite(x))
          );
        } catch {
          return false;
        }
      },
      { message: 'JSON معتبر با مقادیر عددی وارد کنید. مثال: {"input_per_1k_irr": 500}' },
    ),
});
type RuleForm = z.infer<typeof ruleSchema>;

const estimateSchema = z.object({
  model_id: z.string().min(1, 'مدل را انتخاب کنید.'),
  input_tokens: z.number().min(0).optional(),
  output_tokens: z.number().min(0).optional(),
  seconds: z.number().min(0).optional(),
  megapixels: z.number().min(0).optional(),
});
type EstimateForm = z.infer<typeof estimateSchema>;

/** Admin pricing: versioned rules + estimate preview tester. */
export default function AdminPricingPage() {
  const { toast } = useToast();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<PricingRule | null>(null);

  const rules = usePricingRules();
  const models = useAdminModels();
  const createRule = useCreatePricingRule();
  const updateRule = useUpdatePricingRule();
  const estimate = usePricingEstimate();

  const ruleForm = useForm<RuleForm>({ resolver: zodResolver(ruleSchema) });
  const estimateForm = useForm<EstimateForm>({ resolver: zodResolver(estimateSchema) });

  const openCreate = () => {
    setEditing(null);
    ruleForm.reset({ model_id: '', rounding: 'nearest', is_active: true, params_json: '{}' });
    setModalOpen(true);
  };

  const onSaveRule = (values: RuleForm) => {
    const payload = {
      model_id: values.model_id,
      rounding: values.rounding,
      is_active: values.is_active,
      params: JSON.parse(values.params_json) as Record<string, number>,
    };
    const done = {
      onSuccess: () => {
        setModalOpen(false);
        toast('تعرفه ذخیره شد (نسخه جدید ساخته می‌شود).', 'success');
      },
      onError: (err: unknown) =>
        toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'خطایی رخ داد.', 'error'),
    };
    if (editing) updateRule.mutate({ id: editing.id, patch: payload }, done);
    else createRule.mutate(payload, done);
  };

  const onEstimate = (values: EstimateForm) => {
    estimate.mutate(values, {
      onError: (err) =>
        toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'محاسبه ناموفق بود.', 'error'),
    });
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold">تعرفه‌ها</h1>
        <button type="button" onClick={openCreate} className="btn-primary btn-sm">
          تعرفه جدید
        </button>
      </div>

      {rules.isLoading && <LoadingSpinner />}
      {rules.isError && <ErrorState message="بارگذاری تعرفه‌ها ناموفق بود." onRetry={() => rules.refetch()} />}
      {rules.data && rules.data.length === 0 && (
        <EmptyState icon="💲" title="تعرفه‌ای ثبت نشده" description="هنوز قانون قیمتی ثبت نشده است." />
      )}
      {rules.data && rules.data.length > 0 && (
        <ResponsiveTable
          ariaLabel="فهرست تعرفه‌ها"
          keyOf={(r) => r.id}
          rows={rules.data}
          cardHeader={(r) => `${r.model_name ?? r.model_id} — نسخه ${formatNumber(r.version)}`}
          columns={[
            { header: 'مدل', render: (r) => r.model_name ?? <span dir="ltr">{r.model_id}</span> },
            { header: 'سرویس', render: (r) => SERVICE_LABELS[r.service] },
            { header: 'نسخه', render: (r) => <span className="tabular-nums">v{formatNumber(r.version)}</span> },
            {
              header: 'وضعیت',
              render: (r) => (r.is_active ? <span className="badge-success">فعال</span> : <span className="badge-neutral">غیرفعال</span>),
            },
            {
              header: 'پارامترها',
              render: (r) => (
                <span dir="ltr" className="text-xs tabular-nums">
                  {Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(', ') || '—'}
                </span>
              ),
              hideOnCard: true,
            },
            { header: 'ثبت', render: (r) => formatDateTime(r.created_at), hideOnCard: true },
          ]}
        />
      )}

      {/* Estimate tester */}
      <section aria-labelledby="estimate-test-heading" className="card">
        <h2 id="estimate-test-heading" className="text-lg font-bold">
          تست محاسبه قیمت
        </h2>
        <p className="mt-1 text-sm text-neutral-600 dark:text-slate-400">
          با ورودی نمونه، محاسبه تعرفه را پیش‌نمایش کنید؛ بدون ثبت تراکنش.
        </p>
        <form onSubmit={estimateForm.handleSubmit(onEstimate)} className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" noValidate>
          <div>
            <label htmlFor="est-model" className="label">مدل</label>
            <select id="est-model" className="input" {...estimateForm.register('model_id')}>
              <option value="">انتخاب مدل…</option>
              {(models.data ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({SERVICE_LABELS[m.service]})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="est-in" className="label">توکن ورودی</label>
            <input id="est-in" type="number" min={0} dir="ltr" className="input text-left" {...estimateForm.register('input_tokens', { valueAsNumber: true })} />
          </div>
          <div>
            <label htmlFor="est-out" className="label">توکن خروجی</label>
            <input id="est-out" type="number" min={0} dir="ltr" className="input text-left" {...estimateForm.register('output_tokens', { valueAsNumber: true })} />
          </div>
          <div>
            <label htmlFor="est-sec" className="label">ثانیه صوت</label>
            <input id="est-sec" type="number" min={0} dir="ltr" className="input text-left" {...estimateForm.register('seconds', { valueAsNumber: true })} />
          </div>
          <div>
            <label htmlFor="est-mp" className="label">مگاپیکسل تصویر</label>
            <input id="est-mp" type="number" min={0} step="0.1" dir="ltr" className="input text-left" {...estimateForm.register('megapixels', { valueAsNumber: true })} />
          </div>
          <div className="flex items-end">
            <button type="submit" disabled={estimate.isPending} className="btn-primary w-full">
              {estimate.isPending ? 'در حال محاسبه…' : 'محاسبه'}
            </button>
          </div>
        </form>

        {estimate.data && (
          <div className="mt-4 rounded-xl border border-brand-200 bg-brand-50 p-4 dark:border-brand-900/50 dark:bg-brand-950/30" aria-live="polite">
            <ul className="space-y-1 text-sm">
              {estimate.data.breakdown.map((line, i) => (
                <li key={i} className="flex justify-between gap-3">
                  <span className="text-neutral-600 dark:text-slate-400">{line.label}</span>
                  <span className="font-semibold tabular-nums">{formatToman(line.amount_irr)}</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 flex justify-between border-t border-brand-200 pt-2 font-bold dark:border-brand-900/50">
              <span>جمع</span>
              <span className="tabular-nums">{formatToman(estimate.data.total_irr)}</span>
            </p>
          </div>
        )}
      </section>

      <Modal open={modalOpen} title="تعرفه جدید" onClose={() => setModalOpen(false)}>
        <p className="mb-4 text-sm text-neutral-600 dark:text-slate-400">
          ذخیره تعرفه، نسخه جدید می‌سازد؛ نسخه قبلی برای تسویه‌های در جریان حفظ می‌ماند.
        </p>
        <form onSubmit={ruleForm.handleSubmit(onSaveRule)} className="flex flex-col gap-4" noValidate>
          <div>
            <label htmlFor="rule-model" className="label">مدل</label>
            <select id="rule-model" className={`input ${ruleForm.formState.errors.model_id ? 'input-error' : ''}`} {...ruleForm.register('model_id')}>
              <option value="">انتخاب مدل…</option>
              {(models.data ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name} ({SERVICE_LABELS[m.service]})
                </option>
              ))}
            </select>
            {ruleForm.formState.errors.model_id && (
              <p role="alert" className="field-error">{ruleForm.formState.errors.model_id.message}</p>
            )}
          </div>
          <div>
            <label htmlFor="rule-rounding" className="label">روش گرد کردن</label>
            <select id="rule-rounding" className="input" {...ruleForm.register('rounding')}>
              <option value="nearest">نزدیک‌ترین</option>
              <option value="up">به بالا</option>
              <option value="down">به پایین</option>
            </select>
          </div>
          <div>
            <label htmlFor="rule-params" className="label">پارامترهای تعرفه (JSON، مبالغ به ریال)</label>
            <textarea
              id="rule-params"
              rows={4}
              dir="ltr"
              className={`input resize-none text-left font-mono text-sm ${ruleForm.formState.errors.params_json ? 'input-error' : ''}`}
              placeholder='{"input_per_1k_irr": 500, "output_per_1k_irr": 1000}'
              {...ruleForm.register('params_json')}
            />
            {ruleForm.formState.errors.params_json ? (
              <p role="alert" className="field-error">{ruleForm.formState.errors.params_json.message}</p>
            ) : (
              <p className="field-hint">کلیدها را backend تعریف می‌کند؛ مقادیر عددی به ریال باشند.</p>
            )}
          </div>
          <label className="flex items-center gap-2 text-sm font-medium">
            <input type="checkbox" className="h-5 w-5 accent-amber-600" {...ruleForm.register('is_active')} />
            تعرفه فعال باشد
          </label>
          <div className="flex gap-2">
            <button type="submit" disabled={createRule.isPending || updateRule.isPending} className="btn-primary flex-1">
              ذخیره
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
