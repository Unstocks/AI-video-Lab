import { useEffect } from 'react';
import { Outlet, useParams } from 'react-router-dom';
import { EditorHeader } from '@/components/editor/EditorHeader';
import { CommandPalette } from '@/components/shell/CommandPalette';
import { ExecutiveProducerDrawer } from '@/components/supervisor/ExecutiveProducerDrawer';
import { ToastViewport } from '@/components/ui/Primitives';
import { useProjectStore, useSystemStore } from '@/stores/useStudioStore';
import { useEditorStore } from '@/stores/useEditorStore';

export function EditorShell() {
  const { projectId = 'demo' } = useParams();
  const { bootstrap, refreshHealth, dockOpen, setDockOpen } = useSystemStore();
  const { loadProjects, loadProject, boardState, activeClipId } = useProjectStore();
  const { hydrateForProject, hydratedProjectId, undo, redo } = useEditorStore();

  useEffect(() => {
    void bootstrap();
    void loadProjects();
    const timer = window.setInterval(refreshHealth, 30000);
    return () => window.clearInterval(timer);
  }, [bootstrap, loadProjects, refreshHealth]);

  // Load real project state + subscribe to live disk-bus SSE
  useEffect(() => {
    if (!projectId) return;
    void loadProject(projectId);
    if (projectId === 'demo') return;

    const es = new EventSource(`/api/studio/project/${encodeURIComponent(projectId)}/events`);
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === 'change') {
          void loadProject(projectId, true);
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
  }, [projectId, loadProject]);

  // Hydrate normalized editor store once per project switch (never resets when changing ToolRail tabs!)
  useEffect(() => {
    if (projectId === 'demo') {
      if (hydratedProjectId !== 'demo') {
        void hydrateForProject('demo', 'Book Reading Reflection — Hinglish Short');
      }
      return;
    }
    if (boardState && boardState.project_id === projectId && hydratedProjectId !== projectId) {
      void hydrateForProject(
        projectId,
        boardState.title || projectId,
        boardState.editor_draft,
        activeClipId,
      );
    }
  }, [activeClipId, boardState, hydrateForProject, hydratedProjectId, projectId]);

  // Global editor shortcuts: Ctrl+J (Producer Drawer), Ctrl+Z / Ctrl+Y (Undo/Redo)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'j') {
        e.preventDefault();
        setDockOpen(!dockOpen);
        return;
      }
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
        e.preventDefault();
        redo();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [dockOpen, redo, setDockOpen, undo]);

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-[var(--bg-canvas)] text-[var(--text-primary)]">
      <EditorHeader />
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <Outlet />
      </div>
      <ExecutiveProducerDrawer />
      <CommandPalette />
      <ToastViewport />
    </div>
  );
}
