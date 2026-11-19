import type {
  BoardState,
  BrandKitRecord,
  BundledFontInfo,
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
  SubtitlesApiResponse,
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

export function buildMediaUrl(projectId: string, relPath: string, mtime?: number | null): string {
  const clean = relPath.replace(/^\/+/, '');
  const base = `/media/${encodeURIComponent(projectId)}/${clean}`;
  return mtime ? `${base}?v=${Math.floor(mtime)}` : base;
}

export function buildThumbUrl(projectId: string, relPath: string, w = 480): string {
  const clean = relPath.replace(/^\/+/, '');
  return `/thumb/${encodeURIComponent(projectId)}/${clean}?w=${w}`;
}

export const studioApi = {
  // ── System & Catalogs ────────────────────────────────────────────────
  getHealth: () => requestJson<StudioHealth>('/api/studio/health'),
  getPresets: () => requestJson<SubtitlePreset[]>('/api/studio/presets'),
  getPipelines: () => requestJson<PipelineSummary[]>('/api/studio/pipelines'),
  getPlaybooks: () => requestJson<PlaybookSummary[]>('/api/studio/playbooks'),
  getMediaProfiles: () => requestJson<MediaProfile[]>('/api/studio/media-profiles'),
  getFonts: () => requestJson<BundledFontInfo[]>('/api/studio/fonts'),
  getTools: (refresh = false) =>
    requestJson<ToolRegistrySnapshot>(`/api/studio/tools${refresh ? '?refresh=true' : ''}`),
  getMusicLibrary: () => requestJson<MusicLibrarySnapshot>('/api/studio/music-library'),
  getConfig: () => requestJson<Record<string, unknown>>('/api/studio/config'),
  switchFccModel: (model: string) =>
    requestJson<Record<string, unknown>>('/api/studio/fcc/model', {
      method: 'POST',
      body: JSON.stringify({ model }),
    }),

  // ── Brand Kit / My Workspace (SQLite Persisted) ──────────────────────
  listBrandKit: (category?: string) =>
    requestJson<{ count: number; items: BrandKitRecord[] }>(
      `/api/studio/brand-kit${category && category !== 'all' ? `?category=${encodeURIComponent(category)}` : ''}`,
    ),
  addBrandKitItem: (payload: {
    category: BrandKitRecord['category'];
    name: string;
    payload: Record<string, unknown>;
  }) =>
    requestJson<BrandKitRecord>('/api/studio/brand-kit', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteBrandKitItem: (itemId: string) =>
    requestJson<{ ok: boolean; item_id: string }>(
      `/api/studio/brand-kit/${encodeURIComponent(itemId)}`,
      { method: 'DELETE' },
    ),

  // ── Filesystem & Binary Upload ───────────────────────────────────────
  browseFs: (path?: string) =>
    requestJson<FsBrowseResult>(
      `/api/studio/fs/browse${path ? `?path=${encodeURIComponent(path)}` : ''}`,
    ),
  uploadMediaFile: async (
    file: File,
  ): Promise<{ ok: boolean; path: string; filename: string; size_bytes: number }> => {
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

  // ── Projects, Drafts & Deep Inspection ───────────────────────────────
  listProjects: () => requestJson<ProjectSummary[]>('/api/studio/projects'),
  getProjectState: (projectId: string) =>
    requestJson<BoardState>(`/api/studio/project/${encodeURIComponent(projectId)}/state`),
  getEditorDraft: (projectId: string) =>
    requestJson<{
      project_id: string;
      title_override: string | null;
      draft: Record<string, unknown>;
      updated_at: string | null;
    }>(`/api/studio/project/${encodeURIComponent(projectId)}/editor-draft`),
  saveEditorDraft: (projectId: string, draft: Record<string, unknown>) =>
    requestJson<{ ok?: boolean; draft: Record<string, unknown>; updated_at: string }>(
      `/api/studio/project/${encodeURIComponent(projectId)}/editor-draft`,
      {
        method: 'PUT',
        body: JSON.stringify({ draft }),
      },
    ),
  saveCropDraft: (projectId: string, candidateId: string, overrides: CropOverridesMap) =>
    requestJson<{ project_id: string; candidate_id: string; overrides: CropOverridesMap }>(
      `/api/studio/project/${encodeURIComponent(projectId)}/crop-draft/${encodeURIComponent(candidateId)}`,
      {
        method: 'PUT',
        body: JSON.stringify({ overrides }),
      },
    ),
  updateProjectTitle: (projectId: string, title: string) =>
    requestJson<{ project_id: string; title_override: string }>(
      `/api/studio/project/${encodeURIComponent(projectId)}/title`,
      {
        method: 'PATCH',
        body: JSON.stringify({ title }),
      },
    ),
  getTranscript: (projectId: string, candidateId?: string) =>
    requestJson<TranscriptResponse>(
      `/api/studio/project/${encodeURIComponent(projectId)}/transcript${
        candidateId ? `?candidate_id=${encodeURIComponent(candidateId)}` : ''
      }`,
    ),
  getSubtitles: (projectId: string, candidateId = 'source', maxWords = 4) =>
    requestJson<SubtitlesApiResponse>(
      `/api/studio/project/${encodeURIComponent(projectId)}/subtitles/${encodeURIComponent(candidateId)}?max_words=${maxWords}`,
    ),
  generateSubtitles: (
    projectId: string,
    payload: { candidate_id?: string; language?: string; max_words?: number },
    signal?: AbortSignal,
  ) =>
    requestJson<SubtitlesApiResponse>(
      `/api/studio/project/${encodeURIComponent(projectId)}/subtitles/generate`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
        signal,
      },
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
      `/api/studio/project/${encodeURIComponent(projectId)}/waveform/${relPath.replace(/^\/+/, '')}?bins=${bins}`,
    ),
  getFilmstrip: (projectId: string, relPath: string, count = 14, w = 180) =>
    requestJson<FilmstripData>(
      `/api/studio/project/${encodeURIComponent(projectId)}/filmstrip/${relPath.replace(/^\/+/, '')}?count=${count}&w=${w}`,
    ),

  // ── Supervisor & Orchestration ───────────────────────────────────────
  listSessions: () => requestJson<SupervisorSession[]>('/api/studio/sessions'),
  getSession: (sessionId: string) =>
    requestJson<SupervisorSession>(`/api/studio/sessions/${encodeURIComponent(sessionId)}`),
  createSession: (payload: { title?: string; project_id?: string | null }) =>
    requestJson<SupervisorSession>('/api/studio/sessions', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  deleteSession: (sessionId: string) =>
    requestJson<{ ok: boolean; session_id: string }>(
      `/api/studio/sessions/${encodeURIComponent(sessionId)}`,
      { method: 'DELETE' },
    ),
  startJob: (payload: {
    source_input: string;
    project_id?: string;
    clip_count?: number;
    style_preset?: string;
    layout_mode?: string;
    enable_punch_in?: boolean;
  }) =>
    requestJson<SupervisorSession>('/api/studio/jobs', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  startProduction: (payload: {
    pipeline_type: string;
    brief_prompt?: string;
    project_id?: string;
    source_input?: string;
    reference_url?: string;
    style_playbook?: string;
    media_profile?: string;
    render_runtime?: string;
    composition_mode?: 'templated' | 'atelier';
    style_preset?: string;
    budget_usd?: number;
    clip_count?: number;
    layout_mode?: string;
    enable_punch_in?: boolean;
  }) =>
    requestJson<SupervisorSession>('/api/studio/productions', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  sendMessage: (sessionId: string, text: string, clientOpId?: string) =>
    requestJson<SupervisorSession>(
      `/api/studio/sessions/${encodeURIComponent(sessionId)}/message`,
      {
        method: 'POST',
        body: JSON.stringify({ text, client_op_id: clientOpId }),
      },
    ),
  sendGateDecision: (
    sessionId: string,
    payload: {
      stage: string;
      decision: 'approve' | 'revise' | 'reject';
      notes?: string;
      project_id?: string;
      render_runtime?: string;
      composition_mode?: 'templated' | 'atelier';
    },
  ) =>
    requestJson<SupervisorSession>(
      `/api/studio/sessions/${encodeURIComponent(sessionId)}/gate`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),
  sendToolAction: (
    sessionId: string,
    payload: { action: string; params?: Record<string, unknown>; project_id?: string },
  ) =>
    requestJson<SupervisorSession>(
      `/api/studio/sessions/${encodeURIComponent(sessionId)}/tool-action`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),
  approveClips: (
    sessionId: string,
    payload: {
      approved_ids: string[];
      rejected_ids?: string[];
      style_preset?: string;
      layout_mode?: string;
      enable_punch_in?: boolean;
      notes?: string;
      project_id?: string;
    },
  ) =>
    requestJson<SupervisorSession>(
      `/api/studio/sessions/${encodeURIComponent(sessionId)}/approve`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),
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
    requestJson<SupervisorSession>(
      `/api/studio/sessions/${encodeURIComponent(sessionId)}/reframe`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),
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
    requestJson<SupervisorSession>(
      `/api/studio/sessions/${encodeURIComponent(sessionId)}/recut`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),
  changeStylePreset: (
    sessionId: string,
    payload: {
      candidate_id: string;
      style_preset: string;
      project_id?: string;
      layout_mode?: string;
      corrections?: Record<string, string>;
      margin_v?: number;
      highlight_style?: string;
    },
  ) =>
    requestJson<SupervisorSession>(
      `/api/studio/sessions/${encodeURIComponent(sessionId)}/style`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),
  exportClips: (
    sessionId: string,
    payload: {
      clip_ids: string[];
      project_id?: string;
      target_resolution?: '1080p' | '1440p' | '2160p' | '4k';
      codec?: 'auto' | 'hevc' | 'h264';
      clarity_percent?: number;
      audio_bitrate?: string;
      normalize_audio?: boolean;
    },
  ) =>
    requestJson<SupervisorSession>(
      `/api/studio/sessions/${encodeURIComponent(sessionId)}/export`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),
  stopSession: (sessionId: string) =>
    requestJson<SupervisorSession>(
      `/api/studio/sessions/${encodeURIComponent(sessionId)}/stop`,
      { method: 'POST' },
    ),
};
