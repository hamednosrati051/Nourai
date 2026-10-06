import type { Metadata } from 'next';
import localFont from 'next/font/local';
import { BRAND, THEME_STORAGE_KEY } from '@/lib/config';
import { ThemeProvider } from '@/components/ThemeProvider';
import { QueryProvider } from '@/features/providers';
import { ToastProvider } from '@/components/Toast';
import './globals.css';

// Vazirmatn variable webfont, bundled locally (no external fetch).
const vazirmatn = localFont({
  src: './fonts/Vazirmatn-Variable.woff2',
  variable: '--font-vazirmatn',
  display: 'swap',
  weight: '100 900',
});

export const metadata: Metadata = {
  metadataBase: new URL('https://inourai.ir'),
  title: {
    default: `${BRAND.fa} | پلتفرم هوش مصنوعی فارسی`,
    template: `%s | ${BRAND.fa}`,
  },
  description:
    'نورا؛ پلتفرم هوش مصنوعی فارسی: چت‌بات هوشمند، تولید تصویر با هوش مصنوعی، تبدیل متن به صوت و صوت به متن. همه‌چیز به زبان فارسی.',
  keywords: [
    'هوش مصنوعی',
    'هوش مصنوعی فارسی',
    'چت‌بات فارسی',
    'تولید تصویر با هوش مصنوعی',
    'تبدیل متن به صوت',
    'تبدیل صوت به متن',
    'دستیار هوش مصنوعی',
  ],
  openGraph: {
    type: 'website',
    locale: 'fa_IR',
    url: 'https://inourai.ir',
    siteName: BRAND.fa,
    title: `${BRAND.fa} | پلتفرم هوش مصنوعی فارسی`,
    description:
      'چت‌بات هوشمند، تولید تصویر، تبدیل متن به صوت و صوت به متن — همه به زبان فارسی.',
  },
  twitter: {
    card: 'summary_large_image',
    title: `${BRAND.fa} | پلتفرم هوش مصنوعی فارسی`,
    description: 'چت‌بات هوشمند، تولید تصویر، تبدیل متن به صوت و صوت به متن — فارسی.',
  },
  robots: { index: true, follow: true },
  alternates: {
    canonical: 'https://inourai.ir',
  },
};

// Inline, render-blocking script: applies the persisted theme before first paint
// so there is no flash of the wrong theme.
const themeInitScript = `(function(){try{var s=localStorage.getItem('${THEME_STORAGE_KEY}')||'system';var r=s==='system'?(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):s;document.documentElement.dataset.theme=r;document.documentElement.style.colorScheme=r;}catch(e){document.documentElement.dataset.theme='light';}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fa" dir="rtl" suppressHydrationWarning className={vazirmatn.variable}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <ThemeProvider>
          <QueryProvider>
            <ToastProvider>{children}</ToastProvider>
          </QueryProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
