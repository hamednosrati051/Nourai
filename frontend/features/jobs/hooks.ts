'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiPost } from '@/lib/api';

/** Cancel your own queued job (any capability): POST /api/v1/jobs/<id>/cancel. */
export function useCancelJob(invalidateKeys: string[][] = []) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => apiPost<{ id: string; status: string }>(`/jobs/${jobId}/cancel`),
    onSuccess: () => {
      for (const key of invalidateKeys) {
        queryClient.invalidateQueries({ queryKey: key });
      }
      queryClient.invalidateQueries({ queryKey: ['wallet'] });
    },
  });
}
