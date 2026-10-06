import { BRAND } from '@/lib/config';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';

const SECTIONS = [
  {
    title: '۱. چه اطلاعاتی جمع می‌کنیم',
    body: 'شماره موبایل (برای ورود)، محتوایی که وارد می‌کنید (متن، صوت، تصویر)، سوابق تراکنش‌های کیف پول و اشتراک، و اطلاعات فنی پایه (نوع دستگاه و مرورگر) برای امنیت و بهبود سرویس.',
  },
  {
    title: '۲. چرا این اطلاعات را نگه می‌داریم',
    body: 'برای ارائه سرویس، احراز هویت، محاسبه هزینه‌ها، جلوگیری از سوءاستفاده و رعایت الزامات قانونی. بدون این اطلاعات امکان ارائه خدمت وجود ندارد.',
  },
  {
    title: '۳. اشتراک‌گذاری اطلاعات',
    body: 'اطلاعات شما را نمی‌فروشیم. محتوا فقط برای پردازش به ارائه‌دهندگان مدل هوش مصنوعی ارسال می‌شود. در صورت حکم قانونی، ممکن است ملزم به ارائه اطلاعات به مراجع ذی‌صلاح باشیم.',
  },
  {
    title: '۴. امنیت',
    body: 'از روش‌های استاندارد برای محافظت از اطلاعات استفاده می‌کنیم، اما هیچ سیستمی صددرصد امن نیست. رمز عبور خود را با کسی به اشتراک نگذارید.',
  },
  {
    title: '۵. حقوق شما',
    body: 'می‌توانید درخواست مشاهده، اصلاح یا حذف اطلاعات حساب خود را ثبت کنید. حذف حساب به معنای از دست رفتن سوابق و موجودی کیف پول است.',
  },
  {
    title: '۶. کوکی‌ها',
    body: 'از کوکی‌ها برای نگه داشتن نشست ورود و ترجیحات شما (مثل تم) استفاده می‌کنیم.',
  },
  {
    title: '۷. تغییرات',
    body: 'ممکن است این سیاست را به‌روزرسانی کنیم. نسخه جدید در همین صفحه منتشر می‌شود.',
  },
];

/** Privacy Policy — standard text. */
export default function PrivacyPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-12 sm:px-6">
        <h1 className="text-2xl font-extrabold">حریم خصوصی {BRAND.fa}</h1>
        <p className="mt-2 text-sm text-neutral-500">آخرین به‌روزرسانی: مهر ۱۴۰۴</p>
        <div className="mt-6 space-y-6">
          {SECTIONS.map((s) => (
            <section key={s.title}>
              <h2 className="mb-2 text-lg font-extrabold">{s.title}</h2>
              <p className="leading-8 text-neutral-700 dark:text-slate-300">{s.body}</p>
            </section>
          ))}
        </div>
      </main>
      <Footer />
    </div>
  );
}
