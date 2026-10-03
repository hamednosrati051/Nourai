'use client';

import Link from 'next/link';
import { BRAND } from '@/lib/config';
import { useMe } from '@/features/auth/hooks';
import { useGallery } from '@/features/gallery/hooks';
import { PillHeader } from '@/components/PillHeader';
import { Footer } from '@/components/Footer';
import { ServiceCard } from '@/components/ServiceCard';
import { PlansSection } from '@/components/PlansSection';
import { GalleryCarousel } from '@/components/GalleryCarousel';

const SERVICES = [
  {
    icon: '💬',
    title: 'گفتگو',
    description: 'گفت‌وگوی متنی هوشمند با مدل‌های زبانی؛ پاسخ دقیق، سریع و کاملاً فارسی.',
    href: '/dashboard/chat',
    color: '#3b82f6',
  },
  {
    icon: '🎨',
    title: 'تولید تصویر',
    description: 'از روی متن تصویر بسازید؛ با برآورد شفاف هزینه، قبل از ثبت نهایی.',
    href: '/dashboard/image',
    color: '#8b5cf6',
  },
  {
    icon: '🎙️',
    title: 'نورا',
    description: 'صدا بفرستید، متن و پاسخ صوتی بگیرید؛ یک رفت‌وبرگشت کامل و روان.',
    href: '/dashboard/voice',
    color: '#10b981',
  },
  {
    icon: '🔍',
    title: 'تحلیل تصویر',
    description: 'تصویر خود را بدهید؛ ویرایش کنید یا تحلیل هوشمند تحویل بگیرید.',
    href: '/dashboard/image',
    color: '#f59e0b',
  },
];

/** Nourai home: polished single page — hero, services, plans, gallery slider. */
export default function HomePage() {
  const { data: user } = useMe();
  const gallery = useGallery();
  const authed = !!user;
  const ctaHref = authed ? '/dashboard' : '/auth/login';

  return (
    <div className="relative flex min-h-screen flex-col overflow-x-clip">
      <PillHeader />

      {/* Ambient background glows */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-32 right-1/4 h-96 w-96 rounded-full bg-brand-400/20 blur-3xl dark:bg-brand-500/10" />
        <div className="absolute top-40 -left-24 h-80 w-80 rounded-full bg-violet-500/15 blur-3xl dark:bg-violet-500/10" />
        <div className="absolute top-[55%] right-0 h-72 w-72 rounded-full bg-sky-500/10 blur-3xl dark:bg-sky-500/[0.07]" />
      </div>

      <main className="relative flex-1">
        {/* Hero */}
        <section className="mx-auto max-w-4xl px-4 pb-10 pt-32 text-center sm:px-6 sm:pt-40">
          <p className="badge badge-warning mb-5 animate-pulse-soft">پلتفرم هوش مصنوعی فارسی</p>
          <h1 className="text-4xl font-black leading-[1.3] sm:text-6xl sm:leading-[1.25]">
            هوش مصنوعی،
            <br />
            <span className="text-gradient">به زبان شما</span>
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-base leading-8 text-neutral-600 dark:text-slate-400">
            {BRAND.fa} گفت‌وگو، تولید تصویر و تعامل صوتی را در یک پلتفرم ساده و فارسی کنار هم
            آورده — با کیف پول شفاف و قیمت‌گذاری روشن.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link href={ctaHref} className="btn-primary px-8 py-3.5 text-base shadow-lg shadow-brand-500/25">
              {authed ? 'ورود به داشبورد' : 'ثبت‌نام / ورود'}
            </Link>
            <Link href="/gallery" className="btn-secondary px-8 py-3.5 text-base">
              مشاهده گالری
            </Link>
          </div>

          {/* Capability chips */}
          <ul aria-label="قابلیت‌ها" className="mt-10 flex flex-wrap items-center justify-center gap-2.5">
            {[
              { icon: '💬', label: 'متن' },
              { icon: '🎙️', label: 'صوت' },
              { icon: '🎨', label: 'تصویر' },
            ].map((c) => (
              <li
                key={c.label}
                className="flex items-center gap-2 rounded-full border border-neutral-200 bg-white/70 px-4 py-2 text-sm font-medium backdrop-blur dark:border-white/10 dark:bg-navy-800/70 dark:text-slate-300"
              >
                <span aria-hidden="true">{c.icon}</span>
                {c.label}
              </li>
            ))}
          </ul>
        </section>

        {/* Services grid */}
        <section aria-labelledby="services-heading" className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6">
          <h2 id="services-heading" className="mb-8 text-center text-2xl font-black sm:text-3xl">
            سرویس‌های <span className="text-gradient">{BRAND.fa}</span>
          </h2>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {SERVICES.map((s) => (
              <ServiceCard
                key={s.title}
                icon={s.icon}
                title={s.title}
                description={s.description}
                href={authed ? s.href : '/auth/login'}
                color={s.color}
                ctaLabel={authed ? 'شروع' : 'ورود و شروع'}
              />
            ))}
          </div>
        </section>

        {/* Plans */}
        <PlansSection />

        {/* Gallery slider */}
        <section aria-labelledby="creations-heading" className="mx-auto w-full max-w-5xl px-4 pb-20 sm:px-6">
          <div className="mb-8 flex items-center justify-between gap-4">
            <h2 id="creations-heading" className="text-2xl font-black sm:text-3xl">
              ساخته‌های <span className="text-gradient">کاربران</span>
            </h2>
            <Link
              href="/gallery"
              className="inline-link shrink-0 font-bold text-brand-700 hover:underline dark:text-brand-300"
            >
              مشاهده گالری ←
            </Link>
          </div>
          <GalleryCarousel
            items={gallery.data}
            isLoading={gallery.isLoading}
            isError={gallery.isError}
            onRetry={() => gallery.refetch()}
          />
        </section>
      </main>

      <Footer />
    </div>
  );
}
