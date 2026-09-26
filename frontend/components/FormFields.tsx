'use client';

/** Small controlled form primitives for admin/dashboard forms. */

interface BaseProps {
  label: string;
  required?: boolean;
  disabled?: boolean;
  hint?: string;
}

interface TextProps extends BaseProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  dir?: 'rtl' | 'ltr' | 'auto';
}

export function TextField({ label, required, disabled, hint, value, onChange, placeholder, dir }: TextProps) {
  return (
    <Field label={label} required={required} hint={hint}>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        dir={dir}
        className="input"
      />
    </Field>
  );
}

interface NumberProps extends BaseProps {
  value: string;
  onChange: (value: string) => void;
  min?: number;
  max?: number;
  placeholder?: string;
}

export function NumberField({ label, required, disabled, hint, value, onChange, min, max, placeholder }: NumberProps) {
  return (
    <Field label={label} required={required} hint={hint}>
      <input
        type="number"
        inputMode="numeric"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        min={min}
        max={max}
        placeholder={placeholder}
        disabled={disabled}
        dir="ltr"
        className="input"
      />
    </Field>
  );
}

interface TextAreaProps extends BaseProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
}

export function TextAreaField({ label, required, disabled, hint, value, onChange, placeholder, rows = 3 }: TextAreaProps) {
  return (
    <Field label={label} required={required} hint={hint}>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        disabled={disabled}
        className="input resize-y"
      />
    </Field>
  );
}

export function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-bold">
        {label}
        {required && <span className="mr-1 text-rose-500" aria-hidden="true">*</span>}
      </span>
      {children}
      {hint && <span className="mt-1 block text-xs text-neutral-500 dark:text-slate-400">{hint}</span>}
    </label>
  );
}
