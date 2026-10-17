'use client';

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';
import { GALLERY_MAX_ITEMS } from '@/lib/config';
import type { GalleryItem } from '@/types/api';

/**
 * Public gallery feed: at most GALLERY_MAX_ITEMS latest approved items.
 * kind='image' (default) is the ONLY data source for the homepage carousel.
 */
export function useGallery(kind: 'image' | 'video' = 'image') {
  return useQuery({
    queryKey: ['gallery', kind],
    queryFn: async () => {
      const items = await apiGet<GalleryItem[]>(`/gallery?kind=${kind}`);
      return items.slice(0, GALLERY_MAX_ITEMS);
    },
    staleTime: 60_000,
  });
}
