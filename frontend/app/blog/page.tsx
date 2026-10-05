import type { Metadata } from 'next';
import Link from 'next/link';
import { Calendar, ArrowLeft } from 'lucide-react';
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
  cover_image_url: string | null;
  created_at: string;
}

const API_BASE = process.env.BLOG_API_URL || 'http://127.0.0.1:8000';

async function getPosts(): Promise<BlogPost[]> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/blog`, {
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
    return new Intl.DateTimeFormat('fa-IR', { dateStyle: 'long' }).format(new Date(iso));
  } catch {
    return '';
  }
}

export default async function BlogPage() {
  const posts = await getPosts();

  return (
    <div className="relative flex min-h-screen flex-col overflow-x-clip">
      <PillHeader />

      {/* Ambient background */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-32 right-1/4 h-96 w-96 rounded-full bg-brand-400/20 blur-3xl dark:bg-brand-500/10" />
        <div className="absolute top-40 -left-24 h-80 w-80 rounded-full bg-violet-500/15 blur-3xl dark:bg-violet-500/10" />
      </div>

      <main className="relative mx-auto w-full max-w-6xl flex-1 px-4 pb-20 pt-32 sm:px-6">
        <div className="mb-10 text-center">
          <p className="badge badge-warning mb-3">بلاگ</p>
          <h1 className="text-4xl font-black sm:text-5xl">
            مقالات <span className="text-gradient">{BRAND.fa}</span>
          </h1>
          <p className="mx-auto mt-4 max-w-xl text-neutral-600 dark:text-slate-400">
            آموزش‌ها و راهنماهای فارسی درباره هوش مصنوعی، از مبانی تا کاربردهای عملی.
          </p>
        </div>

        {posts.length === 0 ? (
          <p className="text-center text-neutral-500">هنوز مقاله‌ای منتشر نشده است.</p>
        ) : (
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {posts.map((post) => (
              <Link
                key={post.slug}
                href={`/blog/${post.slug}`}
                className="card group overflow-hidden p-0 transition-all hover:-translate-y-1 hover:shadow-xl"
              >
                <div className="relative aspect-[16/9] overflow-hidden bg-gradient-to-br from-brand-100 to-violet-100 dark:from-brand-900/30 dark:to-violet-900/20">
                  {post.cover_image_url ? (
                    <img
                      src={post.cover_image_url}
                      alt={post.title}
                      className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center">
                      <span className="text-6xl font-black text-brand-300 dark:text-brand-700">ن</span>
                    </div>
                  )}
                </div>
                <div className="p-5">
                  <h2 className="line-clamp-2 text-lg font-extrabold leading-8 group-hover:text-brand-700 dark:group-hover:text-brand-300">
                    {post.title}
                  </h2>
                  <p className="mt-2 line-clamp-2 text-sm leading-7 text-neutral-600 dark:text-slate-400">
                    {post.description}
                  </p>
                  <div className="mt-4 flex items-center justify-between">
                    <span className="flex items-center gap-1.5 text-xs text-neutral-400">
                      <Calendar className="h-3.5 w-3.5" />
                      {toFaDate(post.created_at)}
                    </span>
                    <span className="flex items-center gap-1 text-sm font-bold text-brand-600 dark:text-brand-400">
                      خواندن
                      <ArrowLeft className="h-4 w-4 transition-transform group-hover:-translate-x-1" />
                    </span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
      <Footer />
    </div>
  );
}
