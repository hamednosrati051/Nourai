'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { apiGet, apiPost } from '@/lib/api';
import type { AdminAccount, User } from '@/types/api';

// ---------------------------------------------------------------------------
// User session
// ---------------------------------------------------------------------------

/** Current user profile; 401 means "not logged in" (handled by UserGuard). */
export function useMe() {
  return useQuery({
    queryKey: ['me'],
    queryFn: () => apiGet<User>('/me'),
    retry: false,
  });
}

export function useOtpRequest() {
  return useMutation({
    mutationFn: (mobile: string) =>
      apiPost<{ sent: boolean }>('/auth/otp/request', { mobile }),
  });
}

export function useOtpVerify() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ mobile, code }: { mobile: string; code: string }) =>
      apiPost<User>('/auth/otp/verify', { mobile, code }),
    onSuccess: (user) => {
      queryClient.setQueryData(['me'], user);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  const router = useRouter();
  return useMutation({
    mutationFn: () => apiPost<void>('/auth/logout'),
    onSettled: () => {
      queryClient.clear();
      router.replace('/auth/login');
    },
  });
}

// ---------------------------------------------------------------------------
// Admin session (separate cookies from the user session)
// ---------------------------------------------------------------------------

export function useAdminMe() {
  return useQuery({
    queryKey: ['admin', 'me'],
    queryFn: () => apiGet<AdminAccount>('/noura-de03b5bbc11b/me'),
    retry: false,
  });
}

export function useAdminLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      apiPost<AdminAccount>('/noura-de03b5bbc11b/auth/login', { username, password }),
    onSuccess: (admin) => {
      queryClient.setQueryData(['admin', 'me'], admin);
    },
  });
}

export function useAdminLogout() {
  const queryClient = useQueryClient();
  const router = useRouter();
  return useMutation({
    mutationFn: () => apiPost<void>('/noura-de03b5bbc11b/auth/logout'),
    onSettled: () => {
      queryClient.clear();
      router.replace('/noura-de03b5bbc11b/login');
    },
  });
}
