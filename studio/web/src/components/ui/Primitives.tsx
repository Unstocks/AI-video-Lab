import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';
import { cn } from '@/lib/format';
import { useToastStore } from '@/stores/useStudioStore';

export type Tone = 'neutral' | 'lime' | 'amber' | 'cyan' | 'violet' | 'pass' | 'warn' | 'fail';

const TONE_STYLES: Record<Tone, string> = {
  neutral: 'bg-[var(--bg-elevated)] text-[var(--text-secondary)] border-[var(--border-subtle)]',
  lime: 'bg-[var(--accent-lime-soft)] text-[var(--accent-lime-strong)] border-[var(--accent-lime-border)]/50',
  amber: 'bg-[var(--accent-amber-soft)] text-[var(--accent-amber)] border-[var(--accent-amber)]/30',
  cyan: 'bg-[var(--accent-cyan-soft)] text-[var(--accent-cyan)] border-[var(--accent-cyan)]/30',
  violet: 'bg-[var(--accent-violet-soft)] text-[var(--accent-violet)] border-[var(--accent-violet)]/30',
  pass: 'bg-[var(--status-pass-soft)] text-[var(--status-pass)] border-[var(--status-pass)]/30',
  warn: 'bg-[var(--status-warn-soft)] text-[var(--status-warn)] border-[var(--status-warn)]/30',
  fail: 'bg-[var(--status-fail-soft)] text-[var(--status-fail)] border-[var(--status-fail)]/30',
};

export function Badge({
  children,
  tone = 'neutral',
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium tracking-wide',
        TONE_STYLES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function StatusDot({
  tone = 'neutral',
  pulse = false,
}: {
  tone?: 'pass' | 'warn' | 'fail' | 'cyan' | 'amber' | 'neutral';
  pulse?: boolean;
}) {
  const color =
    tone === 'pass'
      ? 'bg-[var(--status-pass)]'
      : tone === 'warn'
        ? 'bg-[var(--status-warn)]'
        : tone === 'fail'
          ? 'bg-[var(--status-fail)]'
          : tone === 'cyan'
            ? 'bg-[var(--accent-cyan)]'
            : tone === 'amber'
              ? 'bg-[var(--accent-amber)]'
              : 'bg-[var(--text-muted)]';
  return (
    <span className="relative inline-flex h-2 w-2 shrink-0">
      {pulse && (
        <span
          className={cn('absolute inline-flex h-full w-full animate-ping rounded-full opacity-75', color)}
        />
      )}
      <span className={cn('relative inline-flex h-2 w-2 rounded-full', color)} />
    </span>
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'forest' | 'lime' | 'secondary' | 'ghost' | 'danger' | 'cyan';
  size?: 'xs' | 'sm' | 'md';
}

export function Button({
  variant = 'secondary',
  size = 'sm',
  className,
  children,
  ...rest
}: ButtonProps) {
  const styles = {
    primary:
      'bg-[var(--cta-primary)] text-[var(--cta-primary-text)] font-semibold hover:bg-[var(--cta-primary-hover)] active:scale-[0.99] shadow-xs',
    forest:
      'bg-[#14452f] text-white font-semibold hover:bg-[#0f3624] active:scale-[0.99] shadow-xs',
    lime:
      'bg-[var(--accent-lime)] text-zinc-950 font-semibold hover:brightness-95 active:scale-[0.99] shadow-xs',
    cyan: 'bg-[var(--accent-cyan)] text-white font-semibold hover:brightness-110 active:scale-[0.99] shadow-xs',
    secondary:
      'bg-[var(--bg-surface)] text-[var(--text-primary)] border border-[var(--border-subtle)] hover:border-[var(--border-strong)] hover:bg-[var(--bg-panel)]',
    ghost: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-elevated)]/80',
    danger:
      'bg-[var(--status-fail-soft)] text-[var(--status-fail)] border border-[var(--status-fail)]/40 hover:bg-[var(--status-fail)] hover:text-white',
  }[variant];

  const sizes = {
    xs: 'h-7 px-2 text-xs gap-1 rounded-md',
    sm: 'h-8 px-3 text-xs gap-1.5 rounded-lg',
    md: 'h-9 px-4 text-sm gap-2 rounded-lg',
  }[size];

  return (
    <button
      type="button"
      className={cn(
        'inline-flex items-center justify-center whitespace-nowrap transition-all duration-150 disabled:pointer-events-none disabled:opacity-45 cursor-pointer',
        styles,
        sizes,
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

export function Panel({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)]',
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-[var(--border-strong)] bg-[var(--bg-surface)]/60 px-6 py-12 text-center">
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--bg-elevated)] text-[var(--text-secondary)]">
        {icon}
      </div>
      <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
      <p className="mt-1 max-w-md text-xs text-[var(--text-muted)] leading-relaxed">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ToastViewport() {
  const { items, dismiss } = useToastStore();
  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 z-[90] flex w-80 flex-col gap-2"
    >
      <AnimatePresence initial={false}>
        {items.map((t) => {
          const Icon =
            t.tone === 'success'
              ? CheckCircle2
              : t.tone === 'warn'
                ? AlertTriangle
                : t.tone === 'error'
                  ? XCircle
                  : Info;
          const color =
            t.tone === 'success'
              ? 'text-[var(--status-pass)]'
              : t.tone === 'warn'
                ? 'text-[var(--status-warn)]'
                : t.tone === 'error'
                  ? 'text-[var(--status-fail)]'
                  : 'text-[var(--accent-cyan)]';
          return (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 14, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.96 }}
              transition={{ duration: 0.16 }}
              className="pointer-events-auto flex items-start gap-2.5 rounded-xl border border-[var(--border-strong)] bg-[var(--bg-panel)] p-3 shadow-[var(--shadow-float)]"
            >
              <Icon className={cn('mt-0.5 h-4 w-4 shrink-0', color)} />
              <div className="min-w-0 flex-1">
                <div className="text-xs font-semibold text-[var(--text-primary)]">{t.title}</div>
                {t.detail && (
                  <div className="mt-0.5 line-clamp-2 text-[11px] text-[var(--text-secondary)]">
                    {t.detail}
                  </div>
                )}
              </div>
              <button
                type="button"
                aria-label="Dismiss notification"
                onClick={() => dismiss(t.id)}
                className="text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
