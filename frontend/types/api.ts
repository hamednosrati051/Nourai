// TypeScript types for all backend API resources.
// Field names follow the backend's REST contract (spec sections 8-10, 17).

/** Pagination metadata returned inside the success envelope's `meta`. */
export interface PageMeta {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

/** Paginated list payload shape. */
export interface Paginated<T> {
  items: T[];
  meta: PageMeta;
}

// ---------------------------------------------------------------------------
// Auth / users
// ---------------------------------------------------------------------------

export interface User {
  id: string;
  mobile: string;
  /** Masked mobile as shown by the admin API (e.g. 0912****789). */
  mobile_masked?: string;
  is_active: boolean;
  created_at: string;
}

export interface AdminAccount {
  id: string;
  username: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Wallet & payments
// ---------------------------------------------------------------------------

export interface Wallet {
  /** Balance in integer IRR. */
  balance_irr: number;
  updated_at: string;
}

export type WalletTransactionType = 'deposit' | 'reserve' | 'settle' | 'release' | 'refund' | 'adjustment';

export interface WalletTransaction {
  id: string;
  type: WalletTransactionType;
  /** Signed amount in integer IRR (positive = credit). */
  amount_irr: number;
  /** Balance after this transaction, in integer IRR. */
  balance_after_irr: number;
  description: string | null;
  reference_type: string | null;
  reference_id: string | null;
  created_at: string;
}

export type PaymentStatus = 'pending' | 'paid' | 'failed' | 'cancelled' | 'expired';

export interface Payment {
  id: string;
  /** Amount in integer IRR. */
  amount_irr: number;
  gateway: string;
  status: PaymentStatus;
  /** Gateway redirect URL for pending payments. */
  redirect_url?: string | null;
  track_id?: string | null;
  reference_id?: string | null;
  created_at: string;
  paid_at?: string | null;
}

// ---------------------------------------------------------------------------
// Models catalog
// ---------------------------------------------------------------------------

export type ModelService = 'text' | 'audio' | 'image';

/** Model capability, matches backend CAP_* constants. */
export type ModelCapability =
  | 'text'
  | 'speech_to_text'
  | 'text_to_speech'
  | 'image'
  | 'generate_image'
  | 'edit_image';

/** Capabilities that back the image page (generation + editing). */
export const IMAGE_CAPABILITIES: ModelCapability[] = ['generate_image', 'edit_image', 'image'];

/** Admin model payload: GET/PATCH /admin/models. */
export interface AiModel {
  id: string;
  slug: string;
  display_name: string;
  capability: ModelCapability;
  provider_key: string;
  provider_model_name: string;
  is_active: boolean;
  pricing_type: string;
  /** Adapter family (e.g. "openai_compat"); selects the runtime adapter. */
  provider_type: string;
  tokenizer_encoding?: string | null;
  config_json?: Record<string, unknown> | null;
  description?: string | null;
  /** True when provider credentials were stored via the admin form. */
  has_credentials?: boolean;
  /** Provider endpoint URL (not sensitive); api_key is never returned. */
  /** Write-only: sent on create/update, never returned by the API. */
  base_url?: string;
  api_key?: string;
  created_at: string;
  updated_at?: string | null;
}

export interface ModelPricingInfo {
  billing_unit: string;
  unit_size: number;
  unit_price_irr: number;
  dimension_key?: string | null;
  quality_key?: string | null;
  minimum_charge_irr?: number | null;
  maximum_charge_irr?: number | null;
  rounding_mode: string;
}

/** Public catalog model: GET /models (active models + pricing). */
export interface PublicModel {
  id: string;
  slug: string;
  display_name: string;
  capability: ModelCapability;
  pricing_type: string;
  description?: string | null;
  pricing: ModelPricingInfo[];
}

// ---------------------------------------------------------------------------
// Chat (text)
// ---------------------------------------------------------------------------

export interface Conversation {
  id: string;
  title: string | null;
  model_id: string;
  model_name?: string;
  created_at: string;
  updated_at: string;
  /**
   * Messages embedded in GET /api/v1/conversations/{id} (the spec's chat
   * contract). There is no separate GET …/messages endpoint.
   */
  messages?: ChatMessage[];
}

export type ChatRole = 'user' | 'assistant' | 'system';

export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  input_tokens?: number | null;
  output_tokens?: number | null;
  /** Cost in integer IRR. */
  cost_irr?: number | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Audio
// ---------------------------------------------------------------------------

export type AudioJobStatus = 'queued' | 'processing' | 'succeeded' | 'failed' | 'cancelled';

export interface AudioJob {
  id: string;
  status: AudioJobStatus;
  transcript: string | null;
  reply_text: string | null;
  input_asset_id: string | null;
  output_asset_id: string | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  finished_at?: string | null;
}

export interface AssetDownload {
  download_url: string;
  expires_in_seconds: number;
  mime_type: string;
  size_bytes: number;
}

export type TtsJobStatus = 'queued' | 'processing' | 'succeeded' | 'failed' | 'cancelled';

export interface TtsJob {
  id: string;
  status: TtsJobStatus;
  text: string | null;
  output_asset_id: string | null;
  error_code?: string | null;
  error_message?: string | null;
  created_at: string;
  finished_at?: string | null;
}

// ---------------------------------------------------------------------------
// Image
// ---------------------------------------------------------------------------

export type ImageJobType = 'text_to_image' | 'image_to_image';
export type ImageJobStatus = 'queued' | 'processing' | 'succeeded' | 'failed' | 'cancelled';

export interface ImageSizeOption {
  /** e.g. "1024x1024". */
  value: string;
  label: string;
  width: number;
  height: number;
}

export interface ImageConfig {
  sizes: ImageSizeOption[];
  /** Max upload size in bytes for the input image. */
  max_upload_bytes: number;
  /** Max input pixels (width x height). */
  max_input_pixels: number;
  max_input_width: number;
  max_input_height: number;
  /** Allowed MIME types for the input image. */
  allowed_mime_types: string[];
  qualities: string[];
}

export interface ImageJob {
  id: string;
  type: ImageJobType;
  status: ImageJobStatus;
  model_id: string;
  model_name?: string;
  prompt: string;
  size?: string | null;
  quality?: string | null;
  /** Signed, short-lived URL of the generated image. */
  result_url: string | null;
  result_width?: number | null;
  result_height?: number | null;
  /** Final settled cost in integer IRR. */
  cost_irr?: number | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Gallery (public)
// ---------------------------------------------------------------------------

export interface GalleryItem {
  id: string;
  /** Optimized, publicly accessible image URL. */
  image_url: string;
  /** Optimized thumbnail URL (falls back to image_url when absent). */
  thumbnail_url?: string | null;
  width?: number | null;
  height?: number | null;
  /** Safe alt text; never contains private prompts or user identifiers. */
  alt_text?: string | null;
  reviewed_at: string;
}

// ---------------------------------------------------------------------------
// Usage history
// ---------------------------------------------------------------------------

export type UsageStatus = 'succeeded' | 'failed' | 'refunded';

export interface UsageEvent {
  id: string;
  service: ModelService;
  model_id: string;
  model_name?: string;
  status: UsageStatus;
  /** Usage units, e.g. token counts or seconds, with a human label. */
  usage_amount?: number | null;
  usage_unit?: string | null;
  /** Charged amount in integer IRR. */
  cost_irr: number;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export interface AdminStats {
  total_users: number;
  active_users: number;
  total_revenue_irr: number;
  revenue_today_irr: number;
  payments_today: number;
  pending_gallery_items: number;
  jobs_today: number;
  active_models: number;
}

export interface AdminUserRow {
  id: string;
  mobile_masked: string;
  is_active: boolean;
  /** Balance in integer IRR. */
  balance_irr: number;
  total_spent_irr: number;
  created_at: string;
  last_login_at?: string | null;
}

export interface AdminUserDetail extends AdminUserRow {
  mobile: string;
}

export type ActivityKind =
  | 'login'
  | 'ai_request'
  | 'payment'
  | 'wallet'
  | 'gallery'
  | 'admin_action';

export interface ActivityItem {
  id: string;
  kind: ActivityKind;
  title: string;
  description?: string | null;
  created_at: string;
}

export type AssetKind = 'generated_image' | 'chat_input_image' | 'input_audio' | 'output_audio';

export interface AssetItem {
  id: string;
  kind: AssetKind;
  /** Signed, short-lived URL. */
  url: string;
  thumbnail_url?: string | null;
  width?: number | null;
  height?: number | null;
  byte_size?: number | null;
  mime_type?: string | null;
  created_at: string;
}

export interface GalleryQueueItem extends GalleryItem {
  user_id: string;
  user_mobile_masked: string;
  status: 'pending' | 'approved' | 'rejected';
  prompt_excerpt?: string | null;
}

export interface PricingRule {
  id: string;
  model_id: string;
  model_name?: string;
  version: number;
  billing_unit: string;
  unit_size: number;
  /** Integer IRR. */
  unit_price_irr: number;
  dimension_key?: string | null;
  quality_key?: string | null;
  /** Integer IRR. */
  minimum_charge_irr?: number | null;
  /** Integer IRR. */
  maximum_charge_irr?: number | null;
  rounding_mode: 'up' | 'down' | 'nearest';
  effective_from?: string | null;
  effective_to?: string | null;
  is_active: boolean;
  created_at: string;
}

export type ResizeMode = 'fit' | 'fill' | 'stretch';

export interface ImageProfile {
  id: string;
  name: string;
  is_active: boolean;
  is_global: boolean;
  model_id?: string | null;
  max_upload_bytes: number;
  max_input_pixels: number;
  allowed_mime_types: string[];
  target_width: number;
  target_height: number;
  resize_mode: ResizeMode;
  output_format: string;
  output_quality: number;
  allow_upscale: boolean;
  updated_at: string;
}

export interface ImagePreviewResult {
  before_width: number;
  before_height: number;
  before_bytes: number;
  after_width: number;
  after_height: number;
  after_bytes: number;
  /** Preview image as a data URL or short-lived URL. */
  preview_url: string;
}

// ---------------------------------------------------------------------------
// Plans (public pricing)
// ---------------------------------------------------------------------------

export interface Plan {
  id: string;
  name: string;
  tagline?: string | null;
  /** Price in integer IRR (0 for free plans); displayed in toman via formatToman. */
  amount_irr: number;
  /** Billing period label, e.g. «ماهانه». */
  period?: string | null;
  features: string[];
  /** Usage limits shown under the features, e.g. «۲۰ درخواست متنی در ماه». */
  limits: string[];
  is_free: boolean;
  /** Featured plan gets the «پیشنهاد ما» badge and highlighted style. */
  is_featured: boolean;
  is_active: boolean;
  sort_order: number;
}

export interface AuditLogEntry {
  id: string;
  actor_type: 'admin' | 'user' | 'system';
  actor_id?: string | null;
  actor_label?: string | null;
  action: string;
  target_type?: string | null;
  target_id?: string | null;
  target_label?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at: string;
}
