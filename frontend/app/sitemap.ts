import type { MetadataRoute } from 'next';

const BASE = 'https://inourai.ir';

async function blogSlugs(): Promise<string[]> {
  try {
    // Server-side: hit the backend directly (same machine).
    const res = await fetch(`${process.env.BLOG_API_URL || 'http://127.0.0.1:8000'}/api/v1/blog`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return [];
    const json = await res.json();
    return (json.data ?? []).map((p: { slug: string }) => p.slug);
  } catch {
    return [];
  }
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const slugs = await blogSlugs();
  const posts: MetadataRoute.Sitemap = slugs.map((slug) => ({
    url: `${BASE}/blog/${slug}`,
    changeFrequency: 'monthly',
    priority: 0.7,
  }));
  return [
    { url: BASE, changeFrequency: 'daily', priority: 1 },
    { url: `${BASE}/gallery`, changeFrequency: 'daily', priority: 0.8 },
    { url: `${BASE}/blog`, changeFrequency: 'weekly', priority: 0.8 },
    ...posts,
    { url: `${BASE}/auth`, changeFrequency: 'monthly', priority: 0.5 },
    { url: `${BASE}/privacy`, changeFrequency: 'yearly', priority: 0.3 },
    { url: `${BASE}/terms`, changeFrequency: 'yearly', priority: 0.3 },
  ];
}
