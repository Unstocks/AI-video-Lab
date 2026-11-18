import {
  Briefcase,
  FileText,
  Film,
  Image as ImageIcon,
  Music,
  Settings,
  Shapes,
  Sparkles,
  Subtitles,
  Type,
} from 'lucide-react';
import { cn } from '@/lib/format';
import { useEditorStore } from '@/stores/useEditorStore';
import type { ToolId } from '@/types/editor';

const TOOLS: Array<{ id: ToolId; label: string; icon: typeof Film }> = [
  { id: 'ai-tools', label: 'AI Tools', icon: Sparkles },
  { id: 'video', label: 'Video', icon: Film },
  { id: 'audio', label: 'Audio', icon: Music },
  { id: 'image', label: 'Image', icon: ImageIcon },
  { id: 'subtitles', label: 'Subtitles', icon: Subtitles },
  { id: 'text', label: 'Text', icon: Type },
  { id: 'elements', label: 'Elements', icon: Shapes },
  { id: 'script', label: 'Script', icon: FileText },
  { id: 'brand-kit', label: 'Brand Kit', icon: Briefcase },
  { id: 'settings', label: 'Settings', icon: Settings },
];

export function ToolRail() {
  const { activeTool, setActiveTool } = useEditorStore();

  return (
    <nav
      aria-label="Editor Tool Rail"
      className="flex w-[68px] shrink-0 flex-col items-center gap-1 border-r border-[var(--border-subtle)] bg-[var(--bg-surface)] py-2.5 overflow-y-auto select-none"
    >
      {TOOLS.map((tool) => {
        const Icon = tool.icon;
        const active = activeTool === tool.id;
        return (
          <button
            key={tool.id}
            type="button"
            aria-label={tool.label}
            aria-current={active ? 'page' : undefined}
            onClick={() => setActiveTool(tool.id)}
            className={cn(
              'relative flex w-[56px] flex-col items-center justify-center gap-1 rounded-[10px] py-2 text-[10px] font-medium transition-all cursor-pointer border',
              active
                ? 'border-[var(--accent-lime-border)] bg-[var(--accent-lime-soft)] text-[var(--text-primary)] font-semibold shadow-2xs'
                : 'border-transparent text-[var(--text-secondary)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)]',
            )}
          >
            {active && (
              <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r-full bg-[var(--accent-lime-border)]" />
            )}
            <Icon className={cn('h-[18px] w-[18px]', active && 'text-[var(--accent-lime-strong)]')} />
            <span className="leading-none tracking-tight">{tool.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
