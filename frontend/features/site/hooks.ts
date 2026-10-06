'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPut } from '@/lib/api';

export interface ContactInfo {
  contact_phone: string | null;
  contact_email: string | null;
  contact_address: string | null;
  contact_telegram: string | null;
  contact_instagram: string | null;
  contact_eitaa: string | null;
  contact_bale: string | null;
  contact_description: string | null;
}

/** Public contact info for the contact page. */
export function useContactInfo() {
  return useQuery({
    queryKey: ['site', 'contact'],
    queryFn: () => apiGet<ContactInfo>('/site/contact'),
    staleTime: 5 * 60_000,
  });
}

/** Admin: current site settings. */
export function useSiteSettings() {
  return useQuery({
    queryKey: ['admin', 'site-settings'],
    queryFn: () => apiGet<ContactInfo>('/admin/settings/site'),
    staleTime: 60_000,
  });
}

/** Admin: update site settings. */
export function useUpdateSiteSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<ContactInfo>) => apiPut<ContactInfo>('/admin/settings/site', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'site-settings'] });
      queryClient.invalidateQueries({ queryKey: ['site', 'contact'] });
    },
  });
}
