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
  title: {
    default: `${BRAND.fa} | پلتفرم هوش مصنوعی`,
    template: `%s | ${BRAND.fa}`,
  },
  description: 'پلتفرم هوش مصنوعی نورا: گفت‌وگوی متنی، تعامل صوتی و تولید تصویر.',
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
