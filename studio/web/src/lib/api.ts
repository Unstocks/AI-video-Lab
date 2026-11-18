import type {
  BoardState,
  CropOverridesMap,
  FilmstripData,
  FsBrowseResult,
  MediaProfile,
  MusicLibrarySnapshot,
  PipelineSummary,
  PlaybookSummary,
  ProjectFileItem,
  ProjectSummary,
  StudioHealth,
  SubtitlePreset,
  SupervisorSession,
  ToolRegistrySnapshot,
  TranscriptResponse,
  WaveformData,
} from '@/types/studio';

function getStudioToken(): string {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="studio-token"]');
  const val = meta?.content?.trim() ?? '';
  if (!val || val === '__STUDIO_TOKEN__') {
    return (window as unknown as { __STUDIO_TOKEN__?: string }).__STUDIO_TOKEN__ ?? '';
  }
  return val;
}

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail || `HTTP ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || 'GET').toUpperCase();
  const headers = new Headers(init?.headers || {});
  if (method !== 'GET' && method !== 'HEAD') {
    const token = getStudioToken();
    if (token) headers.set('X-Studio-Token', token);
    if (!headers.has('Content-Type') && typeof init?.body === 'string') {
      headers.set('Content-Type', 'application/json');
    }
  }
  const resp = await fetch(url, { ...init, headers });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const errBody = await resp.json();
      detail = typeof errBody?.detail === 'string' ? errBody.detail : JSON.stringify(errBody);
    } catch {
      try {
        detail = await resp.text();
      } catch {
        // ignore
      }
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

export const studioApi = {
  // ── System & Catalogs ────────────────────────────────────────────────
  getHealth: () => requestJson<StudioHealth>('/api/studio/health'),
  getPresets: () => requestJson<SubtitlePreset[]>('/api/studio/presets'),
  getPipelines: () => requestJson<PipelineSummary[]>('/api/studio/pipelines'),
  getPlaybooks: () => requestJson<PlaybookSummary[]>('/api/studio/playbooks'),
  getMediaProfiles: () => requestJson<MediaProfile[]>('/api/studio/media-profiles'),
  getTools: (refresh = false) =>
    requestJson<ToolRegistrySnapshot>(`/api/studio/tools${refresh ? '?refresh=true' : ''}`),
  getMusicLibrary: () => requestJson<MusicLibrarySnapshot>('/api/studio/music-library'),
  getConfig: () => requestJson<Record<string, unknown>>('/api/studio/config'),
  switchFccModel: (model: string) =>
    requestJson<Record<string, unknown>>('/api/studio/fcc/model', {
      method: 'POST',
      body: JSON.stringify({ model }),
    }),

  // ── Filesystem & Binary Upload ───────────────────────────────────────
  browseFs: (path?: string) =>
    requestJson<FsBrowseResult>(
      `/api/studio/fs/browse${path ? `?path=${encodeURIComponent(path)}` : ''}`,
    ),
  uploadMediaFile: async (file: File): Promise<{ ok: boolean; path: string; filename: string; size_bytes: number }> => {
    const token = getStudioToken();
    const resp = await fetch(`/api/studio/upload?filename=${encodeURIComponent(file.name)}`, {
      method: 'POST',
      headers: {
        'X-Studio-Token': token,
        'Content-Type': 'application/octet-stream',
      },
      body: file,
    });
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const j = await resp.json();
        detail = j?.detail || detail;
      } catch {
        // ignore
      }
      throw new ApiError(resp.status, detail);
    }
    return resp.json();
  },

  // ── Projects & Deep Inspection ───────────────────────────────────────
  listProjects: () => requestJson<ProjectSummary[]>('/api/studio/projects'),
  getProjectState: (projectId: string) =>
    requestJson<BoardState>(`/api/studio/project/${encodeURIComponent(projectId)}/state`),
  getTranscript: (projectId: string, candidateId?: string) =>
    requestJson<TranscriptResponse>(
      `/api/studio/project/${encodeURIComponent(projectId)}/transcript${
        candidateId ? `?candidate_id=${encodeURIComponent(candidateId)}` : ''
      }`,
    ),
  getArtifact: (projectId: string, artifactName: string) =>
    requestJson<{ name: string; source: string; data: unknown }>(
      `/api/studio/project/${encodeURIComponent(projectId)}/artifacts/${encodeURIComponent(artifactName)}`,
    ),
  getHistory: (projectId: string) =>
    requestJson<{ project_id: string; stages: Record<string, Array<Record<string, unknown>>> }>(
      `/api/studio/project/${encodeURIComponent(projectId)}/history`,
    ),
  getProjectFiles: (projectId: string) =>
    requestJson<{ project_id: string; count: number; files: ProjectFileItem[] }>(
      `/api/studio/project/${encodeURIComponent(projectId)}/files`,
    ),
  getWaveform: (projectId: string, relPath: string, bins = 400) =>
    requestJson<WaveformData>(
      `/api/studio/project/${encodeURIComponent(projectId)}/waveform/${relPath
        .split('/')
        .map(encodeURIComponent)
        .join('/')}?bins=${bins}`,
    ),
  getFilmstrip: (projectId: string, relPath: string, count = 14, width = 180) =>
    requestJson<FilmstripData>(
      `/api/studio/project/${encodeURIComponent(projectId)}/filmstrip/${relPath
        .split('/')
        .map(encodeURIComponent)
        .join('/')}?count=${count}&w=${width}`,
    ),

  // ── Top Supervisor Sessions & Directives ─────────────────────────────
  listSessions: () => requestJson<SupervisorSession[]>('/api/studio/sessions'),
  getSession: (sessionId: string) =>
    requestJson<SupervisorSession>(`/api/studio/sessions/${encodeURIComponent(sessionId)}`),
  createSession: (payload: { title?: string; project_id?: string | null }) =>
    requestJson<SupervisorSession>('/api/studio/sessions', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteSession: (sessionId: string) =>
    requestJson<{ ok: boolean }>(`/api/studio/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE',
    }),
  startProduction: (payload: {
    pipeline_type: string;
    brief_prompt?: string;
    project_id?: string | null;
    source_input?: string | null;
    reference_url?: string | null;
    style_playbook?: string | null;
    media_profile?: string | null;
    render_runtime?: string | null;
    style_preset?: string | null;
    budget_usd?: number | null;
    clip_count?: number;
    layout_mode?: string;
    enable_punch_in?: boolean;
  }) =>
    requestJson<SupervisorSession>('/api/studio/productions', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  sendMessage: (sessionId: string, text: string, clientOpId?: string) =>
    requestJson<SupervisorSession>(`/api/studio/sessions/${encodeURIComponent(sessionId)}/message`, {
      method: 'POST',
      body: JSON.stringify({ text, client_op_id: clientOpId }),
    }),
  sendGateDecision: (
    sessionId: string,
    payload: { stage: string; decision: 'approve' | 'revise' | 'reject'; notes?: string; project_id?: string },
  ) =>
    requestJson<SupervisorSession>(`/api/studio/sessions/${encodeURIComponent(sessionId)}/gate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  approveClips: (
    sessionId: string,
    payload: {
      approved_ids: string[];
      rejected_ids: string[];
      style_preset?: string;
      layout_mode?: string;
      enable_punch_in?: boolean;
      notes?: string;
      project_id?: string;
    },
  ) =>
    requestJson<SupervisorSession>(`/api/studio/sessions/${encodeURIComponent(sessionId)}/approve`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  reframeClip: (
    sessionId: string,
    payload: {
      candidate_id: string;
      crop_overrides: CropOverridesMap;
      project_id?: string;
      style_preset?: string;
      enable_punch_in?: boolean;
    },
  ) =>
    requestJson<SupervisorSession>(`/api/studio/sessions/${encodeURIComponent(sessionId)}/reframe`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  recutClip: (
    sessionId: string,
    payload: {
      candidate_id: string;
      start_seconds: number;
      end_seconds: number;
      project_id?: string;
      style_preset?: string;
      layout_mode?: string;
    },
  ) =>
    requestJson<SupervisorSession>(`/api/studio/sessions/${encodeURIComponent(sessionId)}/recut`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  changeStylePreset: (
    sessionId: string,
    payload: { candidate_id: string; style_preset: string; project_id?: string; layout_mode?: string },
  ) =>
    requestJson<SupervisorSession>(`/api/studio/sessions/${encodeURIComponent(sessionId)}/style`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  exportClips: (sessionId: string, payload: { clip_ids: string[]; project_id?: string }) =>
    requestJson<SupervisorSession>(`/api/studio/sessions/${encodeURIComponent(sessionId)}/export`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  stopSession: (sessionId: string) =>
    requestJson<SupervisorSession>(`/api/studio/sessions/${encodeURIComponent(sessionId)}/stop`, {
      method: 'POST',
    }),
};
