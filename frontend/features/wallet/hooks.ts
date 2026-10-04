'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, buildQuery } from '@/lib/api';
import { tomanToIrr } from '@/lib/currency';
import { DEFAULT_PAGE_SIZE } from '@/lib/config';
import type { Paginated, Payment, Wallet, WalletTransaction } from '@/types/api';

export function useWallet() {
  return useQuery({
    queryKey: ['wallet'],
    queryFn: () => apiGet<Wallet>('/wallet'),
  });
}

export function useWalletTransactions(page = 1, pageSize = DEFAULT_PAGE_SIZE) {
  return useQuery({
    queryKey: ['wallet', 'transactions', page, pageSize],
    queryFn: () =>
      apiGet<Paginated<WalletTransaction>>(`/wallet/transactions${buildQuery({ page, page_size: pageSize })}`),
  });
}

export interface CreatePaymentInput {
  /** Amount in toman (UI unit); converted to IRR before sending. */
  amountToman?: number;
}

export function useCreatePayment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreatePaymentInput) => {
      // Plain wallet top-up: the gateway contract lives in the backend adapter; we send IRR.
      return apiPost<Payment>('/payments', { amount_irr: tomanToIrr(input.amountToman ?? 0) });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['wallet'] });
      queryClient.invalidateQueries({ queryKey: ['payments'] });
    },
  });
}

export function usePayments(page = 1, pageSize = DEFAULT_PAGE_SIZE) {
  return useQuery({
    queryKey: ['payments', page, pageSize],
    queryFn: () =>
      apiGet<Paginated<Payment>>(`/payments${buildQuery({ page, page_size: pageSize })}`),
  });
}

export function usePayment(id: string | null) {
  return useQuery({
    queryKey: ['payments', id],
    queryFn: () => apiGet<Payment>(`/payments/${id}`),
    enabled: !!id,
  });
}
