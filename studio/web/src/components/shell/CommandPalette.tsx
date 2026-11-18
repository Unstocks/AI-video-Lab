import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Cpu,
  Film,
  FolderOpen,
  Layers,
  Moon,
  PanelRight,
  Search,
  ShieldCheck,
  Sparkles,
  Sun,
} from 'lucide-react';
import { useProjectStore, useSystemStore } from '@/stores/useStudioStore';
import { cn } from '@/lib/format';

interface CommandAction {
  id: string;
  group: string;
  label: string;
  hint?: string;
  icon: typeof Film;
  run: () => void;
}

export function CommandPalette() {
  const navigate = useNavigate();
  const { commandPaletteOpen, setCommandPaletteOpen, theme, toggleTheme, dockOpen, setDockOpen } =
    useSystemStore();
  const { projects, activeProjectId } = useProjectStore();
  const [query, setQuery] = useState('');
  const [selectedIdx, setSelectedIdx] = useState(0);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCommandPaletteOpen(!useSystemStore.getState().commandPaletteOpen);
      } else if (e.key === 'Escape' && useSystemStore.getState().commandPaletteOpen) {
        setCommandPaletteOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [setCommandPaletteOpen]);

  const actions = useMemo<CommandAction[]>(() => {
    const base: CommandAction[] = [
      {
        id: 'nav-hub',
        group: 'Workspaces',
        label: 'Production Command Hub & Project Library',
        hint: '1',
        icon: Sparkles,
        run: () => navigate('/'),
      },
      {
        id: 'nav-system',
        group: 'Workspaces',
        label: 'System Capabilities & 169-Tool Registry Matrix',
        hint: '5',
        icon: Cpu,
        run: () => navigate('/system'),
      },
      {
        id: 'toggle-theme',
        group: 'Studio Controls',
        label: theme === 'dark' ? 'Switch to Light Studio Theme' : 'Switch to Broadcast Obsidian Dark Theme',
        icon: theme === 'dark' ? Sun : Moon,
        run: () => toggleTheme(),
      },
      {
        id: 'toggle-dock',
        group: 'Studio Controls',
        label: dockOpen ? 'Collapse Executive Producer Dock' : 'Open Executive Producer Dock',
        icon: PanelRight,
        run: () => setDockOpen(!dockOpen),
      },
    ];

    if (activeProjectId) {
      base.splice(
        1,
        0,
        {
          id: 'nav-nle',
          group: 'Active Project',
          label: `Open Pro NLE Clip & Reframe Studio (${activeProjectId})`,
          hint: '2',
          icon: Film,
          run: () => navigate(`/project/${activeProjectId}/nle`),
        },
        {
          id: 'nav-board',
          group: 'Active Project',
          label: `Open Universal Pipeline Board (${activeProjectId})`,
          hint: '3',
          icon: Layers,
          run: () => navigate(`/project/${activeProjectId}/board`),
        },
        {
          id: 'nav-qa',
          group: 'Active Project',
          label: `Open Broadcast QA & Export Studio (${activeProjectId})`,
          hint: '4',
          icon: ShieldCheck,
          run: () => navigate(`/project/${activeProjectId}/qa`),
        },
      );
    }

    for (const p of projects.slice(0, 12)) {
      const pid = p.project_id || p.id || '';
      if (!pid) continue;
      const targetTab = p.pipeline_type === 'clip-factory' ? 'nle' : 'board';
      base.push({
        id: `proj-${pid}`,
        group: 'Projects',
        label: p.title || pid,
        hint: p.pipeline_type || 'project',
        icon: FolderOpen,
        run: () => navigate(`/project/${pid}/${targetTab}`),
      });
    }
    return base;
  }, [activeProjectId, dockOpen, navigate, projects, setDockOpen, theme, toggleTheme]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return actions;
    return actions.filter(
      (a) =>
        a.label.toLowerCase().includes(q) ||
        a.group.toLowerCase().includes(q) ||
        (a.hint || '').toLowerCase().includes(q),
    );
  }, [actions, query]);

  useEffect(() => {
    setSelectedIdx(0);
  }, [query, commandPaletteOpen]);

  const execute = (action: CommandAction) => {
    setCommandPaletteOpen(false);
    setQuery('');
    action.run();
  };

  return (
    <AnimatePresence>
      {commandPaletteOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] flex items-start justify-center bg-black/65 pt-[12vh] backdrop-blur-xs"
          onMouseDown={() => setCommandPaletteOpen(false)}
        >
          <motion.div
            initial={{ opacity: 0, y: -12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.97 }}
            transition={{ duration: 0.14 }}
            className="w-full max-w-xl overflow-hidden rounded-2xl border border-[var(--border-strong)] bg-[var(--bg-surface)] shadow-[var(--shadow-float)]"
            onMouseDown={(e) => e.stopPropagation()}
            role="dialog"
            aria-label="Command Palette"
          >
            <div className="flex items-center gap-2.5 border-b border-[var(--border-subtle)] px-4 py-3">
              <Search className="h-4 w-4 text-[var(--text-muted)]" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    setSelectedIdx((i) => Math.min(filtered.length - 1, i + 1));
                  } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    setSelectedIdx((i) => Math.max(0, i - 1));
                  } else if (e.key === 'Enter' && filtered[selectedIdx]) {
                    e.preventDefault();
                    execute(filtered[selectedIdx]);
                  }
                }}
                placeholder="Jump to workspace, project, or studio action…"
                className="w-full bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none"
              />
              <kbd className="rounded border border-[var(--border-subtle)] bg-[var(--bg-panel)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-muted)]">
                ESC
              </kbd>
            </div>

            <div className="max-h-80 overflow-y-auto p-2">
              {filtered.length === 0 ? (
                <div className="px-3 py-8 text-center text-xs text-[var(--text-muted)]">
                  No matching studio actions.
                </div>
              ) : (
                filtered.map((item, idx) => {
                  const Icon = item.icon;
                  const active = idx === selectedIdx;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onMouseEnter={() => setSelectedIdx(idx)}
                      onClick={() => execute(item)}
                      className={cn(
                        'flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs transition-colors cursor-pointer',
                        active
                          ? 'bg-[var(--accent-amber-soft)] text-[var(--text-primary)]'
                          : 'text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]',
                      )}
                    >
                      <span className="flex items-center gap-2.5 truncate">
                        <Icon
                          className={cn(
                            'h-4 w-4 shrink-0',
                            active ? 'text-[var(--accent-amber)]' : 'text-[var(--text-muted)]',
                          )}
                        />
                        <span className="truncate font-medium">{item.label}</span>
                      </span>
                      <span className="ml-3 flex items-center gap-2 shrink-0">
                        <span className="text-[10px] text-[var(--text-muted)]">{item.group}</span>
                        {item.hint && (
                          <kbd className="rounded border border-[var(--border-subtle)] bg-[var(--bg-panel)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-muted)]">
                            {item.hint}
                          </kbd>
                        )}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
