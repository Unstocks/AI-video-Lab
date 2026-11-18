import { useMemo, useState } from 'react';
import { BookmarkPlus, ChevronRight } from 'lucide-react';
import {
  TEXT_TEMPLATES,
  createOverlayFromTemplate,
  type TextTemplateCategory,
  type TextTemplateDef,
} from '@/data/textTemplates';
import { cn } from '@/lib/format';
import { playbackHub, toast } from '@/stores/useStudioStore';
import { useEditorStore } from '@/stores/useEditorStore';
import { useBrandKitStore } from '@/stores/useBrandKitStore';

const CHIPS: Array<'All' | TextTemplateCategory> = [
  'All',
  'Simple',
  'Title',
  'Lower Third',
  'Other',
];

export function TextPanel({ duration }: { duration: number }) {
  const { addTextOverlay } = useEditorStore();
  const { saveItem } = useBrandKitStore();
  const [chip, setChip] = useState<'All' | TextTemplateCategory>('All');
  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  const handleInsert = (tpl: TextTemplateDef) => {
    const item = createOverlayFromTemplate(tpl, playbackHub.currentTime, Math.max(duration, 10));
    addTextOverlay(item);
    toast.success(`Added "${tpl.label}"`, 'Drag, resize corners, or rotate on preview canvas.');
  };

  const quickTiles = useMemo(
    () =>
      TEXT_TEMPLATES.filter(
        (t) => t.section === 'Quick' && (chip === 'All' || t.category === chip),
      ),
    [chip],
  );

  const groupedSections = useMemo(() => {
    const order: Array<'Title' | 'Lower Third' | 'Other'> = ['Title', 'Lower Third', 'Other'];
    return order
      .map((sec) => ({
        title: sec,
        items: TEXT_TEMPLATES.filter(
          (t) => t.section === sec && (chip === 'All' || t.category === chip),
        ),
      }))
      .filter((g) => g.items.length > 0);
  }, [chip]);

  const renderTile = (tpl: TextTemplateDef) => (
    <div key={tpl.id} className="group relative">
      <button
        type="button"
        onClick={() => handleInsert(tpl)}
        className="flex h-[82px] w-full flex-col items-center justify-center rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-panel)] px-2 text-center transition-all hover:border-[var(--accent-lime-border)] hover:bg-[var(--bg-elevated)] cursor-pointer overflow-hidden"
      >
        <span
          className="truncate max-w-full leading-tight text-[var(--text-primary)]"
          style={{
            fontFamily: tpl.fontFamily,
            fontWeight: tpl.fontWeight,
            fontStyle: tpl.italic ? 'italic' : 'normal',
            textTransform: tpl.uppercase ? 'uppercase' : 'none',
            fontSize: tpl.sampleSubtext ? '16px' : '19px',
            letterSpacing: tpl.letterSpacing,
          }}
        >
          {tpl.sampleText}
        </span>
        {tpl.sampleSubtext && (
          <span
            className="mt-0.5 truncate max-w-full text-[11px] text-[var(--text-secondary)]"
            style={{ fontFamily: tpl.fontFamily }}
          >
            {tpl.sampleSubtext}
          </span>
        )}
      </button>

      <button
        type="button"
        title="Save to Brand Kit"
        aria-label={`Save ${tpl.label} to Brand Kit`}
        onClick={(e) => {
          e.stopPropagation();
          void saveItem('saved', `Text · ${tpl.label}`, {
            kind: 'text_template',
            templateId: tpl.id,
            sampleText: tpl.sampleText,
            fontFamily: tpl.fontFamily,
          });
        }}
        className="absolute right-1.5 top-1.5 hidden h-6 w-6 items-center justify-center rounded-md bg-[var(--bg-surface)]/90 text-[var(--text-muted)] shadow-xs hover:text-[var(--text-primary)] group-hover:flex cursor-pointer"
      >
        <BookmarkPlus className="h-3.5 w-3.5" />
      </button>
    </div>
  );

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header + Filter Chips */}
      <div className="space-y-3 border-b border-[var(--border-subtle)] px-4 py-3">
        <h2 className="text-base font-bold text-[var(--text-primary)]">Text</h2>
        <div className="flex flex-wrap gap-1.5">
          {CHIPS.map((c) => {
            const active = chip === c;
            return (
              <button
                key={c}
                type="button"
                onClick={() => setChip(c)}
                className={cn(
                  'rounded-full px-3 py-1 text-xs font-semibold border transition-colors cursor-pointer',
                  active
                    ? 'border-[var(--accent-lime-border)] bg-[var(--accent-lime)] text-zinc-950'
                    : 'border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]',
                )}
              >
                {c}
              </button>
            );
          })}
        </div>
      </div>

      {/* Scrollable 2-Column 166×82px Tile Grids */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-6">
        {quickTiles.length > 0 && (
          <div className="grid grid-cols-2 gap-2.5">{quickTiles.map(renderTile)}</div>
        )}

        {groupedSections.map((group) => {
          const expanded = expandedSection === group.title;
          const visible = expanded ? group.items : group.items.slice(0, 6);
          return (
            <div key={group.title} className="space-y-2.5">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold text-[var(--text-primary)]">{group.title}</h3>
                <button
                  type="button"
                  onClick={() => setExpandedSection(expanded ? null : group.title)}
                  className="inline-flex items-center gap-0.5 text-[11px] font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] cursor-pointer"
                >
                  <span>{expanded ? 'Collapse' : 'View All'}</span>
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2.5">{visible.map(renderTile)}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
