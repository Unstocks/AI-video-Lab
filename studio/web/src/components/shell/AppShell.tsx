import { useEffect, type ReactNode } from 'react';
import { Link, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  Clapperboard,
  Cpu,
  Film,
  Layers,
  Moon,
  PanelRightClose,
  PanelRightOpen,
  Search,
  ShieldCheck,
  Sparkles,
  Sun,
} from 'lucide-react';
import { cn } from '@/lib/format';
import { useProjectStore, useSystemStore } from '@/stores/useStudioStore';
import { Badge, StatusDot, ToastViewport } from '@/components/ui/Primitives';
import { CommandPalette } from '@/components/shell/CommandPalette';
import { ExecutiveProducerDock } from '@/components/supervisor/ExecutiveProducerDock';

export function AppShell({ children }: { children?: ReactNode }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { projectId: routeProjectId } = useParams();
  const {
    health,
    theme,
    toggleTheme,
    dockOpen,
    setDockOpen,
    setCommandPaletteOpen,
    bootstrap,
    refreshHealth,
  } = useSystemStore();
  const { activeProjectId, projects, loadProjects, loadProject } = useProjectStore();

  const currentProjectId =
    routeProjectId ||
    activeProjectId ||
    projects[0]?.project_id ||
    projects[0]?.id ||
    null;

  useEffect(() => {
    bootstrap();
    loadProjects();
    const timer = window.setInterval(refreshHealth, 30000);
    return () => window.clearInterval(timer);
  }, [bootstrap, loadProjects, refreshHealth]);

  // Live SSE for library list updates ONLY on Command Hub (avoids HTTP/1.1 socket contention)
  useEffect(() => {
    if (location.pathname !== '/') return;
    const es = new EventSource('/api/studio/library/events');
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === 'library.change') {
          loadProjects();
        }
      } catch {
        // ignore
      }
    };
    const onUnload = () => es.close();
    window.addEventListener('beforeunload', onUnload);
    return () => {
      window.removeEventListener('beforeunload', onUnload);
      es.close();
    };
  }, [location.pathname, loadProjects]);

  // Keep active project state synced via SSE when viewing a project route
  useEffect(() => {
    if (!routeProjectId) return;
    loadProject(routeProjectId);
    const es = new EventSource(`/api/studio/project/${encodeURIComponent(routeProjectId)}/events`);
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === 'change') {
          loadProject(routeProjectId, true);
        }
      } catch {
        // ignore
      }
    };
    const onUnload = () => es.close();
    window.addEventListener('beforeunload', onUnload);
    return () => {
      window.removeEventListener('beforeunload', onUnload);
      es.close();
    };
  }, [routeProjectId, loadProject]);

  // Global 1-5 workspace jump shortcuts (when not typing in inputs)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.ctrlKey || e.metaKey || e.altKey) {
        return;
      }
      if (e.key === '1') navigate('/');
      else if (e.key === '2' && currentProjectId) navigate(`/project/${currentProjectId}/nle`);
      else if (e.key === '3' && currentProjectId) navigate(`/project/${currentProjectId}/board`);
      else if (e.key === '4' && currentProjectId) navigate(`/project/${currentProjectId}/qa`);
      else if (e.key === '5') navigate('/system');
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [currentProjectId, navigate]);

  const navItems = [
    { id: 'hub', label: 'Command Hub', path: '/', icon: Sparkles, enabled: true, kbd: '1' },
    {
      id: 'nle',
      label: 'NLE Studio',
      path: currentProjectId ? `/project/${currentProjectId}/nle` : '/',
      icon: Film,
      enabled: Boolean(currentProjectId),
      kbd: '2',
    },
    {
      id: 'board',
      label: 'Pipeline Board',
      path: currentProjectId ? `/project/${currentProjectId}/board` : '/',
      icon: Layers,
      enabled: Boolean(currentProjectId),
      kbd: '3',
    },
    {
      id: 'qa',
      label: 'QA & Export',
      path: currentProjectId ? `/project/${currentProjectId}/qa` : '/',
      icon: ShieldCheck,
      enabled: Boolean(currentProjectId),
      kbd: '4',
    },
    { id: 'system', label: 'System & Tools', path: '/system', icon: Cpu, enabled: true, kbd: '5' },
  ];

  const isNavActive = (id: string) => {
    if (id === 'hub') return location.pathname === '/';
    if (id === 'system') return location.pathname.startsWith('/system');
    if (id === 'nle') return location.pathname.endsWith('/nle');
    if (id === 'board') return location.pathname.endsWith('/board');
    if (id === 'qa') return location.pathname.endsWith('/qa');
    return false;
  };

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[var(--bg-canvas)] text-[var(--text-primary)]">
      {/* Top Broadcast Header */}
      <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3.5">
        {/* Brand + Active Project */}
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/" className="flex items-center gap-2 shrink-0 group">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--accent-amber)] text-zinc-950 shadow-sm">
              <Clapperboard className="h-4 w-4 stroke-[2.4]" />
            </div>
            <div className="leading-none">
              <div className="text-xs font-bold tracking-tight text-[var(--text-primary)]">
                AI VIDEO LAB
              </div>
              <div className="text-[9px] font-mono uppercase tracking-[0.16em] text-[var(--accent-amber)]">
                PRO STUDIO
              </div>
            </div>
          </Link>

          <div className="h-5 w-px bg-[var(--border-subtle)] hidden sm:block" />

          {/* Workspace Nav Tabs */}
          <nav aria-label="Studio Workspaces" className="flex items-center gap-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = isNavActive(item.id);
              return (
                <button
                  key={item.id}
                  type="button"
                  disabled={!item.enabled}
                  onClick={() => navigate(item.path)}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-all cursor-pointer disabled:opacity-35 disabled:pointer-events-none',
                    active
                      ? 'bg-[var(--bg-elevated)] text-[var(--text-primary)] shadow-xs border border-[var(--border-strong)]'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)] border border-transparent',
                  )}
                >
                  <Icon
                    className={cn(
                      'h-3.5 w-3.5',
                      active ? 'text-[var(--accent-amber)]' : 'text-[var(--text-muted)]',
                    )}
                  />
                  <span className="hidden md:inline">{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>

        {/* Right Telemetry + Controls */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Hardware / FCC Live Badges */}
          <div className="hidden xl:flex items-center gap-1.5">
            <Badge tone={health?.fcc_online ? 'pass' : 'warn'}>
              <StatusDot tone={health?.fcc_online ? 'pass' : 'warn'} />
              {health?.fcc_online ? 'FCC Online' : 'FCC Offline'}
            </Badge>
            <Badge tone={health?.nvenc_available ? 'cyan' : 'neutral'}>
              {health?.nvenc_available ? 'NVENC GPU' : 'CPU x264'}
            </Badge>
            {health?.face_detector && (
              <Badge tone="neutral" className="font-mono text-[10px]">
                {health.face_detector}
              </Badge>
            )}
          </div>

          {/* Command Palette Trigger */}
          <button
            type="button"
            onClick={() => setCommandPaletteOpen(true)}
            className="flex h-7 items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 text-[11px] text-[var(--text-muted)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)] transition-colors cursor-pointer"
          >
            <Search className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Search…</span>
            <kbd className="rounded border border-[var(--border-subtle)] bg-[var(--bg-panel)] px-1 font-mono text-[10px]">
              Ctrl K
            </kbd>
          </button>

          {/* Theme Toggle */}
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            title={theme === 'dark' ? 'Light Studio Theme' : 'Broadcast Obsidian Dark'}
            className="flex h-7 w-7 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors cursor-pointer"
          >
            {theme === 'dark' ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
          </button>

          {/* Supervisor Dock Toggle */}
          <button
            type="button"
            onClick={() => setDockOpen(!dockOpen)}
            aria-label={dockOpen ? 'Collapse Executive Producer Dock' : 'Expand Executive Producer Dock'}
            title={dockOpen ? 'Hide Executive Producer Dock' : 'Show Executive Producer Dock'}
            className={cn(
              'flex h-7 items-center gap-1.5 rounded-lg border px-2 text-[11px] font-medium transition-colors cursor-pointer',
              dockOpen
                ? 'border-[var(--accent-amber)]/40 bg-[var(--accent-amber-soft)] text-[var(--accent-amber)]'
                : 'border-[var(--border-subtle)] bg-[var(--bg-input)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
            )}
          >
            {dockOpen ? (
              <PanelRightClose className="h-3.5 w-3.5" />
            ) : (
              <PanelRightOpen className="h-3.5 w-3.5" />
            )}
            <span className="hidden lg:inline">Producer</span>
          </button>
        </div>
      </header>

      {/* Workspace Body + Collapsible Executive Producer Dock */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <main className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden">
          {children ?? <Outlet />}
        </main>
        {dockOpen && <ExecutiveProducerDock />}
      </div>

      <CommandPalette />
      <ToastViewport />
    </div>
  );
}
