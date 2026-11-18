import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from '@/components/shell/AppShell';
import { CommandHubWorkspace } from '@/workspaces/CommandHubWorkspace';
import { NleStudioWorkspace } from '@/workspaces/NleStudioWorkspace';
import { PipelineBoardWorkspace } from '@/workspaces/PipelineBoardWorkspace';
import { BroadcastQaWorkspace } from '@/workspaces/BroadcastQaWorkspace';
import { SystemCapabilitiesWorkspace } from '@/workspaces/SystemCapabilitiesWorkspace';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<CommandHubWorkspace />} />
          <Route path="/project/:projectId/nle" element={<NleStudioWorkspace />} />
          <Route path="/project/:projectId/board" element={<PipelineBoardWorkspace />} />
          <Route path="/project/:projectId/qa" element={<BroadcastQaWorkspace />} />
          <Route path="/system" element={<SystemCapabilitiesWorkspace />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
