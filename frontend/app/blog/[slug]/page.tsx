import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { PillHeader } from '@/components/PillHeader';
import { Footer } from '@/components/Footer';

interface BlogPost {
  slug: string;
  title: string;
  description: string;
  content: string[];
  created_at: string;
}

async function getPost(slug: string): Promise<BlogPost | null> {
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL || ''}/api/v1/blog/${slug}`,
      { next: { revalidate: 300 } },
    );
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
  return {
    title: post.title,
    description: post.description,
    openGraph: {
      title: post.title,
      description: post.description,
      type: 'article',
    },
  };
}

function toFaDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium' }).format(new Date(iso));
  } catch {
    return '';
  }
}

export default async function BlogPostPage({ params }: { params: { slug: string } }) {
  const post = await getPost(params.slug);
  if (!post) notFound();

  return (
    <div className="relative flex min-h-screen flex-col">
      <PillHeader />
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 pb-20 pt-32 sm:px-6">
        <Link href="/blog" className="inline-link text-sm font-bold">
          → بازگشت به بلاگ
        </Link>
        <h1 className="mt-4 text-3xl font-black leading-[1.6]">{post.title}</h1>
        <p className="mt-2 text-xs text-neutral-400">{toFaDate(post.created_at)}</p>
        <article className="mt-8 flex flex-col gap-5">
          {post.content.map((para, i) => (
            <p key={i} className="leading-9 text-neutral-700 dark:text-slate-300">
              {para}
            </p>
          ))}
        </article>
        <div className="card mt-10 text-center">
          <p className="font-bold">می‌خواهید امتحان کنید؟</p>
          <Link href="/auth/login" className="btn-primary mt-4 inline-block px-8 py-3">
            شروع رایگان با نورا
          </Link>
        </div>
      </main>
      <Footer />
    </div>
  );
}
