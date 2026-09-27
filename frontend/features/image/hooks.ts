'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, apiPostForm, buildQuery } from '@/lib/api';
import { DEFAULT_PAGE_SIZE } from '@/lib/config';
import type { ImageConfig, ImageEstimate, ImageJob, Paginated } from '@/types/api';

export function useImageConfig() {
  return useQuery({
    queryKey: ['image', 'config'],
    queryFn: () => apiGet<ImageConfig>('/image/config'),
    staleTime: 5 * 60_000,
  });
}

export function useImageEstimate() {
  return useMutation({
    mutationFn: (input: {
      type: 'text_to_image' | 'image_to_image';
      model_id: string;
      prompt: string;
      size?: string;
      quality?: string;
      /** Present for image_to_image estimates. */
      image_width?: number;
      image_height?: number;
    }) => apiPost<ImageEstimate>('/image/estimate', input),
  });
}

export interface CreateImageJobInput {
  type: 'text_to_image' | 'image_to_image';
  model_id: string;
  prompt: string;
  size?: string;
  quality?: string;
  /** Raw input file for image_to_image; backend validates and derives a safe copy. */
  inputFile?: File;
}

export function useCreateImageJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateImageJobInput) => {
      if (input.type === 'image_to_image' && input.inputFile) {
        const form = new FormData();
        form.set('type', input.type);
        form.set('model_id', input.model_id);
        form.set('prompt', input.prompt);
        if (input.size) form.set('size', input.size);
        if (input.quality) form.set('quality', input.quality);
        form.set('image', input.inputFile, input.inputFile.name);
        return apiPostForm<ImageJob>('/image/jobs', form, undefined, { 'Idempotency-Key': crypto.randomUUID() });
      }
      const { inputFile: _ignored, ...json } = input;
      return apiPost<ImageJob>('/image/jobs', json, undefined, { 'Idempotency-Key': crypto.randomUUID() });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['image', 'jobs'] });
      queryClient.invalidateQueries({ queryKey: ['wallet'] });
    },
  });
}

/**
 * Single image job with status polling. Polling only runs while the job is
 * still queued/processing (refetchInterval returns false once terminal).
 */
export function useImageJob(id: string | null) {
  return useQuery({
    queryKey: ['image', 'jobs', id],
    queryFn: () => apiGet<ImageJob>(`/image/jobs/${id}`),
    enabled: !!id,
    refetchInterval: (query) => {
      const job = query.state.data as ImageJob | undefined;
      if (!job) return 2000;
      return job.status === 'queued' || job.status === 'processing' ? 2000 : false;
    },
  });
}

export function useImageJobs(page = 1, pageSize = DEFAULT_PAGE_SIZE) {
  return useQuery({
    queryKey: ['image', 'jobs', page, pageSize],
    queryFn: () =>
      apiGet<Paginated<ImageJob>>(`/image/jobs${buildQuery({ page, page_size: pageSize })}`),
  });
}
