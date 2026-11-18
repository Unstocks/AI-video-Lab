import { create } from 'zustand';
import { studioApi } from '@/lib/api';
import type {
  BoardState,
  BundledFontInfo,
  CropOverrideEntry,
  CropOverridesMap,
  FilmstripData,
  MediaProfile,
  MusicLibrarySnapshot,
  PipelineSummary,
  PlaybookSummary,
  ProjectSummary,
  StudioHealth,
  SubtitlePreset,
  SupervisorMessage,
  SupervisorSession,
  ToolRegistrySnapshot,
  TranscriptResponse,
  WaveformData,
} from '@/types/studio';

// ── Zero-rerender 60fps Playback Pub/Sub (With Script Cut-Range Skip) ───
type PlaybackListener = (time: number, duration: number, playing: boolean) => void;

class PlaybackHub {
  currentTime = 0;
  duration = 0;
  playing = false;
  private listeners = new Set<PlaybackListener>();
  private seekHandlers = new Set<(time: number) => void>();

  emit(time: number, duration: number, playing: boolean) {
    this.currentTime = time;
    this.duration = duration;
    this.playing = playing;
    this.listeners.forEach((fn) => fn(time, duration, playing));
  }

  subscribe(fn: PlaybackListener): () => void {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  }

  onSeekRequest(fn: (time: number) => void): () => void {
    this.seekHandlers.add(fn);
    return () => {
      this.seekHandlers.delete(fn);
    };
  }

  requestSeek(time: number) {
    const clamped = Math.max(0, this.duration > 0 ? Math.min(this.duration, time) : time);
    this.currentTime = clamped;
    this.seekHandlers.forEach((fn) => fn(clamped));
    this.listeners.forEach((fn) => fn(clamped, this.duration, this.playing));
  }
}

export const playbackHub = new PlaybackHub();

// ── Toast Store ─────────────────────────────────────────────────────────
export interface ToastItem {
  id: string;
  title: string;
  detail?: string;
  tone: 'info' | 'success' | 'warn' | 'error';
}

interface ToastState {
  items: ToastItem[];
  push: (item: Omit<ToastItem, 'id'>) => void;
  dismiss: (id: string) => void;
}

export const useToastStore = create<ToastState>((set) => ({
  items: [],
  push: (item) => {
    const id = `t_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    set((s) => ({ items: [...s.items.slice(-4), { ...item, id }] }));
    window.setTimeout(() => {
      set((s) => ({ items: s.items.filter((x) => x.id !== id) }));
    }, 4200);
  },
  dismiss: (id) => set((s) => ({ items: s.items.filter((x) => x.id !== id) })),
}));

export const toast = {
  info: (title: string, detail?: string) => useToastStore.getState().push({ title, detail, tone: 'info' }),
  success: (title: string, detail?: string) => useToastStore.getState().push({ title, detail, tone: 'success' }),
  warn: (title: string, detail?: string) => useToastStore.getState().push({ title, detail, tone: 'warn' }),
  error: (title: string, detail?: string) => useToastStore.getState().push({ title, detail, tone: 'error' }),
};

// ── 1. System & Catalog Store ───────────────────────────────────────────
interface SystemState {
  health: StudioHealth | null;
  pipelines: PipelineSummary[];
  playbooks: PlaybookSummary[];
  mediaProfiles: MediaProfile[];
  presets: SubtitlePreset[];
  bundledFonts: BundledFontInfo[];
  tools: ToolRegistrySnapshot | null;
  musicLibrary: MusicLibrarySnapshot | null;
  config: Record<string, unknown>;
  bootstrapped: boolean;
  toolsLoading: boolean;
  theme: 'light' | 'dark';
  commandPaletteOpen: boolean;
  /** Slide-over Executive Producer drawer (default closed for full-width creator canvas) */
  dockOpen: boolean;
  dockWidth: number;
  bootstrap: () => Promise<void>;
  refreshHealth: () => Promise<void>;
  loadTools: (forceRefresh?: boolean) => Promise<void>;
  loadMusicLibrary: () => Promise<void>;
  setTheme: (theme: 'light' | 'dark') => void;
  toggleTheme: () => void;
  setCommandPaletteOpen: (open: boolean) => void;
  setDockOpen: (open: boolean) => void;
  setDockWidth: (width: number) => void;
}

function getInitialTheme(): 'light' | 'dark' {
  try {
    const saved = localStorage.getItem('studio.theme.v2');
    if (saved === 'light' || saved === 'dark') return saved;
  } catch {
    // ignore
  }
  return 'light'; // User-locked default: Creator Crisp Light
}

export const useSystemStore = create<SystemState>((set, get) => ({
  health: null,
  pipelines: [],
  playbooks: [],
  mediaProfiles: [],
  presets: [],
  bundledFonts: [],
  tools: null,
  musicLibrary: null,
  config: {},
  bootstrapped: false,
  toolsLoading: false,
  theme: getInitialTheme(),
  commandPaletteOpen: false,
  dockOpen: false,
  dockWidth: 400,

  bootstrap: async () => {
    if (get().bootstrapped) return;
    set({ bootstrapped: true });
    const theme = get().theme;
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.classList.toggle('dark', theme === 'dark');

    // Run hardware/FCC probe independently so fast catalogs commit in <15ms
    void get().refreshHealth();

    const [pipelines, playbooks, mediaProfiles, presets, config, fonts] = await Promise.allSettled([
      studioApi.getPipelines(),
      studioApi.getPlaybooks(),
      studioApi.getMediaProfiles(),
      studioApi.getPresets(),
      studioApi.getConfig(),
      studioApi.getFonts(),
    ]);

    set({
      pipelines: pipelines.status === 'fulfilled' ? pipelines.value : [],
      playbooks: playbooks.status === 'fulfilled' ? playbooks.value : [],
      mediaProfiles: mediaProfiles.status === 'fulfilled' ? mediaProfiles.value : [],
      presets: presets.status === 'fulfilled' ? presets.value : [],
      config: config.status === 'fulfilled' ? config.value : {},
      bundledFonts: fonts.status === 'fulfilled' ? fonts.value : [],
    });
  },

  refreshHealth: async () => {
    try {
      const health = await studioApi.getHealth();
      set({ health });
    } catch {
      // ignore transient probe errors
    }
  },

  loadTools: async (forceRefresh = false) => {
    if (get().tools && !forceRefresh) return;
    set({ toolsLoading: true });
    try {
      const tools = await studioApi.getTools(forceRefresh);
      set({ tools, toolsLoading: false });
    } catch (e) {
      set({ toolsLoading: false });
      toast.error('Failed to load tool registry', String(e));
    }
  },

  loadMusicLibrary: async () => {
    try {
      const musicLibrary = await studioApi.getMusicLibrary();
      set({ musicLibrary });
    } catch {
      // ignore
    }
  },

  setTheme: (theme) => {
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.classList.toggle('dark', theme === 'dark');
    try {
      localStorage.setItem('studio.theme.v2', theme);
    } catch {
      // ignore
    }
    set({ theme });
  },

  toggleTheme: () => {
    const next = get().theme === 'dark' ? 'light' : 'dark';
    get().setTheme(next);
  },

  setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
  setDockOpen: (open) => set({ dockOpen: open }),
  setDockWidth: (width) => set({ dockWidth: Math.max(320, Math.min(580, Math.round(width))) }),
}));

// ── 2. Project & Disk-Bus State Store ───────────────────────────────────
interface ProjectState {
  projects: ProjectSummary[];
  projectsLoading: boolean;
  activeProjectId: string | null;
  boardState: BoardState | null;
  boardLoading: boolean;
  boardError: string | null;
  activeClipId: string | null;
  transcript: TranscriptResponse | null;
  waveforms: Record<string, WaveformData>;
  filmstrips: Record<string, FilmstripData>;
  loadProjects: () => Promise<void>;
  loadProject: (projectId: string, silent?: boolean) => Promise<void>;
  setActiveClipId: (clipId: string | null) => void;
  loadTranscript: (projectId: string, candidateId?: string) => Promise<void>;
  ensureWaveform: (projectId: string, relPath: string) => Promise<void>;
  ensureFilmstrip: (projectId: string, relPath: string) => Promise<void>;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  projectsLoading: false,
  activeProjectId: null,
  boardState: null,
  boardLoading: false,
  boardError: null,
  activeClipId: null,
  transcript: null,
  waveforms: {},
  filmstrips: {},

  loadProjects: async () => {
    set({ projectsLoading: true });
    try {
      const projects = await studioApi.listProjects();
      set({ projects, projectsLoading: false });
    } catch (e) {
      set({ projectsLoading: false });
      toast.error('Failed to load projects', String(e));
    }
  },

  loadProject: async (projectId, silent = false) => {
    if (projectId === 'demo') {
      set({ activeProjectId: 'demo', boardState: null, boardLoading: false, boardError: null });
      return;
    }
    if (!silent) {
      set({ activeProjectId: projectId, boardLoading: true, boardError: null });
    }
    try {
      const boardState = await studioApi.getProjectState(projectId);
      const clips = boardState.clip_studio?.clips ?? [];
      const prevClip = get().activeClipId;
      const validPrev = prevClip && clips.some((c) => c.candidate_id === prevClip);
      const nextClipId = validPrev ? prevClip : clips[0]?.candidate_id ?? null;

      set({
        activeProjectId: projectId,
        boardState,
        boardLoading: false,
        boardError: null,
        activeClipId: nextClipId,
      });

      if (!silent && boardState.crop_drafts) {
        useNleStore.getState().hydrateDrafts(boardState.crop_drafts);
      }
    } catch (e) {
      set({ boardLoading: false, boardError: String(e) });
    }
  },

  setActiveClipId: (clipId) => set({ activeClipId: clipId }),

  loadTranscript: async (projectId, candidateId) => {
    if (projectId === 'demo') return;
    try {
      const transcript = await studioApi.getTranscript(projectId, candidateId);
      set({ transcript });
    } catch {
      set({ transcript: null });
    }
  },

  ensureWaveform: async (projectId, relPath) => {
    const key = `${projectId}:${relPath}`;
    if (get().waveforms[key]) return;
    try {
      const data = await studioApi.getWaveform(projectId, relPath, 320);
      set((s) => ({ waveforms: { ...s.waveforms, [key]: data } }));
    } catch {
      // ignore
    }
  },

  ensureFilmstrip: async (projectId, relPath) => {
    const key = `${projectId}:${relPath}`;
    if (get().filmstrips[key]) return;
    try {
      const data = await studioApi.getFilmstrip(projectId, relPath, 14, 180);
      set((s) => ({ filmstrips: { ...s.filmstrips, [key]: data } }));
    } catch {
      // ignore
    }
  },
}));

// ── 3. Reframe v2 Crop Draft Store (Exact lib/reframe_v2.py Contract) ───
interface NleState {
  selectedRangeIdx: number;
  timelineZoom: number;
  showSafeZones: boolean;
  /** Per-clip exact reframe_v2 crop_overrides maps */
  drafts: Record<string, CropOverridesMap>;
  past: Array<Record<string, CropOverridesMap>>;
  future: Array<Record<string, CropOverridesMap>>;
  recutStart: number | null;
  recutEnd: number | null;
  setSelectedRangeIdx: (idx: number) => void;
  setTimelineZoom: (z: number) => void;
  setShowSafeZones: (val: boolean) => void;
  hydrateDrafts: (drafts: Record<string, CropOverridesMap>) => void;
  updateRangeOverride: (clipId: string, rangeKey: string, entry: CropOverrideEntry) => void;
  undoCrop: () => void;
  redoCrop: () => void;
  setRecutBounds: (start: number | null, end: number | null) => void;
}

export const useNleStore = create<NleState>((set, get) => ({
  selectedRangeIdx: 0,
  timelineZoom: 1,
  showSafeZones: false,
  drafts: {},
  past: [],
  future: [],
  recutStart: null,
  recutEnd: null,

  setSelectedRangeIdx: (selectedRangeIdx) => set({ selectedRangeIdx }),
  setTimelineZoom: (z) => set({ timelineZoom: Math.max(1, Math.min(8, z)) }),
  setShowSafeZones: (showSafeZones) => set({ showSafeZones }),
  hydrateDrafts: (drafts) => set({ drafts, past: [], future: [] }),

  updateRangeOverride: (clipId, rangeKey, entry) => {
    const prev = get().drafts;
    const nextClipMap: CropOverridesMap = {
      ...(prev[clipId] || {}),
      [rangeKey]: entry,
    };
    const next = { ...prev, [clipId]: nextClipMap };
    set((s) => ({
      drafts: next,
      past: [...s.past.slice(-24), prev],
      future: [],
    }));
  },

  undoCrop: () => {
    const { past, drafts, future } = get();
    if (!past.length) return;
    const prev = past[past.length - 1];
    set({
      drafts: prev,
      past: past.slice(0, -1),
      future: [drafts, ...future.slice(0, 24)],
    });
  },

  redoCrop: () => {
    const { past, drafts, future } = get();
    if (!future.length) return;
    const next = future[0];
    set({
      drafts: next,
      past: [...past.slice(-24), drafts],
      future: future.slice(1),
    });
  },

  setRecutBounds: (recutStart, recutEnd) => set({ recutStart, recutEnd }),
}));

// ── 4. Top-Supervisor (fcc-claude) Session Store ────────────────────────
interface SupervisorState {
  sessions: SupervisorSession[];
  activeSessionId: string | null;
  messages: SupervisorMessage[];
  running: boolean;
  sending: boolean;
  loadSessions: () => Promise<void>;
  selectSession: (sessionId: string) => Promise<void>;
  ensureSessionForProject: (projectId?: string | null, title?: string) => Promise<string>;
  appendMessage: (msg: SupervisorMessage) => void;
  setRunning: (running: boolean) => void;
  sendMessage: (text: string, projectId?: string | null) => Promise<void>;
  stopActiveRun: () => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
}

export const useSupervisorStore = create<SupervisorState>((set, get) => ({
  sessions: [],
  activeSessionId: null,
  messages: [],
  running: false,
  sending: false,

  loadSessions: async () => {
    try {
      const sessions = await studioApi.listSessions();
      set({ sessions });
      if (!get().activeSessionId && sessions.length > 0) {
        await get().selectSession(sessions[0].session_id);
      }
    } catch {
      // ignore
    }
  },

  selectSession: async (sessionId) => {
    set({ activeSessionId: sessionId });
    try {
      const detail = await studioApi.getSession(sessionId);
      set({
        activeSessionId: sessionId,
        messages: detail.messages ?? [],
        running: Boolean(detail.running || detail.status === 'running'),
      });
    } catch (e) {
      toast.error('Could not load session', String(e));
    }
  },

  ensureSessionForProject: async (projectId, title) => {
    const { sessions, activeSessionId } = get();
    if (projectId && projectId !== 'demo') {
      const match = sessions.find((s) => s.project_id === projectId);
      if (match) {
        if (activeSessionId !== match.session_id) {
          await get().selectSession(match.session_id);
        }
        return match.session_id;
      }
    }
    if (activeSessionId && (!projectId || projectId === 'demo')) return activeSessionId;

    const created = await studioApi.createSession({
      project_id: projectId && projectId !== 'demo' ? projectId : null,
      title: title || (projectId && projectId !== 'demo' ? `Director · ${projectId}` : 'Executive Producer'),
    });
    set((s) => ({
      sessions: [created, ...s.sessions],
      activeSessionId: created.session_id,
      messages: [],
      running: false,
    }));
    return created.session_id;
  },

  appendMessage: (msg) => {
    set((s) => {
      if (s.messages.some((m) => m.id === msg.id)) return s;
      return { messages: [...s.messages, msg] };
    });
  },

  setRunning: (running) => set({ running }),

  sendMessage: async (text, projectId) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    set({ sending: true });
    try {
      const sid = await get().ensureSessionForProject(projectId);
      await studioApi.sendMessage(sid, trimmed, `op_${Date.now()}`);
      set({ running: true, sending: false });
      await get().loadSessions();
    } catch (e) {
      set({ sending: false });
      toast.error('Supervisor directive failed', String(e));
    }
  },

  stopActiveRun: async () => {
    const sid = get().activeSessionId;
    if (!sid) return;
    try {
      await studioApi.stopSession(sid);
      set({ running: false });
      toast.warn('Supervisor stopped', 'Subprocess tree terminated cleanly.');
    } catch (e) {
      toast.error('Failed to stop supervisor', String(e));
    }
  },

  deleteSession: async (sessionId) => {
    try {
      await studioApi.deleteSession(sessionId);
      const remaining = get().sessions.filter((s) => s.session_id !== sessionId);
      const wasActive = get().activeSessionId === sessionId;
      set({
        sessions: remaining,
        activeSessionId: wasActive ? remaining[0]?.session_id ?? null : get().activeSessionId,
        messages: wasActive ? [] : get().messages,
      });
      if (wasActive && remaining[0]) {
        await get().selectSession(remaining[0].session_id);
      }
    } catch (e) {
      toast.error('Could not delete session', String(e));
    }
  },
}));
