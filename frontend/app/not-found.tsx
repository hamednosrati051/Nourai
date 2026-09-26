export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-lg flex-col items-center justify-center px-4 text-center">
      <p className="text-6xl font-bold text-brand-600 dark:text-brand-400">۴۰۴</p>
      <h1 className="mt-4 text-xl font-bold">صفحه موردنظر پیدا نشد</h1>
      <p className="mt-2 text-neutral-600 dark:text-slate-400">
        نشانی واردشده اشتباه است یا صفحه حذف شده است.
      </p>
      <a href="/" className="btn-primary mt-6">
        بازگشت به صفحه اصلی
      </a>
    </main>
  );
}
