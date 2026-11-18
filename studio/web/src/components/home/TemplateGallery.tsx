import { useMemo, useState } from 'react';
import {
  HOME_TEMPLATE_CATEGORIES,
  HOME_TEMPLATES,
  type HomeTemplateCard,
} from '@/data/homeTemplates';
import { cn } from '@/lib/format';

export function TemplateGallery({
  onSelectTemplate,
}: {
  onSelectTemplate: (tpl: HomeTemplateCard) => void;
}) {
  const [category, setCategory] = useState<(typeof HOME_TEMPLATE_CATEGORIES)[number]>('All');

  const filtered = useMemo(
    () =>
      category === 'All'
        ? HOME_TEMPLATES
        : HOME_TEMPLATES.filter((t) => t.category === category),
    [category],
  );

  return (
    <section aria-label="Start with a template" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-bold tracking-tight text-[var(--text-primary)]">
          Start with a template
        </h2>
      </div>

      {/* Category Chips */}
      <div className="flex flex-wrap items-center gap-2">
        {HOME_TEMPLATE_CATEGORIES.map((cat) => {
          const active = category === cat;
          return (
            <button
              key={cat}
              type="button"
              onClick={() => setCategory(cat)}
              className={cn(
                'rounded-full px-3.5 py-1.5 text-xs font-semibold transition-all cursor-pointer border',
                active
                  ? 'border-[var(--accent-lime-border)] bg-[var(--accent-lime)] text-zinc-950 shadow-xs'
                  : 'border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)]',
              )}
            >
              {cat}
            </button>
          );
        })}
      </div>

      {/* 5-Column Portrait Template Row */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5">
        {filtered.map((tpl) => (
          <button
            key={tpl.id}
            type="button"
            onClick={() => onSelectTemplate(tpl)}
            className="group relative flex flex-col overflow-hidden rounded-[14px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-left transition-all hover:-translate-y-0.5 hover:border-[var(--accent-lime-border)] hover:shadow-[var(--shadow-panel)] cursor-pointer"
          >
            {/* 9:14 Portrait Preview Surface (Zero external stock images) */}
            <div
              className="relative aspect-[9/13] w-full overflow-hidden p-3.5 flex flex-col justify-between"
              style={{ background: tpl.gradient }}
            >
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-black/55 px-2.5 py-0.5 text-[10px] font-semibold text-white backdrop-blur-xs">
                  {tpl.badge}
                </span>
                <span className="rounded-full bg-white/15 px-2 py-0.5 font-mono text-[9px] text-white/90">
                  9:16
                </span>
              </div>

              {/* Stylized silhouette / editorial framing motif */}
              <div className="my-auto flex flex-col items-center justify-center py-3">
                <div className="h-14 w-14 rounded-full bg-white/12 border border-white/20 flex items-center justify-center">
                  <div className="h-8 w-8 rounded-full bg-white/25" />
                </div>
                <div
                  className="mt-4 text-center text-sm font-extrabold leading-tight tracking-tight text-white drop-shadow-[0_2px_6px_rgba(0,0,0,0.85)]"
                  style={{ fontFamily: tpl.fontFamily }}
                >
                  <div>{tpl.sampleCaption}</div>
                  <div style={{ color: tpl.accentColor }}>{tpl.sampleCaptionHighlight}</div>
                </div>
              </div>

              <div className="text-[10px] font-mono text-white/70 truncate">
                {tpl.style_preset} · {tpl.style_playbook}
              </div>
            </div>

            <div className="p-3 bg-[var(--bg-surface)]">
              <div className="truncate text-xs font-semibold text-[var(--text-primary)] group-hover:text-[var(--accent-lime-strong)] transition-colors">
                {tpl.title}
              </div>
              <div className="mt-0.5 truncate text-[11px] text-[var(--text-muted)]">
                {tpl.subtitle}
              </div>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
