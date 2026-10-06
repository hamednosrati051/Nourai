import Link from 'next/link';
import { BRAND } from '@/lib/config';

/** Simple public footer with brand name and legal link placeholders. */
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
      </div>
    </footer>
  );
}
