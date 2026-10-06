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

/** Buy a paid plan with wallet credit: POST /api/v1/plans/{id}/purchase. */
export function usePurchasePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (planId: string) => apiPost<{ subscription: unknown }>(`/plans/${planId}/purchase`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['me', 'plan'] });
      queryClient.invalidateQueries({ queryKey: ['wallet'] });
      queryClient.invalidateQueries({ queryKey: ['plans'] });
    },
  });
}

export interface MySubscription {
  id: string;
  plan_id: string;
  plan: Plan | null;
  status: string;
  usage_counters: Record<string, number>;
  over_quota: string[];
  remaining: Record<string, number>;
  days_remaining: number;
}

export interface MySubscriptionResponse {
  subscription: MySubscription | null;
}

/** Full subscription (counters + soft over-quota signal). */
export function useMySubscription(enabled = true) {
  return useQuery({
    queryKey: ['me', 'subscription'],
    queryFn: async (): Promise<MySubscription | null> => {
      const data = await apiGet<MySubscriptionResponse>('/me/plan');
      return data?.subscription ?? null;
    },
    enabled,
    staleTime: 60_000,
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
 * The current user's active plan. The backend returns
 * `{ subscription: { plan } }`; tolerated shapes: `{ plan }` or the plan directly.
 */
export function useMyPlan(enabled = true) {
  return useQuery({
    queryKey: ['me', 'plan'],
    queryFn: async (): Promise<Plan | null> => {
      const data = await apiGet<MySubscriptionResponse | MyPlanResponse | Plan | null>('/me/plan');
      if (data && typeof data === 'object' && 'subscription' in data) {
        return (data as MySubscriptionResponse).subscription?.plan ?? null;
      }
      if (data && typeof data === 'object' && 'plan' in data) {
        return (data as MyPlanResponse).plan ?? null;
      }
      return (data as Plan | null) ?? null;
    },
    enabled,
    staleTime: 60_000,
  });
}

export interface SubscriptionHistoryItem extends MySubscription {
  started_at: string;
  expires_at: string;
}

export interface SubscriptionHistoryResponse {
  items: SubscriptionHistoryItem[];
}

/** Full subscription history: active, expired, cancelled — newest first. */
export function useSubscriptionHistory(enabled = true) {
  return useQuery({
    queryKey: ['me', 'subscriptions'],
    queryFn: async (): Promise<SubscriptionHistoryItem[]> => {
      const data = await apiGet<SubscriptionHistoryResponse>('/me/subscriptions');
      return data?.items ?? [];
    },
    enabled,
    staleTime: 60_000,
  });
}
