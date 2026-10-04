'use client';

import { useEffect, useRef } from 'react';
import { useMySubscription } from '@/features/plans/hooks';
import { useToast } from './Toast';

const KIND_LABELS: Record<string, string> = {
  text: 'متن',
  image: 'تصویر',
  audio: 'صوت',
};

/**
 * Soft-quota notice: when the active plan's quota is exhausted in some
 * section, tell the user once per session that usage continues from the
 * wallet. Quotas never block.
 */
export function QuotaNotice() {
  const { toast } = useToast();
  const sub = useMySubscription();
  const shownRef = useRef(false);

  useEffect(() => {
    const over = sub.data?.over_quota ?? [];
    if (shownRef.current || over.length === 0) return;
    shownRef.current = true;
    const labels = over.map((k) => KIND_LABELS[k] ?? k).join('، ');
    toast(
      `سقف اشتراک شما در بخش ${labels} به پایان رسید؛ ادامه استفاده از کیف پول محاسبه می‌شود.`,
      'info',
    );
  }, [sub.data, toast]);

  return null;
}
