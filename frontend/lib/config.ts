// Single source of truth for brand and app-wide constants.
// Renaming the product only requires editing BRAND here.

export const BRAND = {
  /** Persian display name, used throughout the UI. */
  fa: 'نورا',
  /** Latin display name, used in technical contexts (title, meta). */
  en: 'Nourai',
} as const;

/** OTP code length expected by the backend (configurable in one place). */
export const OTP_LENGTH = 5;

/** Countdown (seconds) before the OTP resend button becomes available. */
export const OTP_RESEND_SECONDS = 120;

/** Maximum number of approved gallery images served by the public API. */
export const GALLERY_MAX_ITEMS = 20;

/** localStorage key for the theme preference (light | dark | system). */
export const THEME_STORAGE_KEY = 'nourai-theme';

/** Cookie names the backend uses for sessions (middleware checks presence only). */
export const USER_SESSION_COOKIE =
  process.env.NEXT_PUBLIC_USER_SESSION_COOKIE || 'nourai_user_session';
export const ADMIN_SESSION_COOKIE =
  process.env.NEXT_PUBLIC_ADMIN_SESSION_COOKIE || 'nourai_admin_session';

/** Default pagination page size used across lists. */
export const DEFAULT_PAGE_SIZE = 20;
