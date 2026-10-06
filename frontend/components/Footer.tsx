import Link from 'next/link';
import { BRAND } from '@/lib/config';

/** Footer with brand, legal links and the Enamad trust seal. */
export function Footer() {
  return (
    <footer className="border-t border-neutral-200 bg-neutral-50 dark:border-white/10 dark:bg-navy-950">
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-4 px-4 py-8 sm:flex-row sm:px-6">
        <p className="text-sm text-neutral-600 dark:text-slate-400">
          © {new Date().getFullYear()} {BRAND.fa} — پلتفرم هوش مصنوعی
        </p>
        <nav aria-label="پیوندهای قانونی" className="flex items-center gap-4 text-sm">
          <Link href="/contact" className="inline-link text-neutral-600 hover:text-neutral-900 dark:text-slate-400 dark:hover:text-slate-100">
            تماس با ما
          </Link>
          <Link href="/terms" className="inline-link text-neutral-600 hover:text-neutral-900 dark:text-slate-400 dark:hover:text-slate-100">
            قوانین استفاده
          </Link>
          <Link href="/privacy" className="inline-link text-neutral-600 hover:text-neutral-900 dark:text-slate-400 dark:hover:text-slate-100">
            حریم خصوصی
          </Link>
        </nav>
        <a
          referrerPolicy="origin"
          target="_blank"
          rel="noopener noreferrer"
          href="https://trustseal.enamad.ir/?id=8058389&Code=cMmPln8sGmEQlZXXJjuLHkIjjey0LK5L"
          aria-label="نماد اعتماد الکترونیکی"
          className="shrink-0"
        >
          <img
            referrerPolicy="origin"
            src="https://trustseal.enamad.ir/logo.aspx?id=8058389&Code=cMmPln8sGmEQlZXXJjuLHkIjjey0LK5L"
            alt="نماد اعتماد الکترونیکی"
            width={80}
            height={87}
            className="h-[87px] w-[80px] rounded bg-white p-1"
            loading="lazy"
          />
        </a>
      </div>
    </footer>
  );
}
