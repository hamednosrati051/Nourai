import Link from 'next/link';

interface ServiceCardProps {
  icon: string;
  title: string;
  description: string;
  href: string;
  /** Hex color used for the icon glow and the bottom accent line. */
  color: string;
  ctaLabel?: string;
}

/**
 * App-style service card: color-coded glowing icon, bold title, gray
 * description, and a thin accent line at the bottom in the icon's color.
 */
export function ServiceCard({ icon, title, description, href, color, ctaLabel = 'شروع' }: ServiceCardProps) {
  return (
    <Link
      href={href}
      className="service-card group"
      style={{ ['--svc' as string]: color }}
      aria-label={`${title} — ${ctaLabel}`}
    >
      <span aria-hidden="true" className="service-icon">
        {icon}
      </span>
      <h3 className="text-lg font-extrabold text-neutral-900 dark:text-white">{title}</h3>
      <p className="flex-1 text-sm leading-7 text-neutral-600 dark:text-slate-400">{description}</p>
      <span
        aria-hidden="true"
        className="inline-flex items-center gap-1 text-sm font-bold transition-transform group-hover:-translate-x-1"
        style={{ color }}
      >
        {ctaLabel} ←
      </span>
      <span aria-hidden="true" className="service-accent" />
    </Link>
  );
}
