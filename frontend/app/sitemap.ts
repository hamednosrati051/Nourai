import type { MetadataRoute } from 'next';

import { BLOG_POSTS } from './blog/posts';

const BASE = 'https://inourai.ir';

export default function sitemap(): MetadataRoute.Sitemap {
  const posts: MetadataRoute.Sitemap = BLOG_POSTS.map((p) => ({
    url: `${BASE}/blog/${p.slug}`,
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
