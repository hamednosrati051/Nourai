'use client';

import { useQuery } from '@tanstack/react-query';
import { apiGet, buildQuery } from '@/lib/api';
import { DEFAULT_PAGE_SIZE } from '@/lib/config';
import type { ModelService, Paginated, UsageEvent } from '@/types/api';

export interface UsageFilters {
  page?: number;
  pageSize?: number;
  service?: ModelService | '';
  modelId?: string;
  from?: string;
  to?: string;
}

/** Current user's usage history with server-side filtering. */
export function useUsage(filters: UsageFilters = {}) {
  const { page = 1, pageSize = DEFAULT_PAGE_SIZE, service, modelId, from, to } = filters;
  return useQuery({
    queryKey: ['usage', page, pageSize, service, modelId, from, to],
    queryFn: () =>
      apiGet<Paginated<UsageEvent>>(
        `/usage${buildQuery({
          page,
          page_size: pageSize,
          service: service || undefined,
          model_id: modelId || undefined,
          from: from || undefined,
          to: to || undefined,
        })}`,
      ),
  });
}
