'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPostForm, buildQuery } from '@/lib/api';
import { DEFAULT_PAGE_SIZE } from '@/lib/config';
import type { AudioJob, Paginated } from '@/types/api';

export function useCreateAudioJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, modelId }: { file: File; modelId?: string }) => {
      const form = new FormData();
      form.set('audio', file, file.name);
      if (modelId) form.set('model_id', modelId);
      return apiPostForm<AudioJob>('/audio/jobs', form, undefined, { 'Idempotency-Key': crypto.randomUUID() });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['audio', 'jobs'] });
      queryClient.invalidateQueries({ queryKey: ['wallet'] });
    },
  });
}

/** Single audio job with status polling until it reaches a terminal state. */
export function useAudioJob(id: string | null) {
  return useQuery({
    queryKey: ['audio', 'jobs', id],
    queryFn: () => apiGet<AudioJob>(`/audio/jobs/${id}`),
    enabled: !!id,
    refetchInterval: (query) => {
      const job = query.state.data as AudioJob | undefined;
      if (!job) return 2500;
      return job.status === 'queued' || job.status === 'processing' ? 2500 : false;
    },
  });
}

export function useAudioJobs(page = 1, pageSize = DEFAULT_PAGE_SIZE) {
  return useQuery({
    queryKey: ['audio', 'jobs', page, pageSize],
    queryFn: () =>
      apiGet<Paginated<AudioJob>>(`/audio/jobs${buildQuery({ page, page_size: pageSize })}`),
  });
}