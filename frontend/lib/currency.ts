// Money utilities.
//
// The backend stores all amounts as integer IRR (canonical unit).
// The UI displays toman. ALL conversions go through these helpers;
// never divide/multiply by 10 inline elsewhere.

/** 1 toman = 10 IRR. */
const IRR_PER_TOMAN = 10;

/** Convert an integer IRR amount to a (possibly fractional) toman amount. */
export function irrToToman(irr: number): number {
  return irr / IRR_PER_TOMAN;
}

/** Convert a toman amount to integer IRR, rounding to the nearest rial. */
export function tomanToIrr(toman: number): number {
  return Math.round(toman * IRR_PER_TOMAN);
}

const tomanFormatter = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 0 });
const irrFormatter = new Intl.NumberFormat('fa-IR', { maximumFractionDigits: 0 });

/** Format an IRR amount as a Persian toman string, e.g. «۱۲٬۵۰۰ تومان». */
export function formatToman(irr: number): string {
  return `${tomanFormatter.format(irrToToman(irr))} تومان`;
}

/** Format an IRR amount as a Persian rial string, e.g. «۱۲۵٬۰۰۰ ریال». */
export function formatIrr(irr: number): string {
  return `${irrFormatter.format(irr)} ریال`;
}
