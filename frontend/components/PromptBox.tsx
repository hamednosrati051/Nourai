'use client';

import { useState } from 'react';
import { Check, ChevronDown, Copy } from 'lucide-react';

const COLLAPSE_THRESHOLD = 300;

/**
 * User prompt display: heading with copy button, smart collapse for long
 * prompts with smooth expand. Better than a plain text dump.
 */
export function PromptBox({ prompt, dark = false, large = false }: { prompt: string; dark?: boolean; large?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);
  const isLong = prompt.length > COLLAPSE_THRESHOLD;
  const collapsed = isLong && !expanded;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard unavailable; no-op
    }
  };

  const textColor = dark ? 'text-white/90' : 'text-neutral-700 dark:text-slate-300';
  const boxBg = dark ? 'bg-white/10' : 'bg-neutral-100 dark:bg-navy-800';
  const headingColor = dark ? 'text-white' : '';

  return (
    <div className={`w-full rounded-xl px-5 py-3 ${boxBg}`}>
      <div className="mb-1 flex items-center justify-between">
        <h3 className={`text-base font-bold ${headingColor}`}>متن کاربر:</h3>
        <button
          type="button"
          onClick={copy}
          aria-label="کپی پرامت"
          className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-bold transition ${
            dark
              ? 'bg-white/10 text-white/80 hover:bg-white/20 hover:text-white'
              : 'bg-neutral-200 text-neutral-600 hover:bg-neutral-300 dark:bg-white/10 dark:text-slate-300 dark:hover:bg-white/20'
          }`}
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? 'کپی شد!' : 'کپی'}
        </button>
      </div>
      <div className="relative">
        <p
          dir="auto"
          className={`text-center ${large ? 'text-base leading-8' : 'text-sm leading-7'} ${textColor} transition-all ${
            collapsed ? 'max-h-24 overflow-hidden' : ''
          }`}
        >
          {prompt}
        </p>
        {collapsed && (
          <div
            aria-hidden="true"
            className={`pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t ${
              dark ? 'from-[#1a1a2e]' : 'from-neutral-100 dark:from-navy-800'
            } to-transparent`}
          />
        )}
      </div>
      {isLong && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className={`mx-auto mt-1 flex items-center gap-1 text-xs font-bold transition ${
            dark ? 'text-white/70 hover:text-white' : 'text-brand-600 hover:text-brand-700 dark:text-brand-400'
          }`}
        >
          {expanded ? 'بستن' : 'نمایش کامل'}
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform ${expanded ? 'rotate-180' : ''}`}
          />
        </button>
      )}
    </div>
  );
}
