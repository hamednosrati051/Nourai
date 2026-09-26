'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost } from '@/lib/api';
import type { Plan } from '@/types/api';

/**
 * Public pricing plans (NOT hard-coded). Sorted by `sort_order` as served by
 * GET /api/v1/plans; the client re-sorts defensively.
 */
export function usePlans() {
  return useQuery({
    queryKey: ['plans'],
    queryFn: async () => {
      const plans = await apiGet<Plan[]>('/plans');
      return [...plans].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
    },
    staleTime: 5 * 60_000,
  });
}

/** Activate the free plan directly (no payment): POST /api/v1/plans/{id}/activate. */
export function useActivatePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => apiPost<{ plan: Plan }>('/plans/{id}/activate'.replace('{id}', planId)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['me', 'plan'] });
      queryClient.invalidateQueries({ queryKey: ['plans'] });
    },
  });
}

export interface MyPlanResponse {
  plan: Plan | null;
}

/**
 * The current user's active plan. Tolerant of the backend returning either
 * `{ plan: Plan | null }` or the plan directly.
 */
export function useMyPlan(enabled = true) {
  return useQuery({
    queryKey: ['me', 'plan'],
    queryFn: async (): Promise<Plan | null> => {
      const data = await apiGet<MyPlanResponse | Plan | null>('/me/plan');
      if (data && typeof data === 'object' && 'plan' in data) {
        return (data as MyPlanResponse).plan ?? null;
      }
      return (data as Plan | null) ?? null;
    },
    enabled,
    staleTime: 60_000,
  });
}
