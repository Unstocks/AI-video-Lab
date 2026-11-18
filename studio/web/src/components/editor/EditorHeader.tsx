import { useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  Check,
  Download,
  Film,
  Layers,
  Moon,
  Redo2,
  Save,
  ShieldCheck,
  Sparkles,
  Sun,
  Undo2,
} from 'lucide-react';
import { studioApi } from '@/lib/api';
import { cn } from '@/lib/format';
import {
  toast,
  useProjectStore,
  useSystemStore,
} from '@/stores/useStudioStore';
import { useEditorStore } from '@/stores/useEditorStore';
import { Button, StatusDot } from '@/components/ui/Primitives';
import type { AspectRatioId } from '@/types/editor';

export function EditorHeader() {
  const { projectId = 'demo' } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { theme, toggleTheme, health, dockOpen, setDockOpen } = useSystemStore();
  const { boardState, loadProjects } = useProjectStore();
  const {
    projectTitle,
    setProjectTitle,
    aspectRatio,
    setAspectRatio,
    past,
    future,
    undo,
    redo,
    dirtyDraft,
    persistDraft,
  } = useEditorStore();

  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState(projectTitle);
  const [savingDraft, setSavingDraft] = useState(false);

  const awaitingStage = boardState?.stages?.find((s) => s.status === 'awaiting_human') ?? null;
  const isBoard = location.pathname.endsWith('/board');
  const isQa = location.pathname.endsWith('/qa');
  const isEditor = !isBoard && !isQa;

  const commitTitle = async () => {
    setEditingTitle(false);
    const trimmed = titleDraft.trim();
    if (!trimmed || trimmed === projectTitle) return;
    setProjectTitle(trimmed);
    if (projectId !== 'demo') {
      try {
        await studioApi.updateProjectTitle(projectId, trimmed);
        void loadProjects();
        toast.success('Project renamed', trimmed);
      } catch (e) {
        toast.error('Rename failed', String(e));
      }
    }
  };

  const handleSaveDraft = async () => {
    setSavingDraft(true);
    await persistDraft(projectId);
    setSavingDraft(false);
    toast.success('Draft saved', 'Local workspace draft synced to .studio/sessions.sqlite');
  };

  return (
    <header className="flex h-[52px] shrink-0 items-center justify-between gap-2 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 select-none">
      {/* Left: Home V Mark + Inline Editable Project Title + Undo/Redo */}
      <div className="flex min-w-0 items-center gap-2.5">
        <button
          type="button"
          onClick={() => navigate('/')}
          title="Back to Home"
          aria-label="Back to Home"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--text-primary)] text-[var(--bg-surface)] font-black text-sm tracking-tighter hover:opacity-90 cursor-pointer"
        >
          V
        </button>

        <div className="h-5 w-px bg-[var(--border-subtle)]" />

        {editingTitle ? (
          <input
            autoFocus
            value={titleDraft}
            onChange={(e) => setTitleDraft(e.target.value)}
            onBlur={() => void commitTitle()}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void commitTitle();
              if (e.key === 'Escape') {
                setTitleDraft(projectTitle);
                setEditingTitle(false);
              }
            }}
            aria-label="Edit project title"
            className="h-7 w-52 rounded-md border border-[var(--accent-lime-border)] bg-[var(--bg-input)] px-2 text-xs font-semibold text-[var(--text-primary)] focus:outline-none"
          />
        ) : (
          <button
            type="button"
            onClick={() => {
              setTitleDraft(projectTitle);
              setEditingTitle(true);
            }}
            title="Click to rename project"
            className="max-w-[210px] truncate rounded-md px-2 py-1 text-left text-xs font-semibold text-[var(--text-primary)] hover:bg-[var(--bg-panel)] transition-colors cursor-pointer"
          >
            {projectTitle}
          </button>
        )}

        {/* Undo / Redo */}
        <div className="flex items-center gap-0.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-0.5">
          <button
            type="button"
            disabled={past.length === 0}
            onClick={undo}
            aria-label="Undo"
            title={`Undo (${past.length}) · Ctrl+Z`}
            className="flex h-6 w-7 items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-surface)] hover:text-[var(--text-primary)] disabled:opacity-35 cursor-pointer"
          >
            <Undo2 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            disabled={future.length === 0}
            onClick={redo}
            aria-label="Redo"
            title={`Redo (${future.length}) · Ctrl+Y`}
            className="flex h-6 w-7 items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-surface)] hover:text-[var(--text-primary)] disabled:opacity-35 cursor-pointer"
          >
            <Redo2 className="h-3.5 w-3.5" />
          </button>
        </div>

        {dirtyDraft && (
          <button
            type="button"
            onClick={() => void handleSaveDraft()}
            disabled={savingDraft}
            className="hidden xl:inline-flex items-center gap-1 rounded-full border border-[var(--accent-lime-border)]/60 bg-[var(--accent-lime-soft)] px-2.5 py-0.5 text-[11px] font-semibold text-[var(--accent-lime-strong)] hover:brightness-95 cursor-pointer"
          >
            {savingDraft ? <Check className="h-3 w-3" /> : <Save className="h-3 w-3" />}
            Save Draft
          </button>
        )}
      </div>

      {/* Center: Mode Switcher (Editor / Pipeline Board / QA & Export) */}
      <nav
        aria-label="Editor Views"
        className="hidden md:flex items-center gap-1 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-0.5"
      >
        {(
          [
            ['editor', 'Editor', `/editor/${encodeURIComponent(projectId)}`, Film, isEditor],
            [
              'board',
              'Pipeline Board',
              `/editor/${encodeURIComponent(projectId)}/board`,
              Layers,
              isBoard,
            ],
            [
              'qa',
              'QA & Export',
              `/editor/${encodeURIComponent(projectId)}/qa`,
              ShieldCheck,
              isQa,
            ],
          ] as const
        ).map(([id, label, path, Icon, active]) => (
          <button
            key={id}
            type="button"
            onClick={() => navigate(path)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition-all cursor-pointer',
              active
                ? 'bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-xs'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      {/* Right: Aspect Ratio + Hardware Pill + Theme + Slide-Over Producer Drawer + Export */}
      <div className="flex shrink-0 items-center gap-2">
        <select
          aria-label="Canvas aspect ratio"
          value={aspectRatio}
          onChange={(e) => setAspectRatio(e.target.value as AspectRatioId)}
          className="h-8 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-panel)] px-2 text-xs font-mono font-semibold text-[var(--text-primary)] cursor-pointer"
        >
          <option value="9:16">9:16 Portrait</option>
          <option value="16:9">16:9 Landscape</option>
          <option value="1:1">1:1 Square</option>
          <option value="4:5">4:5 Feed</option>
        </select>

        <span className="hidden 2xl:inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-panel)] px-2.5 py-1 font-mono text-[10px] text-[var(--text-secondary)]">
          <StatusDot tone={health?.nvenc_available ? 'pass' : 'neutral'} />
          {health?.nvenc_available ? 'NVENC' : 'x264'}
        </span>

        <button
          type="button"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          title={theme === 'dark' ? 'Creator Crisp Light' : 'Broadcast Obsidian Dark'}
          className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
        >
          {theme === 'dark' ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
        </button>

        {/* Slide-Over Executive Producer Toggle */}
        <button
          type="button"
          onClick={() => setDockOpen(!dockOpen)}
          aria-label="Toggle Executive Producer Drawer"
          title="Executive Producer (fcc-claude) · Ctrl+J"
          className={cn(
            'inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-xs font-semibold transition-all cursor-pointer',
            awaitingStage
              ? 'border-[var(--accent-amber)] bg-[var(--accent-amber-soft)] text-[var(--accent-amber)]'
              : dockOpen
                ? 'border-[var(--accent-lime-border)] bg-[var(--accent-lime)] text-zinc-950'
                : 'border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-primary)] hover:border-[var(--border-strong)]',
          )}
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">
            {awaitingStage ? `Gate: ${awaitingStage.name}` : 'Producer'}
          </span>
          {awaitingStage && <StatusDot tone="amber" pulse />}
        </button>

        <Button
          variant="primary"
          size="sm"
          onClick={() => navigate(`/editor/${encodeURIComponent(projectId)}/qa`)}
          className="rounded-full px-4"
        >
          <Download className="h-3.5 w-3.5" />
          Export
        </Button>
      </div>
    </header>
  );
}
