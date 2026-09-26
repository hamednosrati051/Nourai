'use client';

import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/lib/api';
import type { PublicModel } from '@/types/api';

/** Active models available to the current user. */
export function useModels() {
  return useQuery({
    queryKey: ['models'],
    queryFn: () => apiGet<PublicModel[]>('/models'),
    staleTime: 5 * 60_000,
  });
}
