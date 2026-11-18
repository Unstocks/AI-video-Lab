import { useEffect, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { HomeSidebar } from '@/components/home/HomeSidebar';
import { CommandPalette } from '@/components/shell/CommandPalette';
import { ExecutiveProducerDrawer } from '@/components/supervisor/ExecutiveProducerDrawer';
import { ToastViewport } from '@/components/ui/Primitives';
import { useProjectStore, useSystemStore } from '@/stores/useStudioStore';

export function HomeShell() {
  const { bootstrap, refreshHealth, setDockOpen, dockOpen } = useSystemStore();
  const { loadProjects } = useProjectStore();
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    void bootstrap();
    void loadProjects();
    const timer = window.setInterval(refreshHealth, 30000);
    return () => window.clearInterval(timer);
  }, [bootstrap, loadProjects, refreshHealth]);

  // Live SSE for Recents & Project Library (DRIFT-05 fixed with subscribe(None))
  useEffect(() => {
    const es = new EventSource('/api/studio/library/events');
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === 'library.change') {
          void loadProjects();
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
  }, [loadProjects]);

  // Ctrl+J toggles slide-over Executive Producer Drawer
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'j') {
        e.preventDefault();
        setDockOpen(!dockOpen);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [dockOpen, setDockOpen]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[var(--bg-home)] text-[var(--text-primary)]">
      <HomeSidebar collapsed={collapsed} onToggleCollapse={() => setCollapsed((v) => !v)} />
      <main className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden bg-[var(--bg-home)]">
        <Outlet />
      </main>
      <ExecutiveProducerDrawer />
      <CommandPalette />
      <ToastViewport />
    </div>
  );
}
