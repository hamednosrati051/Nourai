'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiDelete, apiGet, apiPatch, apiPost, apiPut, buildQuery } from '@/lib/api';
import { DEFAULT_PAGE_SIZE } from '@/lib/config';
import type {
  ActivityItem,
  AdminStats,
  AdminUserDetail,
  AdminUserRow,
  AiModel,
  AssetItem,
  AuditLogEntry,
  GalleryQueueItem,
  ImagePreviewResult,
  ImageProfile,
  Paginated,
  Payment,
  Plan,
  PricingRule,
  UsageEvent,
  WalletTransaction,
} from '@/types/api';

// ---------------------------------------------------------------------------
// Dashboard stats
// ---------------------------------------------------------------------------

export function useAdminDashboard() {
  return useQuery({
    queryKey: ['admin', 'dashboard'],
    queryFn: () => apiGet<AdminStats>('/admin/dashboard'),
  });
}

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------

export interface AdminUserFilters {
  page?: number;
  pageSize?: number;
  search?: string;
  isActive?: boolean | '';
}

export function useAdminUsers(filters: AdminUserFilters = {}) {
  const { page = 1, pageSize = DEFAULT_PAGE_SIZE, search, isActive } = filters;
  return useQuery({
    queryKey: ['admin', 'users', page, pageSize, search, isActive],
    queryFn: () =>
      apiGet<Paginated<AdminUserRow>>(
        `/admin/users${buildQuery({
          page,
          page_size: pageSize,
          search: search || undefined,
          is_active: isActive === '' ? undefined : isActive,
        })}`,
      ),
  });
}

export function useAdminUser(id: string | null) {
  return useQuery({
    queryKey: ['admin', 'users', id],
    queryFn: () => apiGet<AdminUserDetail>(`/admin/users/${id}`),
    enabled: !!id,
  });
}

export function useUserActivity(id: string | null, page = 1) {
  return useQuery({
    queryKey: ['admin', 'users', id, 'activity', page],
    queryFn: () =>
      apiGet<Paginated<ActivityItem>>(
        `/admin/users/${id}/activity${buildQuery({ page, page_size: DEFAULT_PAGE_SIZE })}`,
      ),
    enabled: !!id,
  });
}

const USER_ASSET_KIND_MAP = {
  generated: 'generated_image',
  chat_input: 'chat_input_image',
  edit_input: 'input_image_original,input_image_processed',
} as const;

export function useUserAssets(id: string | null, kind?: 'generated' | 'chat_input' | 'edit_input', enabled = true) {
  return useQuery({
    queryKey: ['admin', 'users', id, 'assets', kind],
    queryFn: () =>
      apiGet<AssetItem[]>(
        `/admin/users/${id}/assets${buildQuery({ kind: kind ? USER_ASSET_KIND_MAP[kind] : undefined })}`,
      ),
    enabled: !!id && enabled,
  });
}

export function useUserWalletTransactions(id: string | null, page = 1) {
  return useQuery({
    queryKey: ['admin', 'users', id, 'wallet-transactions', page],
    queryFn: () =>
      apiGet<Paginated<WalletTransaction>>(
        `/admin/users/${id}/wallet-transactions${buildQuery({ page, page_size: DEFAULT_PAGE_SIZE })}`,
      ),
    enabled: !!id,
  });
}

export function useUpdateUserStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, isActive, reason }: { id: string; isActive: boolean; reason: string }) =>
      apiPatch<AdminUserDetail>(`/admin/users/${id}/status`, { is_active: isActive, reason }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'users', variables.id] });
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
  });
}

export function useWalletAdjustment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      amountIrr,
      reason,
    }: {
      id: string;
      /** Signed integer IRR: positive = credit, negative = debit. */
      amountIrr: number;
      reason: string;
    }) => apiPost<WalletTransaction>(`/admin/users/${id}/wallet-adjustments`, { amount_irr: amountIrr, reason }),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'users', variables.id] });
      queryClient.invalidateQueries({ queryKey: ['admin', 'users', variables.id, 'wallet-transactions'] });
    },
  });
}

// ---------------------------------------------------------------------------
// Payments / usage (admin)
// ---------------------------------------------------------------------------

export function useAdminPayments(page = 1, status?: string) {
  return useQuery({
    queryKey: ['admin', 'payments', page, status],
    queryFn: () =>
      apiGet<Paginated<Payment>>(
        `/admin/payments${buildQuery({ page, page_size: DEFAULT_PAGE_SIZE, status: status || undefined })}`,
      ),
  });
}

export function useAdminUsage(page = 1, filters?: { service?: string; userId?: string }) {
  return useQuery({
    queryKey: ['admin', 'usage', page, filters],
    queryFn: () =>
      apiGet<Paginated<UsageEvent>>(
        `/admin/usage${buildQuery({ page, page_size: DEFAULT_PAGE_SIZE, ...filters })}`,
      ),
  });
}

// ---------------------------------------------------------------------------
// Gallery moderation queue
// ---------------------------------------------------------------------------

export function useAdminGallery(status: 'pending' | 'approved' | 'rejected' = 'pending') {
  return useQuery({
    queryKey: ['admin', 'gallery', status],
    queryFn: () => apiGet<GalleryQueueItem[]>(`/admin/gallery${buildQuery({ status })}`),
  });
}

export function useApproveGalleryItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (assetId: string) => apiPost<GalleryQueueItem>(`/admin/gallery/${assetId}/approve`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'gallery'] }),
  });
}

export function useRejectGalleryItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ assetId, reason }: { assetId: string; reason?: string }) =>
      apiPost<GalleryQueueItem>(`/admin/gallery/${assetId}/reject`, { reason }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'gallery'] }),
  });
}

export function useRemoveGalleryItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (assetId: string) => apiDelete<void>(`/admin/gallery/${assetId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'gallery'] }),
  });
}

// ---------------------------------------------------------------------------
// Models
// ---------------------------------------------------------------------------

export function useAdminModels() {
  return useQuery({
    queryKey: ['admin', 'models'],
    queryFn: () => apiGet<AiModel[]>('/admin/models'),
  });
}

export function useCreateAdminModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<AiModel>) => apiPost<AiModel>('/admin/models', input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'models'] }),
  });
}

export function useUpdateAdminModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<AiModel> }) =>
      apiPatch<AiModel>(`/admin/models/${id}`, patch),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'models'] }),
  });
}

// ---------------------------------------------------------------------------
// Pricing rules (versioned)
// ---------------------------------------------------------------------------

export function usePricingRules() {
  return useQuery({
    queryKey: ['admin', 'pricing-rules'],
    queryFn: () => apiGet<PricingRule[]>('/admin/pricing-rules'),
  });
}

export function useCreatePricingRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<PricingRule>) => apiPost<PricingRule>('/admin/pricing-rules', input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'pricing-rules'] }),
  });
}

export function useUpdatePricingRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<PricingRule> }) =>
      apiPatch<PricingRule>(`/admin/pricing-rules/${id}`, patch),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'pricing-rules'] }),
  });
}

export function useDeletePricingRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete<unknown>(`/admin/pricing-rules/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'pricing-rules'] }),
  });
}

export function useDeleteModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete<unknown>(`/admin/models/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'models'] }),
  });
}

export interface PricingEstimateLine {
  billing_unit: string;
  amount_irr: number;
  quantity: string;
  units_charged: number;
  unit_price_usd: string;
  rule_version: number;
}

export function usePricingEstimate() {
  return useMutation({
    mutationFn: (input: Record<string, unknown>) =>
      apiPost<{ total_irr: number; lines: PricingEstimateLine[] }>(
        '/admin/pricing/estimate',
        input,
      ),
  });
}

// ---------------------------------------------------------------------------
// Currency settings (USD rate + image cost-protection margin)
// ---------------------------------------------------------------------------

export interface CurrencySettings {
  usd_to_irr: number;
  image_cost_margin_pct: number;
}

export function useCurrencySettings() {
  return useQuery({
    queryKey: ['admin', 'currency-settings'],
    queryFn: () => apiGet<CurrencySettings>('/admin/settings/currency'),
  });
}

export function useUpdateCurrencySettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { usd_to_irr: number; image_cost_margin_pct: number }) =>
      apiPut<CurrencySettings>('/admin/settings/currency', input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'currency-settings'] }),
  });
}

// ---------------------------------------------------------------------------
// Image processing profiles
// ---------------------------------------------------------------------------

export function useImageProfiles() {
  return useQuery({
    queryKey: ['admin', 'image-profiles'],
    queryFn: () => apiGet<ImageProfile[]>('/admin/settings/image-processing'),
  });
}

export function useUpdateImageProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<ImageProfile> }) =>
      apiPut<ImageProfile>(`/admin/settings/image-processing/${id}`, patch),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'image-profiles'] }),
  });
}

export function useImageProfilePreview() {
  return useMutation({
    mutationFn: async ({ profileId, file }: { profileId: string; file: File }) => {
      const { apiPostForm } = await import('@/lib/api');
      const form = new FormData();
      form.set('image', file, file.name);
      form.set('profile_id', profileId);
      // Spec endpoint: POST /api/v1/admin/settings/image-processing/preview
      return apiPostForm<ImagePreviewResult>('/admin/settings/image-processing/preview', form);
    },
  });
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------

export function useAuditLog(page = 1, search?: string) {
  return useQuery({
    queryKey: ['admin', 'audit', page, search || ''],
    queryFn: () =>
      apiGet<Paginated<AuditLogEntry>>(
        `/admin/audit-logs${buildQuery({ page, page_size: DEFAULT_PAGE_SIZE, search: search || undefined })}`,
      ),
  });
}

// ---------------------------------------------------------------------------
// Plans
// ---------------------------------------------------------------------------

export function useAdminPlans() {
  return useQuery({
    queryKey: ['admin', 'plans'],
    queryFn: () => apiGet<Plan[]>('/admin/plans'),
    staleTime: 30_000,
  });
}

export interface PlanInput {
  name: string;
  description?: string;
  /** Canonical unit: integer IRR (UI enters toman and converts). */
  price_irr: number;
  period_days?: number;
  features: string[];
  /** Real quotas: { monthly_text, monthly_image, monthly_audio_minutes }. */
  usage_limits?: Record<string, number>;
  is_free: boolean;
  is_featured: boolean;
  is_active: boolean;
  sort_order: number;
}

export function useCreateAdminPlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PlanInput) => apiPost<Plan>('/admin/plans', input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'plans'] }),
  });
}

export function useUpdateAdminPlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, input }: { id: string; input: Partial<PlanInput> }) =>
      apiPatch<Plan>('/admin/plans/{id}'.replace('{id}', id), input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'plans'] }),
  });
}

export function useDeleteAdminPlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete<unknown>('/admin/plans/{id}'.replace('{id}', id)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'plans'] }),
  });
}

export interface AdminJob {
  id: string;
  capability: string;
  status: string;
  user_id: string;
  user_mobile_masked: string | null;
  created_at: string | null;
  started_at: string | null;
  prompt_text: string | null;
}

export function useAdminJobs(status: 'queued' | 'processing') {
  return useQuery({
    queryKey: ['admin', 'jobs', status],
    queryFn: () =>
      apiGet<Paginated<AdminJob>>(`/admin/jobs${buildQuery({ status })}`),
  });
}

export function useAdminCancelJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => apiPost<{ id: string; status: string }>(`/admin/jobs/${jobId}/cancel`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'jobs'] });
      queryClient.invalidateQueries({ queryKey: ['wallet'] });
    },
  });
}

// ---------------------------------------------------------------------------
// Prompt filter: global toggle + blocklist words.
// ---------------------------------------------------------------------------
export interface PromptBlocklistWord {
  id: string;
  phrase: string;
  category?: string | null;
  is_active: boolean;
  note?: string | null;
  created_at: string;
  updated_at: string;
}

export function usePromptFilter() {
  return useQuery({
    queryKey: ['admin', 'prompt-filter'],
    queryFn: () => apiGet<{ enabled: boolean }>('/admin/prompt-filter'),
  });
}

export function useSetPromptFilter() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (enabled: boolean) =>
      apiPut<{ enabled: boolean }>('/admin/prompt-filter', { enabled }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'prompt-filter'] }),
  });
}

export function useBlocklistWords() {
  return useQuery({
    queryKey: ['admin', 'prompt-filter', 'words'],
    queryFn: () => apiGet<PromptBlocklistWord[]>('/admin/prompt-filter/words'),
  });
}

export function useCreateBlocklistWord() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { phrase: string; category?: string; is_active?: boolean }) =>
      apiPost<PromptBlocklistWord>('/admin/prompt-filter/words', input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'prompt-filter', 'words'] }),
  });
}

export function useUpdateBlocklistWord() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<Pick<PromptBlocklistWord, 'phrase' | 'category' | 'is_active' | 'note'>> }) =>
      apiPatch<PromptBlocklistWord>(`/admin/prompt-filter/words/${id}`, patch),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'prompt-filter', 'words'] }),
  });
}

export function useDeleteBlocklistWord() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete<void>(`/admin/prompt-filter/words/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'prompt-filter', 'words'] }),
  });
}

export interface AdminBlogPost {
  id: string;
  slug: string;
  title: string;
  description: string;
  content: string[];
  is_published: boolean;
  created_at: string;
  updated_at: string;
}

export function useAdminBlogPosts() {
  return useQuery({
    queryKey: ['admin', 'blog'],
    queryFn: () => apiGet<AdminBlogPost[]>('/admin/blog'),
  });
}

export function useCreateBlogPost() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { slug: string; title: string; description?: string; content?: string[]; is_published?: boolean }) =>
      apiPost<AdminBlogPost>('/admin/blog', input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'blog'] }),
  });
}

export function useUpdateBlogPost() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Partial<Omit<AdminBlogPost, 'id' | 'created_at' | 'updated_at'>> }) =>
      apiPatch<AdminBlogPost>(`/admin/blog/${id}`, patch),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'blog'] }),
  });
}

export function useDeleteBlogPost() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete<void>(`/admin/blog/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'blog'] }),
  });
}
