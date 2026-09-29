// Date/time formatting helpers. The backend stores timestamps in UTC;
// the UI renders them in the user's locale (Persian calendar).

const dateTimeFormatter = new Intl.DateTimeFormat('fa-IR', {
  dateStyle: 'medium',
  timeStyle: 'short',
});

const dateFormatter = new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium' });

const timeFormatter = new Intl.DateTimeFormat('fa-IR', {
  hour: '2-digit',
  minute: '2-digit',
});

/**
 * Parse a backend ISO timestamp. The backend stores timestamps in UTC but
 * serializes naive datetimes (no offset suffix); a bare ISO string is parsed
 * by `new Date()` as *local* time, shifting every displayed time by the UTC
 * offset. Interpret offset-less strings as UTC by appending "Z".
 */
function parseBackendDateTime(iso: string): Date {
  const hasOffset = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso.trim());
  return new Date(hasOffset ? iso : `${iso.trim()}Z`);
}

/** Format an ISO timestamp as a Persian date+time string. */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = parseBackendDateTime(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return dateTimeFormatter.format(d);
}

/** Format an ISO timestamp as a Persian date string. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = parseBackendDateTime(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return dateFormatter.format(d);
}

/** Format an ISO timestamp as a Persian time string. */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = parseBackendDateTime(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return timeFormatter.format(d);
}

/** Format a byte count as a human-readable Persian string. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return '—';
  if (bytes < 1024) return `${new Intl.NumberFormat('fa-IR').format(bytes)} بایت`;
  const units = ['کیلوبایت', 'مگابایت', 'گیگابایت'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const formatted = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 1 }).format(value);
  return `${formatted} ${units[unit]}`;
}

/** Format a duration in seconds as «m:ss». */
export function formatDuration(totalSeconds: number | null | undefined): string {
  if (totalSeconds === null || totalSeconds === undefined || Number.isNaN(totalSeconds)) return '—';
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);
  return `${new Intl.NumberFormat('fa-IR').format(minutes)}:${String(seconds).padStart(2, '0')}`;
}

/** Format a plain number with Persian digits. */
export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  return new Intl.NumberFormat('fa-IR').format(value);
}
