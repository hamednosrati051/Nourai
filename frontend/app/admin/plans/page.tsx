'use client';

import { CreditCard, Star } from 'lucide-react';
import { useState } from 'react';
import {
  PlanInput,
  useAdminPlans,
  useCreateAdminPlan,
  useDeleteAdminPlan,
  useUpdateAdminPlan,
} from '@/features/admin/hooks';
import { ResponsiveTable } from '@/components/DataTable';
import { EmptyState } from '@/components/EmptyState';
import { ErrorState } from '@/components/ErrorState';
import { LoadingSpinner } from '@/components/LoadingSpinner';
import { Modal } from '@/components/Modal';
import { TextAreaField, TextField, NumberField } from '@/components/FormFields';
import { useToast } from '@/components/Toast';
import { formatToman, tomanToIrr, irrToToman } from '@/lib/currency';
import type { Plan } from '@/types/api';

const emptyForm = {
  name: '',
  tagline: '',
  priceToman: '',
  period: '',
  features: '',
  limits: '',
  quota_text: '',
  quota_image: '',
  quota_audio: '',
  is_free: false,
  is_featured: false,
  is_active: true,
  sort_order: '0',
};

type FormState = typeof emptyForm;

export default function AdminPlansPage() {
  const { toast } = useToast();
  const plans = useAdminPlans();
  const createPlan = useCreateAdminPlan();
  const updatePlan = useUpdateAdminPlan();
  const deletePlan = useDeleteAdminPlan();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Plan | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);

  const openAdd = () => {
    setEditing(null);
    setForm(emptyForm);
    setModalOpen(true);
  };

  const openEdit = (plan: Plan) => {
    setEditing(plan);
    const ul = plan.usage_limits ?? {};
    setForm({
      name: plan.name,
      tagline: plan.tagline ?? '',
      priceToman: String(irrToToman(plan.amount_irr)),
      period: plan.period ?? '',
      features: plan.features.join('\n'),
      limits: plan.limits.join('\n'),
      quota_text: ul.monthly_text != null ? String(ul.monthly_text) : '',
      quota_image: ul.monthly_image != null ? String(ul.monthly_image) : '',
      quota_audio: ul.monthly_audio_minutes != null ? String(ul.monthly_audio_minutes) : '',
      is_free: plan.is_free,
      is_featured: plan.is_featured,
      is_active: plan.is_active,
      sort_order: String(plan.sort_order),
    });
    setModalOpen(true);
  };

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const toInput = (): PlanInput => {
    const lines = (v: string) =>
      v
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
    const isFree = form.is_free;
    const num = (v: string) => {
      const n = Number(v);
      return v.trim() !== '' && Number.isInteger(n) && n >= 0 ? n : undefined;
    };
    const usage_limits: Record<string, number> = {};
    const qt = num(form.quota_text);
    const qi = num(form.quota_image);
    const qa = num(form.quota_audio);
    if (qt !== undefined) usage_limits.monthly_text = qt;
    if (qi !== undefined) usage_limits.monthly_image = qi;
    if (qa !== undefined) usage_limits.monthly_audio_minutes = qa;
    return {
      name: form.name.trim(),
      tagline: form.tagline.trim() || undefined,
      amount_irr: isFree ? 0 : tomanToIrr(Number(form.priceToman) || 0),
      period: form.period.trim() || undefined,
      features: lines(form.features),
      limits: lines(form.limits),
      usage_limits,
      is_free: isFree,
      is_featured: form.is_featured,
      is_active: form.is_active,
      sort_order: Number(form.sort_order) || 0,
    };
  };

  const save = () => {
    const input = toInput();
    if (!input.name) {
      toast('نام اشتراک الزامی است.', 'error');
      return;
    }
    if (!input.is_free && input.amount_irr <= 0) {
      toast('قیمت اشتراک پولی باید بیشتر از صفر باشد.', 'error');
      return;
    }
    if (editing) {
      updatePlan.mutate(
        { id: editing.id, input },
        {
          onSuccess: () => {
            toast('اشتراک به‌روزرسانی شد.', 'success');
            setModalOpen(false);
          },
          onError: () => toast('به‌روزرسانی اشتراک ناموفق بود.', 'error'),
        },
      );
    } else {
      createPlan.mutate(input, {
        onSuccess: () => {
          toast('اشتراک جدید ثبت شد.', 'success');
          setModalOpen(false);
        },
        onError: () => toast('ثبت اشتراک ناموفق بود.', 'error'),
      });
    }
  };

  const remove = (plan: Plan) => {
    if (!window.confirm(`اشتراک «${plan.name}» حذف شود؟ این عمل قابل بازگشت نیست.`)) return;
    deletePlan.mutate(plan.id, {
      onSuccess: () => toast('اشتراک حذف شد.', 'success'),
      onError: () => toast('حذف اشتراک ناموفق بود.', 'error'),
    });
  };

  const busy = createPlan.isPending || updatePlan.isPending;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold">مدیریت اشتراک‌ها</h1>
          <p className="text-sm text-neutral-500 dark:text-slate-400">
            اشتراک‌ها از همین‌جا در صفحه اصلی نمایش داده می‌شوند؛ قیمت‌ها به تومان وارد و به IRR ذخیره می‌شوند.
          </p>
        </div>
        <button type="button" onClick={openAdd} className="btn-primary">
          افزودن اشتراک
        </button>
      </div>

      {plans.isLoading && <LoadingSpinner label="در حال بارگذاری اشتراک‌ها…" />}
      {plans.isError && (
        <ErrorState message="بارگذاری اشتراک‌ها ناموفق بود." onRetry={() => plans.refetch()} />
      )}
      {plans.data && plans.data.length === 0 && (
        <EmptyState icon={CreditCard} title="اشتراکی ثبت نشده است" description="اولین اشتراک را با «افزودن اشتراک» بسازید." />
      )}

      {plans.data && plans.data.length > 0 && (
        <ResponsiveTable
          ariaLabel="جدول اشتراک‌ها"
          columns={[
            { header: 'نام', render: (p: Plan) => <span className="font-bold">{p.name}</span> },
            {
              header: 'قیمت',
              render: (p: Plan) =>
                p.is_free ? (
                  <span className="badge badge-success">رایگان</span>
                ) : (
                  <span className="tabular-nums">{formatToman(p.amount_irr)}</span>
                ),
            },
            { header: 'دوره', render: (p: Plan) => p.period ?? '—' },
            {
              header: 'پیشنهادی',
              render: (p: Plan) =>
                p.is_featured ? <span className="badge badge-warning inline-flex items-center gap-1">پیشنهاد ما <Star aria-hidden="true" className="h-3.5 w-3.5" /></span> : '—',
            },
            {
              header: 'وضعیت',
              render: (p: Plan) =>
                p.is_active ? (
                  <span className="badge badge-success">فعال</span>
                ) : (
                  <span className="badge badge-danger">غیرفعال</span>
                ),
            },
            { header: 'ترتیب', render: (p: Plan) => p.sort_order },
            {
              header: 'اقدام',
              render: (p: Plan) => (
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => openEdit(p)}
                    className="btn-secondary !px-3 !py-1.5 text-xs"
                  >
                    ویرایش
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(p)}
                    disabled={deletePlan.isPending}
                    className="btn-danger !px-3 !py-1.5 text-xs"
                  >
                    حذف
                  </button>
                </div>
              ),
            },
          ]}
          rows={plans.data}
          keyOf={(p) => p.id}
        />
      )}

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? `ویرایش اشتراک «${editing.name}»` : 'افزودن اشتراک جدید'}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <TextField label="نام اشتراک" value={form.name} onChange={(v) => set('name', v)} required placeholder="پایه" />
          <TextField label="توضیح کوتاه" value={form.tagline} onChange={(v) => set('tagline', v)} placeholder="مناسب استفاده روزمره" />
          <NumberField
            label="قیمت (تومان)"
            value={form.priceToman}
            onChange={(v) => set('priceToman', v)}
            min={0}
            disabled={form.is_free}
          />
          <TextField label="دوره" value={form.period} onChange={(v) => set('period', v)} placeholder="ماهانه" />
          <NumberField label="ترتیب نمایش" value={form.sort_order} onChange={(v) => set('sort_order', v)} min={0} />
        </div>
        <div className="mt-4 grid gap-4">
          <TextAreaField
            label="ویژگی‌ها (هر خط یک مورد)"
            value={form.features}
            onChange={(v) => set('features', v)}
            rows={4}
            placeholder={'مکالمه متنی نامحدود\nتولید تصویر پیشرفته'}
          />
          <TextAreaField
            label="محدودیت‌ها (هر خط یک مورد)"
            value={form.limits}
            onChange={(v) => set('limits', v)}
            rows={3}
            placeholder={'۲۰ درخواست متنی در ماه\nبدون دسترسی به مدل‌های پیشرفته'}
          />
        </div>
        <div className="mt-4">
          <p className="mb-2 text-sm font-bold">سقف‌های واقعی سهمیه (عدد؛ خالی = بدون سقف)</p>
          <div className="grid gap-4 sm:grid-cols-3">
            <NumberField label="پیام متنی در ماه" value={form.quota_text} onChange={(v) => set('quota_text', v)} min={0} placeholder="۱۰۰۰" />
            <NumberField label="تصویر در ماه" value={form.quota_image} onChange={(v) => set('quota_image', v)} min={0} placeholder="۱۰" />
            <NumberField label="دقیقه صوت در ماه" value={form.quota_audio} onChange={(v) => set('quota_audio', v)} min={0} placeholder="۶۰" />
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.is_free} onChange={(e) => set('is_free', e.target.checked)} className="h-5 w-5" />
            اشتراک رایگان
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.is_featured} onChange={(e) => set('is_featured', e.target.checked)} className="h-5 w-5" />
            پیشنهادی (نشان «پیشنهاد ما»)
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.is_active} onChange={(e) => set('is_active', e.target.checked)} className="h-5 w-5" />
            فعال
          </label>
        </div>
        <div className="mt-6 flex justify-end gap-3">
          <button type="button" onClick={() => setModalOpen(false)} className="btn-secondary" disabled={busy}>
            انصراف
          </button>
          <button type="button" onClick={save} className="btn-primary" disabled={busy}>
            {busy ? 'در حال ذخیره…' : editing ? 'ذخیره تغییرات' : 'ثبت اشتراک'}
          </button>
        </div>
      </Modal>
    </div>
  );
}
