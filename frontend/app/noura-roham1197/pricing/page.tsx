'use client';

import { CircleDollarSign } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  useAdminModels,
  useCreatePricingRule,
  useCurrencySettings,
  useDeletePricingRule,
  usePricingEstimate,
  usePricingRules,
  useUpdateCurrencySettings,
  useUpdatePricingRule,
} from '@/features/admin/hooks';
import { formatToman, tomanToIrr, irrToToman } from '@/lib/currency';
import { formatNumber } from '@/lib/format';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { ResponsiveTable } from '@/components/DataTable';
import { Modal } from '@/components/Modal';
import { useToast } from '@/components/Toast';
import { ApiError, getErrorMessage } from '@/lib/api';
import type { ModelCapability, PricingRule } from '@/types/api';

const CAPABILITY_LABELS: Record<ModelCapability, string> = {
  text: 'متن',
  speech_to_text: 'stt',
  text_to_speech: 'tts',
  image: 'تصویر',
  generate_image: 'تولید تصویر',
  edit_image: 'ویرایش تصویر',
};

const BILLING_UNIT_LABELS: Record<string, string> = {
  fixed_request: 'هر درخواست',
  input_token: 'توکن ورودی',
  output_token: 'توکن خروجی',
  audio_second: 'ثانیه صوت',
  image_count: 'تعداد تصویر',
  input_megapixel: 'مگاپیکسل ورودی',
  output_megapixel: 'مگاپیکسل خروجی',
};

const ROUNDING_LABELS: Record<string, string> = {
  up: 'به بالا',
  down: 'به پایین',
  nearest: 'نزدیک‌ترین',
};

const optionalToman = z
  .union([z.number(), z.string()])
  .optional()
  .transform((v) => {
    if (v === undefined || v === '' || v === null) return undefined;
    const n = typeof v === 'string' ? Number(v) : v;
    return Number.isFinite(n) && n >= 0 ? n : undefined;
  });

const ruleSchema = z.object({
  model_id: z.string().min(1, 'مدل را انتخاب کنید.'),
  billing_unit: z.string().min(1, 'واحد محاسبه را انتخاب کنید.'),
  unit_size: z.coerce.number().int().min(1, 'اندازه واحد حداقل ۱ باشد.'),
  /** USD in the UI; converted to IRR at billing time with the admin rate. */
  unit_price_usd: z.coerce.number().min(0, 'قیمت نامعتبر است.'),
  dimension_key: z.string().trim().optional(),
  quality_key: z.string().trim().optional(),
  minimum_charge_toman: optionalToman,
  maximum_charge_toman: optionalToman,
  rounding_mode: z.enum(['up', 'down', 'nearest']),
  effective_from: z.string().optional(),
  effective_to: z.string().optional(),
});
type RuleForm = z.infer<typeof ruleSchema>;

const editSchema = z.object({
  is_active: z.boolean(),
  minimum_charge_toman: optionalToman,
  maximum_charge_toman: optionalToman,
  effective_from: z.string().optional(),
  effective_to: z.string().optional(),
});
type EditForm = z.infer<typeof editSchema>;

const estimateSchema = z.object({
  kind: z.enum(['text', 'audio', 'image']),
  model_id: z.string().min(1, 'مدل را انتخاب کنید.'),
  input_tokens: z.coerce.number().min(0).optional(),
  max_output_tokens: z.coerce.number().min(0).optional(),
  audio_seconds: z.coerce.number().min(0).optional(),
  image_count: z.coerce.number().min(1).optional(),
  input_megapixels: z.coerce.number().min(0).optional(),
  output_megapixels: z.coerce.number().min(0).optional(),
  dimension_key: z.string().trim().optional(),
  quality_key: z.string().trim().optional(),
});
type EstimateForm = z.infer<typeof estimateSchema>;

/** Admin pricing: versioned rules + estimate preview tester. */
export default function AdminPricingPage() {
  const { toast } = useToast();
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<PricingRule | null>(null);

  const rules = usePricingRules();
  const models = useAdminModels();
  const createRule = useCreatePricingRule();
  const updateRule = useUpdatePricingRule();
  const deleteRule = useDeletePricingRule();
  const estimate = usePricingEstimate();
  const currency = useCurrencySettings();
  const updateCurrency = useUpdateCurrencySettings();
  const [rateToman, setRateToman] = useState('');

  const rateIrr = currency.data?.usd_to_irr ?? 0;
  useEffect(() => {
    if (currency.data) setRateToman(String(irrToToman(currency.data.usd_to_irr)));
  }, [currency.data]);

  const onSaveRate = () => {
    const toman = Number(rateToman);
    if (!Number.isFinite(toman) || toman <= 0) {
      toast('نرخ دلار نامعتبر است.', 'error');
      return;
    }
    updateCurrency.mutate(
      {
        usd_to_irr: tomanToIrr(toman),
        image_cost_margin_pct: currency.data?.image_cost_margin_pct ?? 30,
      },
      {
        onSuccess: () => toast('نرخ دلار ذخیره شد؛ از این لحظه روی محاسبات جدید اعمال می‌شود.', 'success'),
        onError: (err: unknown) =>
          toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'خطایی رخ داد.', 'error'),
      },
    );
  };

  const ruleForm = useForm<RuleForm>({ resolver: zodResolver(ruleSchema) });
  const editForm = useForm<EditForm>({ resolver: zodResolver(editSchema) });
  const estimateForm = useForm<EstimateForm>({
    resolver: zodResolver(estimateSchema),
    defaultValues: { kind: 'text' },
  });
  const estimateKind = estimateForm.watch('kind');
  const usdPreview = Number(ruleForm.watch('unit_price_usd')) || 0;

  const openCreate = () => {
    ruleForm.reset({
      model_id: '',
      billing_unit: '',
      unit_size: 1,
      unit_price_usd: 0,
      dimension_key: '',
      quality_key: '',
      rounding_mode: 'up',
      effective_from: '',
      effective_to: '',
    });
    setCreateOpen(true);
  };

  const openEdit = (rule: PricingRule) => {
    setEditing(rule);
    editForm.reset({
      is_active: rule.is_active,
      minimum_charge_toman: rule.minimum_charge_irr != null ? irrToToman(rule.minimum_charge_irr) : undefined,
      maximum_charge_toman: rule.maximum_charge_irr != null ? irrToToman(rule.maximum_charge_irr) : undefined,
      effective_from: rule.effective_from ? rule.effective_from.slice(0, 16) : '',
      effective_to: rule.effective_to ? rule.effective_to.slice(0, 16) : '',
    });
  };

  const onCreateRule = (values: RuleForm) => {
    createRule.mutate(
      {
        model_id: values.model_id,
        billing_unit: values.billing_unit,
        unit_size: values.unit_size,
        unit_price_usd: String(values.unit_price_usd),
        ...(values.dimension_key?.trim() ? { dimension_key: values.dimension_key.trim() } : {}),
        ...(values.quality_key?.trim() ? { quality_key: values.quality_key.trim() } : {}),
        ...(values.minimum_charge_toman != null
          ? { minimum_charge_irr: tomanToIrr(values.minimum_charge_toman) }
          : {}),
        ...(values.maximum_charge_toman != null
          ? { maximum_charge_irr: tomanToIrr(values.maximum_charge_toman) }
          : {}),
        rounding_mode: values.rounding_mode,
        ...(values.effective_from ? { effective_from: values.effective_from } : {}),
        ...(values.effective_to ? { effective_to: values.effective_to } : {}),
      },
      {
        onSuccess: () => {
          setCreateOpen(false);
          toast('تعرفه ذخیره شد (نسخه جدید ساخته می‌شود).', 'success');
        },
        onError: (err: unknown) =>
          toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'خطایی رخ داد.', 'error'),
      },
    );
  };

  const onEditRule = (values: EditForm) => {
    if (!editing) return;
    updateRule.mutate(
      {
        id: editing.id,
        patch: {
          is_active: values.is_active,
          minimum_charge_irr: values.minimum_charge_toman != null ? tomanToIrr(values.minimum_charge_toman) : null,
          maximum_charge_irr: values.maximum_charge_toman != null ? tomanToIrr(values.maximum_charge_toman) : null,
          effective_from: values.effective_from || null,
          effective_to: values.effective_to || null,
        },
      },
      {
        onSuccess: () => {
          setEditing(null);
          toast('تعرفه به‌روزرسانی شد.', 'success');
        },
        onError: (err: unknown) =>
          toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'خطایی رخ داد.', 'error'),
      },
    );
  };

  const onDeleteRule = (rule: PricingRule) => {
    const label = `${rule.model_name ?? rule.model_id} — ${BILLING_UNIT_LABELS[rule.billing_unit] ?? rule.billing_unit} (نسخه ${rule.version})`;
    if (!window.confirm(`تعرفه «${label}» حذف شود؟ این عمل قابل بازگشت نیست.`)) return;
    deleteRule.mutate(rule.id, {
      onSuccess: () => toast('تعرفه حذف شد.', 'success'),
      onError: (err: unknown) =>
        toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'حذف تعرفه ناموفق بود.', 'error'),
    });
  };

  const onEstimate = (values: EstimateForm) => {
    estimate.mutate(
      {
        kind: values.kind,
        model_id: values.model_id,
        input_tokens: values.input_tokens ?? 0,
        max_output_tokens: values.max_output_tokens ?? 0,
        audio_seconds: values.audio_seconds ?? 0,
        image_count: values.image_count ?? 1,
        input_megapixels: values.input_megapixels ?? 0,
        output_megapixels: values.output_megapixels ?? 0,
        ...(values.dimension_key?.trim() ? { dimension_key: values.dimension_key.trim() } : {}),
        ...(values.quality_key?.trim() ? { quality_key: values.quality_key.trim() } : {}),
      },
      {
        onError: (err) =>
          toast(err instanceof ApiError ? getErrorMessage(err.code, err.message) : 'محاسبه ناموفق بود.', 'error'),
      },
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-extrabold">تعرفه‌ها</h1>
        <button type="button" onClick={openCreate} className="btn-primary btn-sm">
          تعرفه جدید
        </button>
      </div>

      {/* Exchange rate: USD tariffs convert with this rate at billing time */}
      <section aria-labelledby="fx-rate-heading" className="card">
        <h2 id="fx-rate-heading" className="text-lg font-bold">نرخ ارز</h2>
        <p className="mt-1 text-sm text-neutral-600 dark:text-slate-400">
          تعرفه‌ها به دلار ثبت می‌شوند و موقع صورتحساب با این نرخ به تومان تبدیل می‌شوند.
          تغییر نرخ از همین لحظه روی درخواست‌های جدید اعمال می‌شود؛ نیازی به ویرایش تعرفه‌ها نیست.
        </p>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="fx-rate" className="label">نرخ هر دلار (تومان)</label>
            <input
              id="fx-rate"
              type="number"
              min={0}
              step="any"
              dir="ltr"
              className="input text-left"
              value={rateToman}
              onChange={(e) => setRateToman(e.target.value)}
              placeholder="266000"
            />
          </div>
          <button
            type="button"
            onClick={onSaveRate}
            disabled={updateCurrency.isPending || currency.isLoading}
            className="btn-primary"
          >
            {updateCurrency.isPending ? 'در حال ذخیره…' : 'ذخیره نرخ'}
          </button>
        </div>
      </section>

      {rules.isLoading && <LoadingSpinner />}
      {rules.isError && <ErrorState message="بارگذاری تعرفه‌ها ناموفق بود." onRetry={() => rules.refetch()} />}
      {rules.data && rules.data.length === 0 && (
        <EmptyState icon={CircleDollarSign} title="تعرفه‌ای ثبت نشده" description="هنوز قانون قیمتی ثبت نشده است." />
      )}
      {rules.data && rules.data.length > 0 && (
        <ResponsiveTable
          ariaLabel="فهرست تعرفه‌ها"
          keyOf={(r) => r.id}
          rows={[...rules.data].sort((a, b) => Number(b.is_active) - Number(a.is_active) || new Date(b.created_at).getTime() - new Date(a.created_at).getTime())}
          cardHeader={(r) => `${r.model_name ?? r.model_id} — نسخه ${formatNumber(r.version)}`}
          columns={[
            { header: 'مدل', render: (r) => r.model_name ?? <span dir="ltr">{r.model_id}</span> },
            {
              header: 'واحد',
              render: (r) => BILLING_UNIT_LABELS[r.billing_unit] ?? <span dir="ltr">{r.billing_unit}</span>,
            },
            {
              header: 'قیمت واحد',
              render: (r) => (
                <span className="tabular-nums">
                  <span dir="ltr">${r.unit_price_usd}</span>{' '}
                  <span className="text-xs text-neutral-500">/ {formatNumber(r.unit_size)}</span>
                  {rateIrr > 0 && (
                    <span className="block text-xs text-neutral-500">
                      ≈ {formatToman(Math.ceil(Number(r.unit_price_usd) * rateIrr))}
                    </span>
                  )}
                </span>
              ),
            },
            { header: 'نسخه', render: (r) => <span className="tabular-nums">v{formatNumber(r.version)}</span> },
            {
              header: 'وضعیت',
              render: (r) =>
                r.is_active ? (
                  <span className="badge-success">فعال</span>
                ) : (
                  <span className="badge-neutral">غیرفعال</span>
                ),
            },
            {
              header: 'عملیات',
              render: (r) => (
                <div className="flex gap-2">
                  <button type="button" className="btn-secondary btn-sm" onClick={() => openEdit(r)}>
                    ویرایش
                  </button>
                  <button type="button" className="btn-danger btn-sm" onClick={() => onDeleteRule(r)}>
                    حذف
                  </button>
                </div>
              ),
              hideOnCard: true,
            },
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
            <label htmlFor="est-kind" className="label">نوع</label>
            <select id="est-kind" className="input" {...estimateForm.register('kind')}>
              <option value="text">متن</option>
              <option value="audio">صوت</option>
              <option value="image">تصویر</option>
            </select>
          </div>
          <div>
            <label htmlFor="est-model" className="label">مدل</label>
            <select id="est-model" className="input" {...estimateForm.register('model_id')}>
              <option value="">انتخاب مدل…</option>
              {(models.data ?? []).filter((m) => m.is_active).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name} ({CAPABILITY_LABELS[m.capability] ?? m.capability})
                </option>
              ))}
            </select>
          </div>
          {estimateKind === 'text' && (
            <>
              <div>
                <label htmlFor="est-in" className="label">توکن ورودی</label>
                <input id="est-in" type="number" min={0} dir="ltr" className="input text-left" {...estimateForm.register('input_tokens')} />
              </div>
              <div>
                <label htmlFor="est-out" className="label">حداکثر توکن خروجی</label>
                <input id="est-out" type="number" min={0} dir="ltr" className="input text-left" {...estimateForm.register('max_output_tokens')} />
              </div>
            </>
          )}
          {estimateKind === 'audio' && (
            <div>
              <label htmlFor="est-sec" className="label">ثانیه صوت</label>
              <input id="est-sec" type="number" min={0} dir="ltr" className="input text-left" {...estimateForm.register('audio_seconds')} />
            </div>
          )}
          {estimateKind === 'image' && (
            <>
              <div>
                <label htmlFor="est-count" className="label">تعداد تصویر</label>
                <input id="est-count" type="number" min={1} dir="ltr" className="input text-left" {...estimateForm.register('image_count')} />
              </div>
              <div>
                <label htmlFor="est-imp" className="label">مگاپیکسل ورودی</label>
                <input id="est-imp" type="number" min={0} step="0.1" dir="ltr" className="input text-left" {...estimateForm.register('input_megapixels')} />
              </div>
              <div>
                <label htmlFor="est-omp" className="label">مگاپیکسل خروجی</label>
                <input id="est-omp" type="number" min={0} step="0.1" dir="ltr" className="input text-left" {...estimateForm.register('output_megapixels')} />
              </div>
              <div>
                <label htmlFor="est-dim" className="label">کلید بُعد (اختیاری)</label>
                <input id="est-dim" dir="ltr" className="input text-left" {...estimateForm.register('dimension_key')} />
              </div>
              <div>
                <label htmlFor="est-quality" className="label">کلید کیفیت (اختیاری)</label>
                <input id="est-quality" dir="ltr" className="input text-left" {...estimateForm.register('quality_key')} />
              </div>
            </>
          )}
          <div className="flex items-end">
            <button type="submit" disabled={estimate.isPending} className="btn-primary w-full">
              {estimate.isPending ? 'در حال محاسبه…' : 'محاسبه'}
            </button>
          </div>
        </form>

        {estimate.data && (
          <div className="mt-4 rounded-xl border border-brand-200 bg-brand-50 p-4 dark:border-brand-900/50 dark:bg-brand-950/30" aria-live="polite">
            <ul className="space-y-1 text-sm">
              {(estimate.data.lines ?? []).map((line, i) => (
                <li key={i} className="flex justify-between gap-3">
                  <span className="text-neutral-600 dark:text-slate-400">{BILLING_UNIT_LABELS[line.billing_unit] ?? line.billing_unit}</span>
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

      {/* Create modal */}
      <Modal open={createOpen} title="تعرفه جدید" onClose={() => setCreateOpen(false)}>
        <p className="mb-4 text-sm text-neutral-600 dark:text-slate-400">
          ذخیره تعرفه، نسخه جدید می‌سازد؛ نسخه قبلی برای تسویه‌های در جریان حفظ می‌ماند.
          قیمت واحد به <b>دلار</b> وارد می‌شود؛ حداقل/حداکثر دریافتی به تومان.
        </p>
        <form onSubmit={ruleForm.handleSubmit(onCreateRule)} className="flex flex-col gap-4" noValidate>
          <div>
            <label htmlFor="rule-model" className="label">مدل</label>
            <select id="rule-model" className={`input ${ruleForm.formState.errors.model_id ? 'input-error' : ''}`} {...ruleForm.register('model_id')}>
              <option value="">انتخاب مدل…</option>
              {(models.data ?? []).filter((m) => m.is_active).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.display_name} ({CAPABILITY_LABELS[m.capability] ?? m.capability})
                </option>
              ))}
            </select>
            {ruleForm.formState.errors.model_id && (
              <p role="alert" className="field-error">{ruleForm.formState.errors.model_id.message}</p>
            )}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="rule-unit" className="label">واحد محاسبه</label>
              <select id="rule-unit" className="input" {...ruleForm.register('billing_unit')}>
                <option value="">انتخاب واحد…</option>
                {Object.entries(BILLING_UNIT_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
              {ruleForm.formState.errors.billing_unit && (
                <p role="alert" className="field-error">{ruleForm.formState.errors.billing_unit.message}</p>
              )}
            </div>
            <div>
              <label htmlFor="rule-size" className="label">اندازه واحد</label>
              <input id="rule-size" type="number" min={1} step={1} dir="ltr" className="input text-left" {...ruleForm.register('unit_size')} />
              <p className="field-hint">مثلاً برای «هر یک میلیون توکن»: ۱٬۰۰۰٬۰۰۰</p>
              {ruleForm.formState.errors.unit_size && (
                <p role="alert" className="field-error">{ruleForm.formState.errors.unit_size.message}</p>
              )}
            </div>
          </div>
          <div>
            <label htmlFor="rule-price" className="label">قیمت هر واحد (دلار)</label>
            <input id="rule-price" type="number" min={0} step="any" dir="ltr" className="input text-left" {...ruleForm.register('unit_price_usd')} />
            {usdPreview > 0 && rateIrr > 0 && (
              <p className="field-hint">≈ {formatToman(Math.ceil(usdPreview * rateIrr))} با نرخ فعلی</p>
            )}
            {ruleForm.formState.errors.unit_price_usd && (
              <p role="alert" className="field-error">{ruleForm.formState.errors.unit_price_usd.message}</p>
            )}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="rule-dim" className="label">کلید بُعد (اختیاری)</label>
              <input id="rule-dim" dir="ltr" className="input text-left" placeholder="مثلاً 1024x1024" {...ruleForm.register('dimension_key')} />
            </div>
            <div>
              <label htmlFor="rule-quality" className="label">کلید کیفیت (اختیاری)</label>
              <input id="rule-quality" dir="ltr" className="input text-left" placeholder="مثلاً hd" {...ruleForm.register('quality_key')} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="rule-min" className="label">حداقل دریافتی (تومان، اختیاری)</label>
              <input id="rule-min" type="number" min={0} step="any" dir="ltr" className="input text-left" {...ruleForm.register('minimum_charge_toman')} />
            </div>
            <div>
              <label htmlFor="rule-max" className="label">حداکثر دریافتی (تومان، اختیاری)</label>
              <input id="rule-max" type="number" min={0} step="any" dir="ltr" className="input text-left" {...ruleForm.register('maximum_charge_toman')} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <label htmlFor="rule-rounding" className="label">روش گرد کردن</label>
              <select id="rule-rounding" className="input" {...ruleForm.register('rounding_mode')}>
                {Object.entries(ROUNDING_LABELS).map(([v, l]) => (
                  <option key={v} value={v}>{l}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="rule-from" className="label">اعتبار از (اختیاری)</label>
              <input id="rule-from" type="datetime-local" dir="ltr" className="input text-left" {...ruleForm.register('effective_from')} />
            </div>
            <div>
              <label htmlFor="rule-to" className="label">اعتبار تا (اختیاری)</label>
              <input id="rule-to" type="datetime-local" dir="ltr" className="input text-left" {...ruleForm.register('effective_to')} />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={createRule.isPending} className="btn-primary flex-1">
              {createRule.isPending ? 'در حال ذخیره…' : 'ذخیره'}
            </button>
            <button type="button" onClick={() => setCreateOpen(false)} className="btn-secondary flex-1">
              انصراف
            </button>
          </div>
        </form>
      </Modal>

      {/* Edit modal: only fields the backend PATCH accepts */}
      <Modal open={editing !== null} title="ویرایش تعرفه" onClose={() => setEditing(null)}>
        <p className="mb-4 text-sm text-neutral-600 dark:text-slate-400">
          واحد، قیمت و اندازه واحد نسخه‌بندی می‌شوند؛ برای تغییر آن‌ها تعرفه جدید بسازید.
        </p>
        <form onSubmit={editForm.handleSubmit(onEditRule)} className="flex flex-col gap-4" noValidate>
          <label className="flex items-center gap-2 text-sm font-medium">
            <input type="checkbox" className="h-5 w-5 accent-amber-600" {...editForm.register('is_active')} />
            تعرفه فعال باشد
          </label>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="edit-min" className="label">حداقل دریافتی (تومان)</label>
              <input id="edit-min" type="number" min={0} step="any" dir="ltr" className="input text-left" {...editForm.register('minimum_charge_toman')} />
            </div>
            <div>
              <label htmlFor="edit-max" className="label">حداکثر دریافتی (تومان)</label>
              <input id="edit-max" type="number" min={0} step="any" dir="ltr" className="input text-left" {...editForm.register('maximum_charge_toman')} />
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="edit-from" className="label">اعتبار از</label>
              <input id="edit-from" type="datetime-local" dir="ltr" className="input text-left" {...editForm.register('effective_from')} />
            </div>
            <div>
              <label htmlFor="edit-to" className="label">اعتبار تا</label>
              <input id="edit-to" type="datetime-local" dir="ltr" className="input text-left" {...editForm.register('effective_to')} />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={updateRule.isPending} className="btn-primary flex-1">
              {updateRule.isPending ? 'در حال ذخیره…' : 'ذخیره'}
            </button>
            <button type="button" onClick={() => setEditing(null)} className="btn-secondary flex-1">
              انصراف
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
