import Link from 'next/link';

interface CapabilityCardProps {
  icon: string;
  title: string;
  description: string;
  href: string;
  ctaLabel: string;
}

/** Homepage card introducing one of the three AI capabilities. */
export function CapabilityCard({ icon, title, description, href, ctaLabel }: CapabilityCardProps) {
  return (
    <article className="card flex flex-col gap-3 transition-transform hover:-translate-y-0.5">
      <span aria-hidden="true" className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-100 text-2xl dark:bg-brand-900/40">
        {icon}
      </span>
      <h3 className="text-lg font-bold">{title}</h3>
      <p className="flex-1 text-sm leading-7 text-neutral-600 dark:text-slate-400">{description}</p>
      <Link href={href} className="inline-link font-semibold text-brand-700 hover:underline dark:text-brand-400">
        {ctaLabel} ←
      </Link>
    </article>
  );
}
