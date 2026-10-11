'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, buildQuery } from '@/lib/api';
import { DEFAULT_PAGE_SIZE } from '@/lib/config';
import type { Paginated, VideoConfig, VideoJob } from '@/types/api';
import { randomUUID } from '@/lib/uuid';

export function useVideoConfig() {
  return useQuery({
    queryKey: ['video', 'config'],
    queryFn: () => apiGet<VideoConfig>('/video/config'),
    staleTime: 5 * 60_000,
  });
}

export interface CreateVideoJobInput {
  prompt: string;
  seconds: number;
  size: string;
  /** Optional video model id; backend falls back to the active video model. */
  model_id?: string;
}

export function useCreateVideoJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateVideoJobInput) =>
      apiPost<VideoJob>('/video/jobs', input, undefined, { 'Idempotency-Key': randomUUID() }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['video', 'jobs'] });
      queryClient.invalidateQueries({ queryKey: ['wallet'] });
    },
  });
}

/**
 * Single video job with status polling. Video rendering takes minutes, so
 * the poll interval is longer than for images. Polling stops once terminal.
 */
export function useVideoJob(id: string | null) {
  return useQuery({
    queryKey: ['video', 'jobs', id],
    queryFn: () => apiGet<VideoJob>(`/video/jobs/${id}`),
    enabled: !!id,
    refetchInterval: (query) => {
      const job = query.state.data as VideoJob | undefined;
      if (!job) return 5000;
      return job.status === 'queued' || job.status === 'processing' ? 8000 : false;
    },
  });
}

export function useVideoJobs(page = 1, pageSize = DEFAULT_PAGE_SIZE) {
  return useQuery({
    queryKey: ['video', 'jobs', page, pageSize],
    queryFn: () =>
      apiGet<Paginated<VideoJob>>(`/video/jobs${buildQuery({ page, page_size: pageSize })}`),
  });
}
