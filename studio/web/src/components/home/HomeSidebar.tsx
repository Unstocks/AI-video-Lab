import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  ChevronRight,
  Cpu,
  ExternalLink,
  Film,
  FolderOpen,
  Grid2x2,
  Moon,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  Scissors,
  Sparkles,
  Sun,
  Video,
  Wand2,
} from 'lucide-react';
import { buildThumbUrl } from '@/lib/api';
import { cn } from '@/lib/format';
import { useProjectStore, useSystemStore } from '@/stores/useStudioStore';
import { useEditorStore } from '@/stores/useEditorStore';
import { StatusDot } from '@/components/ui/Primitives';

const THUMB_GRADIENTS = [
  'linear-gradient(135deg, #1e293b, #334155)',
  'linear-gradient(135deg, #14452f, #22543d)',
  'linear-gradient(135deg, #3b0764, #6d28d9)',
  'linear-gradient(135deg, #7c2d12, #c2410c)',
  'linear-gradient(135deg, #0c4a6e, #0284c7)',
];

export function HomeSidebar({
  collapsed,
  onToggleCollapse,
}: {
  collapsed: boolean;
  onToggleCollapse: () => void;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const { projects, activeProjectId } = useProjectStore();
  const { theme, toggleTheme, health, setDockOpen } = useSystemStore();
  const { setActiveTool } = useEditorStore();
  const [showAllRecents, setShowAllRecents] = useState(false);

  const primaryProjectId = activeProjectId || projects[0]?.project_id || 'demo';
  const visibleRecents = showAllRecents ? projects : projects.slice(0, 10);

  const openEditorWithTool = (tool: 'video' | 'image' | 'brand-kit') => {
    setActiveTool(tool);
    navigate(`/editor/${encodeURIComponent(primaryProjectId)}`);
  };

  return (
    <aside
      aria-label="Home Navigation"
      style={{ width: collapsed ? 68 : 280 }}
      className="flex h-full shrink-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-surface)] transition-[width] duration-200 select-none overflow-hidden"
    >
      {/* Brand Header: Bold V Mark + Collapse */}
      <div className="flex h-14 shrink-0 items-center justify-between px-4">
        <button
          type="button"
          onClick={() => navigate('/')}
          className="flex items-center gap-2.5 text-left cursor-pointer min-w-0"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--text-primary)] text-[var(--bg-surface)] font-black text-base tracking-tighter">
            V
          </span>
          {!collapsed && (
            <div className="min-w-0 leading-tight">
              <div className="truncate text-sm font-bold tracking-tight text-[var(--text-primary)]">
                AI Video Lab
              </div>
              <div className="truncate font-mono text-[10px] text-[var(--text-muted)]">
                OpenMontage Studio
              </div>
            </div>
          )}
        </button>

        {!collapsed && (
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-label="Collapse sidebar"
            title="Collapse sidebar"
            className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--text-muted)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)] cursor-pointer"
          >
            <PanelLeftClose className="h-4 w-4" />
          </button>
        )}
      </div>

      {collapsed && (
        <div className="flex justify-center pb-2">
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-label="Expand sidebar"
            title="Expand sidebar"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-muted)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)] cursor-pointer"
          >
            <PanelLeftOpen className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Primary Actions: Create video / Edit video */}
      <div className="px-3 space-y-1">
        <button
          type="button"
          onClick={() => navigate('/')}
          className={cn(
            'flex w-full items-center gap-2.5 rounded-full px-3 py-2 text-[13px] font-semibold transition-colors cursor-pointer',
            location.pathname === '/'
              ? 'bg-[var(--bg-elevated)] text-[var(--text-primary)]'
              : 'text-[var(--text-secondary)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)]',
            collapsed && 'justify-center px-0',
          )}
          title="Create video"
        >
          <Sparkles className="h-4 w-4 shrink-0" />
          {!collapsed && <span className="truncate">Create video</span>}
        </button>

        <button
          type="button"
          onClick={() => navigate(`/editor/${encodeURIComponent(primaryProjectId)}`)}
          className={cn(
            'flex w-full items-center gap-2.5 rounded-full px-3 py-2 text-[13px] font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)] transition-colors cursor-pointer',
            collapsed && 'justify-center px-0',
          )}
          title="Edit video"
        >
          <Scissors className="h-4 w-4 shrink-0" />
          {!collapsed && <span className="truncate">Edit video</span>}
        </button>
      </div>

      {/* Secondary Nav */}
      <div className="mt-4 px-3 space-y-0.5">
        {[
          { label: 'Create asset', icon: Wand2, onClick: () => openEditorWithTool('image') },
          { label: 'Assets', icon: FolderOpen, onClick: () => openEditorWithTool('video') },
          { label: 'Brand', icon: Palette, onClick: () => openEditorWithTool('brand-kit') },
          {
            label: 'System & 169 Tools',
            icon: Cpu,
            active: location.pathname === '/system',
            onClick: () => navigate('/system'),
          },
        ].map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.label}
              type="button"
              onClick={item.onClick}
              title={item.label}
              className={cn(
                'flex w-full items-center gap-2.5 rounded-lg px-3 py-1.5 text-[13px] transition-colors cursor-pointer',
                item.active
                  ? 'bg-[var(--bg-elevated)] text-[var(--text-primary)] font-semibold'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)]',
                collapsed && 'justify-center px-0',
              )}
            >
              <Icon className="h-4 w-4 shrink-0 text-[var(--text-muted)]" />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </button>
          );
        })}
      </div>

      {/* Recents Project Stack */}
      {!collapsed && (
        <div className="mt-5 flex min-h-0 flex-1 flex-col border-t border-[var(--border-subtle)] pt-3">
          <div className="flex items-center justify-between px-4 pb-2">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
              Recents
            </span>
            {projects.length > 0 && (
              <span className="font-mono text-[10px] text-[var(--text-muted)]">
                {projects.length}
              </span>
            )}
          </div>

          <div className="flex-1 overflow-y-auto px-2.5 space-y-1">
            {/* Instant Hinglish/English Creator Demo Shortcut */}
            <button
              type="button"
              onClick={() => navigate('/editor/demo')}
              className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-[var(--bg-panel)] transition-colors cursor-pointer"
            >
              <div
                className="flex h-7 w-10 shrink-0 items-center justify-center rounded-md text-[10px] font-bold text-zinc-950"
                style={{ background: 'linear-gradient(135deg, #c6f64d, #84cc16)' }}
              >
                DEMO
              </div>
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-medium text-[var(--text-primary)]">
                  Book Reading — Hinglish Short
                </div>
                <div className="truncate text-[10px] text-[var(--text-muted)]">
                  Interactive Sandbox · 9:16
                </div>
              </div>
            </button>

            {visibleRecents.map((p, idx) => {
              const pid = p.project_id || p.id || '';
              const thumb = p.poster ? buildThumbUrl(pid, p.poster, 120) : null;
              return (
                <button
                  key={pid}
                  type="button"
                  onClick={() => navigate(`/editor/${encodeURIComponent(pid)}`)}
                  className="group flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-[var(--bg-panel)] transition-colors cursor-pointer"
                >
                  <div
                    className="relative h-7 w-10 shrink-0 overflow-hidden rounded-md border border-[var(--border-subtle)]"
                    style={{ background: THUMB_GRADIENTS[idx % THUMB_GRADIENTS.length] }}
                  >
                    {thumb ? (
                      <img
                        src={thumb}
                        alt=""
                        className="h-full w-full object-cover"
                        onError={(e) => {
                          (e.currentTarget as HTMLImageElement).style.display = 'none';
                        }}
                      />
                    ) : (
                      <div className="flex h-full w-full items-center justify-center text-white/75">
                        <Film className="h-3.5 w-3.5" />
                      </div>
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate text-xs font-medium text-[var(--text-primary)]">
                        {p.title || pid}
                      </span>
                      {p.awaiting_human && <StatusDot tone="amber" pulse />}
                      {p.live && !p.awaiting_human && <StatusDot tone="pass" pulse />}
                    </div>
                    <div className="truncate font-mono text-[10px] text-[var(--text-muted)]">
                      {p.pipeline_type || 'clip-factory'}
                    </div>
                  </div>
                </button>
              );
            })}

            {projects.length > 10 && (
              <button
                type="button"
                onClick={() => setShowAllRecents((v) => !v)}
                className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-panel)] cursor-pointer"
              >
                <span>{showAllRecents ? 'Show less' : `View all (${projects.length})`}</span>
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Bottom Footer Links */}
      <div className="mt-auto border-t border-[var(--border-subtle)] px-3 py-2.5 space-y-1">
        {!collapsed && (
          <div className="flex items-center justify-between px-2 pb-1.5 text-[10px] text-[var(--text-muted)]">
            <span className="inline-flex items-center gap-1.5">
              <StatusDot tone={health?.fcc_online ? 'pass' : 'warn'} />
              {health?.fcc_online ? 'FCC Online' : 'FCC Standby'}
            </span>
            <span className="font-mono">{health?.nvenc_available ? 'NVENC' : 'x264'}</span>
          </div>
        )}

        <div className={cn('flex items-center gap-1', collapsed ? 'flex-col' : 'justify-between')}>
          <button
            type="button"
            onClick={() => setDockOpen(true)}
            title="Executive Producer (Ctrl+J)"
            className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)] cursor-pointer"
          >
            <Video className="h-3.5 w-3.5" />
            {!collapsed && <span>API / Producer</span>}
          </button>

          {!collapsed && (
            <a
              href="http://127.0.0.1:4750"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-[var(--text-secondary)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)]"
              title="Open Read-Only Backlot Board (port 4750)"
            >
              <Grid2x2 className="h-3.5 w-3.5" />
              <span>More apps</span>
              <ExternalLink className="h-2.5 w-2.5 opacity-60" />
            </a>
          )}

          <button
            type="button"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            title={theme === 'dark' ? 'Creator Crisp Light' : 'Broadcast Obsidian Dark'}
            className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
          >
            {theme === 'dark' ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
          </button>
        </div>
      </div>
    </aside>
  );
}
