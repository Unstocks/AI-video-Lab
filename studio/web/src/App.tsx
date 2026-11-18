import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { HomeShell } from '@/shells/HomeShell';
import { EditorShell } from '@/shells/EditorShell';
import { HomePage } from '@/pages/HomePage';
import { EditorPage } from '@/pages/EditorPage';
import { PipelineBoardWorkspace } from '@/workspaces/PipelineBoardWorkspace';
import { BroadcastQaWorkspace } from '@/workspaces/BroadcastQaWorkspace';
import { SystemCapabilitiesWorkspace } from '@/workspaces/SystemCapabilitiesWorkspace';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Shell 1: Home / Create Shell (280px Sidebar + 1280px Create Canvas) */}
        <Route element={<HomeShell />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/system" element={<SystemCapabilitiesWorkspace />} />
        </Route>

        {/* Shell 2: Full-Screen Creator Video Editor + Pipeline Board + Broadcast QA */}
        <Route element={<EditorShell />}>
          <Route path="/editor/:projectId" element={<EditorPage />} />
          <Route path="/editor/:projectId/board" element={<PipelineBoardWorkspace />} />
          <Route path="/editor/:projectId/qa" element={<BroadcastQaWorkspace />} />
          {/* Backwards-compatible aliases */}
          <Route path="/project/:projectId/nle" element={<EditorPage />} />
          <Route path="/project/:projectId/board" element={<PipelineBoardWorkspace />} />
          <Route path="/project/:projectId/qa" element={<BroadcastQaWorkspace />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
