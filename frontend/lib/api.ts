// Centralized API client for the Flask backend.
//
// Conventions (see spec section 17):
// - Base URL: `${NEXT_PUBLIC_API_URL}/api/v1` (same origin when the env var is empty).
// - Success envelope: { data, meta, request_id } -> this client unwraps `data`.
// - Error envelope: { error: { code, message }, request_id } -> throws ApiError.
// - Auth is cookie-based (HttpOnly cookies set by the backend); the frontend
//   never reads or stores tokens. `credentials: 'include'` is always sent.
// - Mutations (POST/PATCH/PUT/DELETE) attach the CSRF token from the
//   `nourai_admin_csrf` / `nourai_csrf` cookie as the `X-CSRF-Token` header
//   when present (double-submit cookie, see backend app/api/deps.py).

export interface ApiSuccessEnvelope<T> {
  data: T;
  meta?: Record<string, unknown>;
  request_id?: string;
}

export interface ApiErrorEnvelope {
  error: { code: string; message?: string };
  request_id?: string;
}

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId?: string;

  constructor(code: string, message: string, status: number, requestId?: string) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.requestId = requestId;
  }
}

/** Persian, user-safe messages for known backend error codes. */
const ERROR_MESSAGES: Record<string, string> = {
  VALIDATION_ERROR: 'اطلاعات واردشده معتبر نیست. لطفاً بررسی کنید.',
  UNAUTHORIZED: 'نشست شما منقضی شده است. لطفاً دوباره وارد شوید.',
  FORBIDDEN: 'به این بخش دسترسی ندارید.',
  USER_DISABLED: 'حساب کاربری شما غیرفعال شده است.',
  RATE_LIMITED: 'تعداد درخواست‌ها زیاد است؛ لطفاً کمی بعد دوباره تلاش کنید.',
  INSUFFICIENT_BALANCE: 'موجودی کیف پول کافی نیست. لطفاً کیف پول را شارژ کنید.',
  MODEL_UNAVAILABLE: 'این مدل در حال حاضر فعال نیست.',
  FILE_TOO_LARGE: 'حجم فایل بیشتر از حد مجاز است.',
  IMAGE_DIMENSIONS_EXCEEDED: 'ابعاد تصویر بیشتر از حد مجاز است.',
  UNSUPPORTED_IMAGE_TYPE: 'فرمت تصویر پشتیبانی نمی‌شود.',
  IMAGE_PROCESSING_FAILED: 'پردازش تصویر ناموفق بود.',
  PRICING_RULE_UNAVAILABLE: 'تعرفه این سرویس در دسترس نیست.',
  TOKENIZER_UNAVAILABLE: 'سرویس محاسبه هزینه در دسترس نیست.',
  PAYMENT_VERIFICATION_FAILED: 'تأیید پرداخت ناموفق بود.',
  PROVIDER_ERROR: 'سرویس هوش مصنوعی موقتاً در دسترس نیست؛ لطفاً بعداً تلاش کنید.',
};

/** Resolve a backend error code to a safe Persian message for the UI. */
export function getErrorMessage(code: string, fallback?: string): string {
  return ERROR_MESSAGES[code] ?? fallback ?? 'خطایی رخ داد. لطفاً دوباره تلاش کنید.';
}

const API_ORIGIN = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/+$/, '');

/** Build a full URL for a `/api/v1/...` path. */
export function apiUrl(path: string): string {
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${API_ORIGIN}/api/v1${p}`;
}

/** Read a cookie value by name (client-side only). */
function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}

type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

interface ApiFetchOptions {
  method?: HttpMethod;
  /** JSON body for the request. */
  body?: unknown;
  /** multipart/form-data body (CSRF header is still attached). */
  formData?: FormData;
  headers?: Record<string, string>;
  /** Extra fetch init overrides. */
  init?: RequestInit;
  /** Internal: set when this call is already a retry after a token refresh. */
  _retried?: boolean;
}

// --- Silent token refresh ---
// The access cookie (nourai_at) lives ~15 minutes; the refresh cookie
// (nourai_rt) lives 30 days. When an API call gets 401 because the access
// token expired, transparently call /auth/refresh (cookie-based) and retry
// the original request once. Concurrent 401s share a single in-flight
// refresh so we don't stampede the endpoint.
let refreshPromise: Promise<boolean> | null = null;

function tryRefresh(refreshPath: string): Promise<boolean> {
  if (refreshPromise) return refreshPromise;
  const p = (async () => {
    try {
      // /auth/refresh is a POST with a session cookie, so CSRF protection
      // applies: send the double-submit token like apiFetch does.
      const csrf = readCookie('nourai_csrf') ?? readCookie('nourai_admin_csrf');
      const res = await fetch(apiUrl(refreshPath), {
        method: 'POST',
        credentials: 'include',
        headers: csrf ? { 'X-CSRF-Token': csrf } : {},
      });
      return res.ok;
    } catch {
      return false;
    }
  })();
  refreshPromise = p;
  p.finally(() => {
    if (refreshPromise === p) refreshPromise = null;
  });
  return p;
}

/**
 * Which refresh endpoint (if any) applies to a 401 on `path`.
 * Auth-flow paths (login/OTP/refresh itself) never trigger a refresh:
 * a 401 there means "not logged in / wrong code", not "token expired".
 */
function refreshPathFor(path: string): string | null {
  if (path.startsWith('/auth/') || path.startsWith('/admin/auth/')) return null;
  if (path.startsWith('/admin/')) return '/admin/auth/refresh';
  return '/auth/refresh';
}

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { method = 'GET', body, formData, headers = {}, init = {}, _retried = false } = options;

  const finalHeaders: Record<string, string> = { ...headers };
  if (body !== undefined && !formData) {
    finalHeaders['Content-Type'] = 'application/json';
  }
  // CSRF protection for state-changing requests (double-submit cookie).
  // Precedence mirrors the backend (app/api/deps.py::csrf_protect), which
  // checks the user cookie first: readCookie('nourai_csrf') wins over the
  // admin one, so cookie and header always refer to the same token.
  if (method !== 'GET') {
    const csrf = readCookie('nourai_csrf') ?? readCookie('nourai_admin_csrf');
    if (csrf) finalHeaders['X-CSRF-Token'] = csrf;
  }

  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      method,
      credentials: 'include',
      headers: finalHeaders,
      body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
      ...init,
    });
  } catch {
    throw new ApiError('NETWORK_ERROR', 'ارتباط با سرور برقرار نشد. اتصال اینترنت را بررسی کنید.', 0);
  }

  let payload: unknown = null;
  const text = await response.text();
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!response.ok) {
    // Silent refresh: the access token is short-lived. On 401, try to
    // refresh once (via the long-lived refresh cookie) and retry the
    // original request before surfacing the error.
    if (response.status === 401 && !_retried) {
      const refreshPath = refreshPathFor(path);
      if (refreshPath && (await tryRefresh(refreshPath))) {
        return apiFetch<T>(path, { ...options, _retried: true });
      }
    }
    const envelope = payload as ApiErrorEnvelope | null;
    const code = envelope?.error?.code ?? `HTTP_${response.status}`;
    const message =
      envelope?.error?.message || getErrorMessage(code);
    throw new ApiError(code, message, response.status, envelope?.request_id);
  }

  const envelope = payload as ApiSuccessEnvelope<T> | null;
  // Tolerate backends that return the payload unwrapped in dev.
  if (envelope && typeof envelope === 'object' && 'data' in envelope) {
    return envelope.data as T;
  }
  return payload as T;
}

export const apiGet = <T>(path: string, init?: RequestInit) =>
  apiFetch<T>(path, { method: 'GET', init });

export const apiPost = <T>(path: string, body?: unknown, init?: RequestInit, headers?: Record<string, string>) =>
  apiFetch<T>(path, { method: 'POST', body, init, headers });

export const apiPatch = <T>(path: string, body?: unknown, init?: RequestInit) =>
  apiFetch<T>(path, { method: 'PATCH', body, init });

export const apiPut = <T>(path: string, body?: unknown, init?: RequestInit) =>
  apiFetch<T>(path, { method: 'PUT', body, init });

export const apiDelete = <T>(path: string, body?: unknown, init?: RequestInit) =>
  apiFetch<T>(path, { method: 'DELETE', body, init });

export const apiPostForm = <T>(path: string, formData: FormData, init?: RequestInit, headers?: Record<string, string>) =>
  apiFetch<T>(path, { method: 'POST', formData, init, headers });

/** Build a query string from a params object, skipping undefined/null/empty values. */
export function buildQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}