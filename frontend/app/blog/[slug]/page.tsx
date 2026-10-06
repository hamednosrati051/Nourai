import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowRight, Calendar } from 'lucide-react';
import { PillHeader } from '@/components/PillHeader';
import { Footer } from '@/components/Footer';

interface BlogPost {
  slug: string;
  title: string;
  description: string;
  cover_image_url: string | null;
  content: string[];
  created_at: string;
}

const API_BASE = process.env.BLOG_API_URL || 'http://127.0.0.1:8000';

async function getPost(slug: string): Promise<BlogPost | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/blog/${slug}`, {
      next: { revalidate: 300 },
    });
    if (!res.ok) return null;
    const json = await res.json();
    return json.data ?? null;
  } catch {
    return null;
  }
}

export async function generateMetadata({
  params,
}: {
  params: { slug: string };
}): Promise<Metadata> {
  const post = await getPost(params.slug);
  if (!post) return {};
  const images = post.cover_image_url ? [post.cover_image_url] : [];
  return {
    title: post.title,
    description: post.description,
    alternates: {
      canonical: `https://inourai.ir/blog/${post.slug}`,
    },
    openGraph: {
      title: post.title,
      description: post.description,
      type: 'article',
      url: `https://inourai.ir/blog/${post.slug}`,
      images,
    },
  };
}

function toFaDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat('fa-IR', { dateStyle: 'long' }).format(new Date(iso));
  } catch {
    return '';
  }
}

export default async function BlogPostPage({ params }: { params: { slug: string } }) {
  const post = await getPost(params.slug);
  if (!post) notFound();

  return (
    <div className="relative flex min-h-screen flex-col overflow-x-clip">
      <PillHeader />

      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -top-32 right-1/4 h-96 w-96 rounded-full bg-brand-400/20 blur-3xl dark:bg-brand-500/10" />
      </div>

      <main className="relative mx-auto w-full max-w-3xl flex-1 px-4 pb-20 pt-28 sm:px-6">
        <Link
          href="/blog"
          className="inline-flex items-center gap-1.5 text-sm font-bold text-brand-600 hover:underline dark:text-brand-400"
        >
          <ArrowRight className="h-4 w-4" />
          بازگشت به بلاگ
        </Link>

        <h1 className="mt-6 text-3xl font-black leading-[1.7] sm:text-4xl">{post.title}</h1>
        <p className="mt-3 flex items-center gap-1.5 text-sm text-neutral-400">
          <Calendar className="h-4 w-4" />
          {toFaDate(post.created_at)}
        </p>

        {post.cover_image_url && (
          <div className="mt-8 overflow-hidden rounded-3xl shadow-lg">
            <img
              src={post.cover_image_url}
              alt={post.title}
              className="aspect-[16/9] w-full object-cover"
            />
          </div>
        )}

        <article className="mt-8 flex flex-col gap-6">
          <p className="text-lg font-medium leading-9 text-neutral-600 dark:text-slate-300">
            {post.description}
          </p>
          {post.content.map((para, i) => {
            const imgMatch = para.match(/^!\[.*?]\((.*?)\)$/);
            if (imgMatch) {
              return (
                <img
                  key={i}
                  src={imgMatch[1]}
                  alt=""
                  className="mx-auto max-h-96 rounded-lg object-contain"
                  loading="lazy"
                />
              );
            }
            return (
              <p key={i} className="leading-9 text-neutral-700 dark:text-slate-300">
                {para}
              </p>
            );
          })}
        </article>

        <div className="card mt-12 bg-gradient-to-br from-brand-50 to-violet-50 text-center dark:from-brand-950/40 dark:to-violet-950/20">
          <p className="text-lg font-extrabold">می‌خواهید امتحان کنید؟</p>
          <p className="mt-2 text-sm text-neutral-600 dark:text-slate-400">
            همین حالا با نورا شروع کنید — رایگان.
          </p>
          <Link href="/auth/login" className="btn-primary mt-5 inline-block px-10 py-3.5">
            شروع با نورا
          </Link>
        </div>
      </main>
      <Footer />
    </div>
  );
}
