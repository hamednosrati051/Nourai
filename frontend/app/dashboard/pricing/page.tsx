'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Image as ImageIcon, MessageSquare, Mic, ScanEye, Volume2, FileText, Loader2 } from 'lucide-react';
import { PillHeader } from '@/components/PillHeader';
import { FloatingNav } from '@/components/FloatingNav';

interface PricingRule {
  billing_unit: string;
  unit_price_usd: number;
  unit_size: number;
}

interface ModelPricing {
  slug: string;
  display_name: string;
  capability: string;
  pricing: PricingRule[];
}

interface PricingData {
  usd_to_irr: number;
  models: ModelPricing[];
}

const CAPABILITY_META: Record<string, { title: string; unit: string; description: string; color: string; icon: any }> = {
  text: {
    title: 'گفت‌وگوی متنی',
    unit: 'هر ۱٬۰۰۰ کلمه',
    description: 'مکالمه با مدل‌های زبانی، از جمله دستیار قرارداد',
    color: '#38bdf8',
    icon: MessageSquare,
  },
  speech_to_text: {
    title: 'تبدیل صوت به متن',
    unit: 'هر دقیقه',
    description: 'پیاده‌سازی صوت فارسی به متن (شنوا)',
    color: '#f472b6',
    icon: Mic,
  },
  text_to_speech: {
    title: 'تبدیل متن به صوت',
    unit: 'هر دقیقه',
    description: 'تبدیل متن به گفتار فارسی',
    color: '#34d399',
    icon: Volume2,
  },
  generate_image: {
    title: 'تولید تصویر',
    unit: 'هر تصویر',
    description: 'ساخت تصویر از توضیح متنی',
    color: '#a78bfa',
    icon: ImageIcon,
  },
  edit_image: {
    title: 'ویرایش تصویر',
    unit: 'هر تصویر',
    description: 'ویرایش و تغییر تصویر',
    color: '#fbbf24',
    icon: ScanEye,
  },
  vision: {
    title: 'تحلیل تصویر',
    unit: 'هر تصویر',
    description: 'تحلیل و تفسیر تصویر، از جمله برگه آزمایش و قرارداد',
    color: '#f97316',
    icon: FileText,
  },
};

function formatToman(amount: number): string {
  return `≈ ${Math.round(amount).toLocaleString('fa-IR')} تومان`;
}

function calculatePrice(model: ModelPricing, usdToIrr: number): string {
  if (!model.pricing.length || !usdToIrr) return '—';
  
  const rule = model.pricing[0];
  if (!rule) return '—';

  // Vision: input (image ~1000 tokens) + output (~500 tokens)
  if (model.capability === 'vision') {
    const inputRule = model.pricing.find(r => r.billing_unit === 'input_token');
    const outputRule = model.pricing.find(r => r.billing_unit === 'output_token');
    const inputUsd = (inputRule?.unit_price_usd || 0) * 1000;
    const outputUsd = (outputRule?.unit_price_usd || 0) * 500;
    const totalIrr = (inputUsd + outputUsd) * usdToIrr;
    return formatToman(totalIrr / 10);
  }

  const priceUsd = rule.unit_price_usd;
  
  if (model.capability === 'text') {
    // ~1500 tokens per 1000 words, input + output
    const inputRule = model.pricing.find(r => r.billing_unit === 'input_token');
    const outputRule = model.pricing.find(r => r.billing_unit === 'output_token');
    const inputUsd = (inputRule?.unit_price_usd || 0) * 750;
    const outputUsd = (outputRule?.unit_price_usd || 0) * 750;
    const totalIrr = (inputUsd + outputUsd) * usdToIrr;
    return formatToman(totalIrr / 10);
  }
  
  if (model.capability === 'speech_to_text' || model.capability === 'text_to_speech') {
    // Per minute estimate (60 seconds)
    const totalUsd = priceUsd * 60 / rule.unit_size;
    return formatToman(totalUsd * usdToIrr / 10);
  }
  
  // Per image/request
  const totalIrr = priceUsd * usdToIrr;
  return formatToman(totalIrr / 10);
}

export default function PricingPage() {
  const [data, setData] = useState<PricingData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch('/api/v1/site/pricing')
      .then((r) => r.json())
      .then((json) => {
        if (json.data) {
          setData(json.data);
        } else {
          setError(true);
        }
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, []);

  return (
    <div className="min-h-screen">
      <PillHeader />
      <FloatingNav />

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-20 pt-28 sm:px-6 md:pe-24">
        <Link
          href="/dashboard"
          className="mb-6 inline-flex items-center gap-1.5 text-sm font-bold text-neutral-600 hover:text-neutral-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          <ArrowRight className="h-4 w-4" />
          بازگشت به داشبورد
        </Link>

        <div className="mb-8">
          <p className="badge badge-warning mb-3">تعرفه‌ها</p>
          <h1 className="text-3xl font-black">تعرفه خدمات</h1>
          <p className="mt-2 text-sm text-neutral-600 dark:text-slate-400">
            هزینه هر سرویس به تومان. مبلغ دقیق هر درخواست از کیف پول شما کسر می‌شود.
          </p>
          {data && data.usd_to_irr > 0 && (
            <p className="mt-1 text-xs text-neutral-500">
              نرخ دلار: {data.usd_to_irr.toLocaleString('fa-IR')} ریال
            </p>
          )}
        </div>

        {loading && (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-8 w-8 animate-spin text-neutral-400" />
          </div>
        )}

        {error && (
          <div className="py-20 text-center text-sm text-neutral-500">
            خطا در بارگذاری تعرفه‌ها. لطفاً دوباره تلاش کنید.
          </div>
        )}

        {data && !loading && (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {data.models.map((model) => {
              const meta = CAPABILITY_META[model.capability];
              if (!meta) return null;
              const Icon = meta.icon;
              const price = calculatePrice(model, data.usd_to_irr);
              return (
                <div key={model.slug} className="card group" style={{ ['--svc' as string]: meta.color }}>
                  <span aria-hidden="true" className="service-icon">
                    <Icon className="h-7 w-7" style={{ color: meta.color }} />
                  </span>
                  <h3 className="text-lg font-extrabold text-neutral-900 dark:text-white">
                    {meta.title}
                  </h3>
                  <p className="flex-1 text-sm leading-7 text-neutral-600 dark:text-slate-400">
                    {meta.description}
                  </p>
                  <div className="mt-2 flex items-baseline justify-between">
                    <span className="text-xs text-neutral-500">{meta.unit}</span>
                    <span className="text-lg font-black" style={{ color: meta.color }}>
                      {price}
                    </span>
                  </div>
                  <span aria-hidden="true" className="service-accent" />
                </div>
              );
            })}
          </div>
        )}

        <p className="mt-6 text-center text-xs text-neutral-500">
          قیمت‌ها بر اساس تعرفه‌های فعلی و نرخ دلار محاسبه شده‌اند و ممکن است تغییر کنند. مبلغ نهایی هر درخواست در تاریخچه مصرف ثبت می‌شود.
        </p>
      </main>
    </div>
  );
}
