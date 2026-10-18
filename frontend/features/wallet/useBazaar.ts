'use client';

import { useCallback, useEffect, useState } from 'react';
import { apiPost } from '@/lib/api';
import { useToast } from '@/components/Toast';

declare global {
  interface Window {
    BazaarBridge?: {
      isNativeApp(): boolean;
      getVersion(): string;
      purchase(sku: string): void;
      consume(purchaseToken: string): void;
    };
    onBazaarPurchaseResult?: (purchaseData: string, signature: string) => void;
    onBazaarPurchaseError?: (code: string) => void;
  }
}

/** Detect if running inside the native Android app. */
export function isBazaarApp(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return !!window.BazaarBridge && window.BazaarBridge.isNativeApp();
  } catch {
    return false;
  }
}

const ERROR_MESSAGES: Record<string, string> = {
  USER_CANCELLED: 'خرید لغو شد.',
  ALREADY_OWNED: 'این محصول قبلاً خریداری شده است.',
  BIND_FAILED: 'اتصال به بازار برقرار نشد. اپ بازار نصب است؟',
  NO_BUY_INTENT: 'امکان شروع خرید نیست.',
  LAUNCH_FAILED: 'باز کردن صفحه پرداخت ناموفق بود.',
  REMOTE_ERROR: 'خطا در ارتباط با بازار.',
  NO_DATA: 'اطلاعات خرید دریافت نشد.',
  MISSING_DATA: 'اطلاعات خرید ناقص است.',
  EMPTY_SKU: 'شناسه کالا نامعتبر است.',
};

export const BAZAAR_CHARGE_SKUS = [
  { sku: 'charge_50k', label: '۵۰٬۰۰۰ تومان' },
  { sku: 'charge_100k', label: '۱۰۰٬۰۰۰ تومان' },
  { sku: 'charge_200k', label: '۲۰۰٬۰۰۰ تومان' },
  { sku: 'charge_300k', label: '۳۰۰٬۰۰۰ تومان' },
] as const;

export const BAZAAR_PLAN_SKUS: Record<string, string> = {
  '990000': 'plan_light',
  '1990000': 'plan_basic',
  '3990000': 'plan_economy',
  '5990000': 'plan_image',
};

/**
 * Bazaar in-app billing hook. Only active inside the native app.
 */
export function useBazaarPayment(onSuccess?: () => void) {
  const { toast } = useToast();
  const [inApp, setInApp] = useState(false);
  const [buying, setBuying] = useState<string | null>(null);

  useEffect(() => {
    setInApp(isBazaarApp());
  }, []);

  const verifyPurchase = useCallback(async (purchaseData: string, signature: string) => {
    try {
      const res = await apiPost<{ type: string }>(
        '/bazaar/verify',
        { purchase_data: purchaseData, signature },
      );
      try {
        const data = JSON.parse(purchaseData);
        if (data.productId?.startsWith('charge_') && data.purchaseToken) {
          window.BazaarBridge?.consume(data.purchaseToken);
        }
      } catch {
        // non-fatal
      }
      toast(res.type === 'subscription' ? 'اشتراک فعال شد.' : 'کیف پول شارژ شد.', 'success');
      onSuccess?.();
    } catch {
      toast('تأیید خرید ناموفق بود.', 'error');
    } finally {
      setBuying(null);
    }
  }, [toast, onSuccess]);

  useEffect(() => {
    if (!inApp) return;
    window.onBazaarPurchaseResult = (purchaseData, signature) => {
      verifyPurchase(purchaseData, signature);
    };
    window.onBazaarPurchaseError = (code) => {
      setBuying(null);
      toast(ERROR_MESSAGES[code] ?? 'خطا در خرید.', 'error');
    };
    return () => {
      window.onBazaarPurchaseResult = undefined;
      window.onBazaarPurchaseError = undefined;
    };
  }, [inApp, verifyPurchase, toast]);

  const purchase = useCallback((sku: string) => {
    if (!window.BazaarBridge) {
      toast('پرداخت بازار فقط در اپ اندروید فعال است.', 'error');
      return;
    }
    setBuying(sku);
    try {
      window.BazaarBridge.purchase(sku);
    } catch {
      setBuying(null);
      toast('خطا در شروع خرید.', 'error');
    }
  }, [toast]);

  return { inApp, buying, purchase };
}
