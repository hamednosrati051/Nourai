'use client';

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';
import { GALLERY_MAX_ITEMS } from '@/lib/config';
import type { GalleryItem } from '@/types/api';

/**
 * Public gallery feed: at most GALLERY_MAX_ITEMS latest approved images.
 * This is the ONLY data source for the homepage carousel.
 */
export function useGallery() {
  return useQuery({
    queryKey: ['gallery'],
    queryFn: async () => {
      const items = await apiGet<GalleryItem[]>('/gallery');
      return items.slice(0, GALLERY_MAX_ITEMS);
    },
    staleTime: 60_000,
  });
}
