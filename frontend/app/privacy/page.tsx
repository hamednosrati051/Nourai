import { BRAND } from '@/lib/config';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';

/** Placeholder until the privacy text is provided by the product owner. */
export default function PrivacyPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-12 sm:px-6">
        <h1 className="text-2xl font-extrabold">حریم خصوصی {BRAND.fa}</h1>
        <p className="mt-4 leading-8 text-neutral-600 dark:text-slate-400">
          متن سیاست حریم خصوصی به‌زودی در اینجا منتشر می‌شود.
        </p>
      </main>
      <Footer />
    </div>
  );
}
