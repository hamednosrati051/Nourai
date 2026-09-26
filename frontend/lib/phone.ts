import { z } from 'zod';

// Iranian mobile number helpers. The backend normalizes before storing;
// the frontend validates and normalizes to the canonical `09xxxxxxxxx` form.

const FA_DIGITS: Record<string, string> = {
  '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
  '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
  '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
  '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
};

/** Replace Persian/Arabic digits with Latin digits and trim whitespace. */
export function toLatinDigits(input: string): string {
  return input
    .trim()
    .replace(/[۰-۹٠-٩]/g, (d) => FA_DIGITS[d] ?? d);
}

/**
 * Normalize a mobile number to `09xxxxxxxxx`.
 * Accepts 09..., +98..., 0098..., 98... forms.
 */
export function normalizeMobile(input: string): string {
  let digits = toLatinDigits(input).replace(/[\s-]/g, '');
  if (digits.startsWith('+98')) digits = `0${digits.slice(3)}`;
  else if (digits.startsWith('0098')) digits = `0${digits.slice(4)}`;
  else if (digits.startsWith('98')) digits = `0${digits.slice(2)}`;
  return digits;
}

/** Canonical Iranian mobile regex: starts with 09, 11 digits total. */
export const MOBILE_REGEX = /^09\d{9}$/;

export const mobileSchema = z
  .string()
  .min(1, 'شماره موبایل را وارد کنید.')
  .transform((v) => normalizeMobile(v))
  .refine((v) => MOBILE_REGEX.test(v), {
    message: 'شماره موبایل معتبر نیست. مثال: 09123456789',
  });

/** Mask a mobile number for display, e.g. 0912****789. */
export function maskMobile(mobile: string): string {
  const digits = toLatinDigits(mobile);
  if (digits.length < 7) return '***';
  return `${digits.slice(0, 4)}****${digits.slice(-3)}`;
}
