'use client';

import { useCancelJob } from './hooks';

/** "لغو" button for a queued job; the wallet hold is released on cancel. */
export function CancelJobButton({
  jobId,
  invalidateKeys,
}: {
  jobId: string;
  invalidateKeys: string[][];
}) {
  const cancel = useCancelJob(invalidateKeys);
  return (
    <button
      type="button"
      className="btn-secondary btn-sm"
      disabled={cancel.isPending}
      onClick={() => {
        if (window.confirm('این درخواست لغو شود؟ مبلغ رزروشده به کیف پول برمی‌گردد.')) {
          cancel.mutate(jobId);
        }
      }}
    >
      {cancel.isPending ? 'در حال لغو…' : 'لغو درخواست'}
    </button>
  );
}
