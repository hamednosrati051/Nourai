'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPostForm, apiUrl, buildQuery } from '@/lib/api';
import { DEFAULT_PAGE_SIZE } from '@/lib/config';
import type { AssetDownload, AudioJob, Paginated } from '@/types/api';
import { randomUUID } from '@/lib/uuid';

export function useCreateAudioJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, mode }: { file: File; mode?: 'assistant' | 'transcribe' }) => {
      const form = new FormData();
      // Backend reads request.files["file"]; models resolve to defaults.
      form.set('file', file, file.name);
      form.set('mode', mode ?? 'assistant');
      return apiPostForm<AudioJob>('/audio/jobs', form, undefined, { 'Idempotency-Key': randomUUID() });
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

/** Signed download URL for an asset (e.g. the synthesized reply audio). */
export function useAssetDownloadUrl(assetId: string | null) {
  return useQuery({
    queryKey: ['assets', assetId, 'download'],
    queryFn: () => apiGet<AssetDownload>(`/assets/${assetId}/download`),
    enabled: !!assetId,
    staleTime: 1000 * 60 * 5,
  });
}

/** Direct stream URL for <audio>/<img> tags (same-origin, cookie auth). */
export function assetStreamUrl(assetId: string): string {
  return apiUrl(`/assets/${assetId}/download?stream=1`);
}
