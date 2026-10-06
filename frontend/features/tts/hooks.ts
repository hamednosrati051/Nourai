import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiGet, apiPost, buildQuery } from '@/lib/api';
import { DEFAULT_PAGE_SIZE } from '@/lib/config';
import type { Paginated, TtsJob } from '@/types/api';
import { randomUUID } from '@/lib/uuid';

export const TTS_MAX_CHARS = 2000;

export interface TtsVoiceOption {
  value: string;
  label: string;
}

export interface TtsModel {
  id: string;
  slug: string;
  display_name: string;
  provider_type: string;
  voices: TtsVoiceOption[];
  default_voice?: string | null;
}

export function useTtsModels() {
  return useQuery({
    queryKey: ['tts', 'models'],
    queryFn: () => apiGet<TtsModel[]>('/tts/models'),
    staleTime: 60_000,
  });
}

export function useCreateTtsJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ text, voice }: { text: string; voice?: string }) =>
      apiPost<TtsJob>('/tts/jobs', { text, voice: voice || undefined }, undefined, {
        'Idempotency-Key': randomUUID(),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tts', 'jobs'] });
      queryClient.invalidateQueries({ queryKey: ['wallet'] });
    },
  });
}

export function useTtsJob(id: string | null) {
  return useQuery({
    queryKey: ['tts', 'jobs', id],
    queryFn: () => apiGet<TtsJob>(`/tts/jobs/${id}`),
    enabled: !!id,
    refetchInterval: (query) => {
      const job = query.state.data as TtsJob | undefined;
      if (!job) return 2500;
      return job.status === 'queued' || job.status === 'processing' ? 2500 : false;
    },
  });
}

export function useTtsJobs(page = 1, pageSize = DEFAULT_PAGE_SIZE) {
  return useQuery({
    queryKey: ['tts', 'jobs', page, pageSize],
    queryFn: () =>
      apiGet<Paginated<TtsJob>>(`/tts/jobs${buildQuery({ page, page_size: pageSize })}`),
  });
}
