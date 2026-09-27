'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiDelete, apiGet, apiPost } from '@/lib/api';
import type { ChatMessage, Conversation } from '@/types/api';

export function useConversations() {
  return useQuery({
    queryKey: ['conversations'],
    queryFn: () => apiGet<Conversation[]>('/conversations'),
  });
}

export function useConversation(id: string | null) {
  return useQuery({
    queryKey: ['conversations', id],
    queryFn: () => apiGet<Conversation>(`/conversations/${id}`),
    enabled: !!id,
  });
}

/**
 * Messages for a conversation. The spec defines only GET /conversations/{id}
 * (no separate GET …/messages), so messages are selected from that response.
 */
export function useConversationMessages(conversationId: string | null) {
  const { data, ...rest } = useConversation(conversationId);
  return { ...rest, data: data?.messages ?? [] };
}

export function useCreateConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { model_id: string; title?: string }) =>
      apiPost<Conversation>('/conversations', input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) =>
      apiDelete<{ id: string; deleted: boolean }>(`/conversations/${conversationId}`),
    onSuccess: (_data, conversationId) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      queryClient.removeQueries({ queryKey: ['conversations', conversationId] });
    },
  });
}

export function useSendMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ conversationId, content }: { conversationId: string; content: string }) =>
      apiPost<{ user_message: ChatMessage; assistant_message: ChatMessage }>(
        `/conversations/${conversationId}/messages`,
        { content },
        undefined,
        { 'Idempotency-Key': crypto.randomUUID() },
      ),
    onSuccess: (_data, variables) => {
      // Messages are read from GET /conversations/{id}.
      queryClient.invalidateQueries({ queryKey: ['conversations', variables.conversationId] });
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
      queryClient.invalidateQueries({ queryKey: ['wallet'] });
    },
  });
}
