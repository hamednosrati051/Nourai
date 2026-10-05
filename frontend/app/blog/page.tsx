import type { Metadata } from 'next';
import Link from 'next/link';
import { BRAND } from '@/lib/config';
import { PillHeader } from '@/components/PillHeader';
import { Footer } from '@/components/Footer';

export const metadata: Metadata = {
  title: 'بلاگ هوش مصنوعی',
  description: 'مقالات فارسی درباره هوش مصنوعی: آموزش، کاربردها و راهنمای استفاده از نورا.',
};

interface BlogPost {
  slug: string;
  title: string;
  description: string;
  created_at: string;
}

async function getPosts(): Promise<BlogPost[]> {
  try {
    const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}/api/v1/blog`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return [];
    const json = await res.json();
    return json.data ?? [];
  } catch {
    return [];
  }
}

function toFaDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium' }).format(new Date(iso));
  } catch {
    return '';
  }
}

export default async function BlogPage() {
  const posts = await getPosts();
  return (
    <div className="relative flex min-h-screen flex-col">
      <PillHeader />
      <main className="mx-auto w-full max-w-4xl flex-1 px-4 pb-20 pt-32 sm:px-6">
        <p className="badge badge-warning mb-3">بلاگ</p>
        <h1 className="text-3xl font-black">
          مقالات <span className="text-gradient">{BRAND.fa}</span>
        </h1>
        <p className="mt-2 text-sm text-neutral-600 dark:text-slate-400">
          آموزش‌ها و راهنماهای فارسی درباره هوش مصنوعی و استفاده از نورا.
        </p>
        {posts.length === 0 ? (
          <p className="mt-8 text-neutral-500">هنوز مقاله‌ای منتشر نشده است.</p>
        ) : (
          <div className="mt-8 flex flex-col gap-4">
            {posts.map((post) => (
              <Link
                key={post.slug}
                href={`/blog/${post.slug}`}
                className="card transition-shadow hover:shadow-lg"
              >
                <h2 className="text-lg font-extrabold">{post.title}</h2>
                <p className="mt-2 text-sm leading-7 text-neutral-600 dark:text-slate-400">
                  {post.description}
                </p>
                <p className="mt-3 text-xs text-neutral-400">{toFaDate(post.created_at)}</p>
              </Link>
            ))}
          </div>
        )}
      </main>
      <Footer />
    </div>
  );
}
