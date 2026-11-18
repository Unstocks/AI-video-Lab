import { create } from 'zustand';
import { studioApi } from '@/lib/api';
import { DEMO_CAPTIONS, DEMO_DURATION, DEMO_PROJECT_ID, DEMO_PROJECT_TITLE } from '@/data/demoProjectSeed';
import { playbackHub, toast } from '@/stores/useStudioStore';
import type {
  AiToolsSettings,
  AspectRatioId,
  CanvasSelection,
  CaptionCue,
  CutRange,
  EditorUndoableState,
  StageViewMode,
  SubtitleBoxTransform,
  SubtitleEditorTab,
  SubtitlePanelState,
  SubtitleStyleGroup,
  TextOverlayItem,
  ToolId,
} from '@/types/editor';

const DEFAULT_SUBTITLE_BOX: SubtitleBoxTransform = {
  x: 0.5,
  y: 0.81,
  width: 0.86,
  rotation: 0,
  fontScale: 1,
};

const DEFAULT_AI_TOOLS: AiToolsSettings = {
  layoutMode: 'auto',
  enablePunchIn: true,
  magicSilenceCut: false,
  broadcastLoudnorm: true,
  voiceDenoise: false,
  seamSubtitles: true,
  eyeContactAssist: false,
};

function snapshotUndoable(s: EditorStoreState): EditorUndoableState {
  return {
    captions: s.captions.map((c) => ({ ...c })),
    textOverlays: s.textOverlays.map((t) => ({ ...t })),
    cutRanges: s.cutRanges.map((r) => ({ ...r })),
    subtitleBox: { ...s.subtitleBox },
    activeSubtitlePreset: s.activeSubtitlePreset,
    aspectRatio: s.aspectRatio,
    canvasBg: s.canvasBg,
    corrections: { ...s.corrections },
  };
}

interface EditorStoreState extends EditorUndoableState {
  hydratedProjectId: string | null;
  projectTitle: string;
  activeTool: ToolId;
  stageViewMode: StageViewMode;
  showSubtitles: boolean;
  subtitlePanelState: SubtitlePanelState;
  subtitleTab: SubtitleEditorTab;
  subtitleStyleGroup: SubtitleStyleGroup | null;
  subtitleLanguage: string;
  subtitleEvidenceQuality: string;
  selection: CanvasSelection;
  activeCaptionId: string | null;
  aiTools: AiToolsSettings;
  scriptTipDismissed: boolean;
  dirtyDraft: boolean;
  past: EditorUndoableState[];
  future: EditorUndoableState[];

  // Actions
  hydrateForProject: (
    projectId: string,
    title: string,
    savedDraft?: Record<string, unknown>,
    candidateId?: string | null,
  ) => Promise<void>;
  setProjectTitle: (title: string) => void;
  setActiveTool: (tool: ToolId) => void;
  setStageViewMode: (mode: StageViewMode) => void;
  setShowSubtitles: (show: boolean) => void;
  setSubtitlePanelState: (state: SubtitlePanelState) => void;
  setSubtitleTab: (tab: SubtitleEditorTab) => void;
  setSubtitleStyleGroup: (group: SubtitleStyleGroup | null) => void;
  setSubtitleLanguage: (lang: string) => void;
  setSelection: (sel: CanvasSelection) => void;
  setActiveCaptionId: (id: string | null) => void;
  setActiveSubtitlePreset: (preset: string) => void;
  setAspectRatio: (ratio: AspectRatioId) => void;
  setCanvasBg: (hex: string) => void;
  updateAiTools: (patch: Partial<AiToolsSettings>) => void;
  dismissScriptTip: () => void;

  // Subtitle CRUD (Undoable)
  setCaptions: (captions: CaptionCue[], evidenceQuality?: string) => void;
  updateCaptionText: (id: string, text: string) => void;
  updateCaptionTiming: (id: string, start: number, end: number) => void;
  duplicateCaption: (id: string) => void;
  deleteCaption: (id: string) => void;
  splitCaptionAtTime: (time: number) => void;
  addCaptionAtTime: (time: number, maxDuration: number) => void;
  updateSubtitleBox: (patch: Partial<SubtitleBoxTransform>, commitHistory?: boolean) => void;

  // Text Overlay CRUD (Undoable)
  addTextOverlay: (item: TextOverlayItem) => void;
  updateTextOverlay: (id: string, patch: Partial<TextOverlayItem>, commitHistory?: boolean) => void;
  deleteTextOverlay: (id: string) => void;

  // Script Doc-Cut CRUD (Undoable)
  addCutRange: (range: Omit<CutRange, 'id'>) => void;
  removeCutRange: (id: string) => void;

  // History & Draft Persistence
  undo: () => void;
  redo: () => void;
  persistDraft: (projectId: string) => Promise<void>;
}

function pushHistory(s: EditorStoreState) {
  return {
    past: [...s.past.slice(-30), snapshotUndoable(s)],
    future: [] as EditorUndoableState[],
    dirtyDraft: true,
  };
}

export const useEditorStore = create<EditorStoreState>((set, get) => ({
  hydratedProjectId: null,
  projectTitle: DEMO_PROJECT_TITLE,
  activeTool: 'subtitles',
  stageViewMode: 'preview',
  showSubtitles: true,
  subtitlePanelState: 'setup',
  subtitleTab: 'edit',
  subtitleStyleGroup: null,
  subtitleLanguage: 'US English',
  subtitleEvidenceQuality: 'medium_word',
  selection: null,
  activeCaptionId: null,
  captions: [],
  textOverlays: [],
  cutRanges: [],
  subtitleBox: { ...DEFAULT_SUBTITLE_BOX },
  activeSubtitlePreset: 'hinglish_impact',
  aspectRatio: '9:16',
  canvasBg: '#0b0d11',
  corrections: {},
  aiTools: { ...DEFAULT_AI_TOOLS },
  scriptTipDismissed: false,
  dirtyDraft: false,
  past: [],
  future: [],

  hydrateForProject: async (projectId, title, savedDraft, candidateId) => {
    if (projectId === DEMO_PROJECT_ID) {
      set({
        hydratedProjectId: DEMO_PROJECT_ID,
        projectTitle: DEMO_PROJECT_TITLE,
        captions: DEMO_CAPTIONS.map((c) => ({ ...c })),
        textOverlays: [],
        cutRanges: [],
        subtitleBox: { ...DEFAULT_SUBTITLE_BOX },
        activeSubtitlePreset: 'hinglish_impact',
        subtitlePanelState: 'editor',
        subtitleTab: 'edit',
        subtitleStyleGroup: null,
        subtitleEvidenceQuality: 'medium_word',
        activeCaptionId: DEMO_CAPTIONS[0]?.id ?? null,
        selection: { kind: 'subtitle', id: DEMO_CAPTIONS[0]?.id ?? 'cap_001' },
        aspectRatio: '9:16',
        canvasBg: '#0b0d11',
        corrections: {},
        dirtyDraft: false,
        past: [],
        future: [],
      });
      playbackHub.emit(0.3, DEMO_DURATION, false);
      return;
    }

    const d = savedDraft || {};
    const draftCaptions = Array.isArray(d.captions) ? (d.captions as CaptionCue[]) : null;
    const draftOverlays = Array.isArray(d.textOverlays) ? (d.textOverlays as TextOverlayItem[]) : [];
    const draftCuts = Array.isArray(d.cutRanges) ? (d.cutRanges as CutRange[]) : [];
    const draftSubBox =
      d.subtitleBox && typeof d.subtitleBox === 'object'
        ? { ...DEFAULT_SUBTITLE_BOX, ...(d.subtitleBox as Partial<SubtitleBoxTransform>) }
        : { ...DEFAULT_SUBTITLE_BOX };
    const draftPreset =
      typeof d.activeSubtitlePreset === 'string' ? d.activeSubtitlePreset : 'hinglish_impact';
    const draftAspect =
      d.aspectRatio === '16:9' || d.aspectRatio === '1:1' || d.aspectRatio === '4:5'
        ? d.aspectRatio
        : '9:16';
    const draftBg = typeof d.canvasBg === 'string' ? d.canvasBg : '#0b0d11';
    const draftCorr =
      d.corrections && typeof d.corrections === 'object'
        ? (d.corrections as Record<string, string>)
        : {};

    let captions: CaptionCue[] = draftCaptions ?? [];
    let evidenceQuality = 'unknown';

    if (!draftCaptions || draftCaptions.length === 0) {
      try {
        const res = await studioApi.getSubtitles(projectId, candidateId || 'source', 4);
        evidenceQuality = res.evidence_quality || 'unknown';
        captions = (res.captions || []).map((c) => ({
          id: c.id,
          start: c.start,
          end: c.end,
          text: c.text,
          originalText: c.text,
          speaker: c.speaker,
          styleName: c.style_name || 'Default',
        }));
      } catch {
        captions = [];
      }
    }

    set({
      hydratedProjectId: projectId,
      projectTitle: title || projectId,
      captions,
      textOverlays: draftOverlays,
      cutRanges: draftCuts,
      subtitleBox: draftSubBox,
      activeSubtitlePreset: draftPreset,
      subtitlePanelState: captions.length > 0 ? 'editor' : 'setup',
      subtitleTab: 'edit',
      subtitleStyleGroup: null,
      subtitleEvidenceQuality: evidenceQuality,
      activeCaptionId: captions[0]?.id ?? null,
      selection: captions[0] ? { kind: 'subtitle', id: captions[0].id } : null,
      aspectRatio: draftAspect,
      canvasBg: draftBg,
      corrections: draftCorr,
      dirtyDraft: false,
      past: [],
      future: [],
    });
  },

  setProjectTitle: (projectTitle) => set({ projectTitle }),
  setActiveTool: (activeTool) => set({ activeTool }),
  setStageViewMode: (stageViewMode) => set({ stageViewMode }),
  setShowSubtitles: (showSubtitles) => set({ showSubtitles }),
  setSubtitlePanelState: (subtitlePanelState) => set({ subtitlePanelState }),
  setSubtitleTab: (subtitleTab) => set({ subtitleTab }),
  setSubtitleStyleGroup: (subtitleStyleGroup) => set({ subtitleStyleGroup }),
  setSubtitleLanguage: (subtitleLanguage) => set({ subtitleLanguage }),
  setSelection: (selection) => set({ selection }),
  setActiveCaptionId: (activeCaptionId) =>
    set({
      activeCaptionId,
      selection: activeCaptionId ? { kind: 'subtitle', id: activeCaptionId } : null,
    }),

  setActiveSubtitlePreset: (activeSubtitlePreset) =>
    set((s) => ({ ...pushHistory(s), activeSubtitlePreset })),

  setAspectRatio: (aspectRatio) => set((s) => ({ ...pushHistory(s), aspectRatio })),
  setCanvasBg: (canvasBg) => set((s) => ({ ...pushHistory(s), canvasBg })),

  updateAiTools: (patch) =>
    set((s) => ({ aiTools: { ...s.aiTools, ...patch }, dirtyDraft: true })),

  dismissScriptTip: () => set({ scriptTipDismissed: true }),

  setCaptions: (captions, evidenceQuality) =>
    set((s) => ({
      ...pushHistory(s),
      captions,
      subtitleEvidenceQuality: evidenceQuality ?? s.subtitleEvidenceQuality,
      activeCaptionId: captions[0]?.id ?? null,
      selection: captions[0] ? { kind: 'subtitle', id: captions[0].id } : null,
    })),

  updateCaptionText: (id, text) =>
    set((s) => {
      const target = s.captions.find((c) => c.id === id);
      const nextCorrections = { ...s.corrections };
      if (target?.originalText && target.originalText !== text && text.trim()) {
        // Track word-level non-destructive typo fixes (never mutates immutable source/transcript.json)
        const oldWords = target.originalText.trim().split(/\s+/);
        const newWords = text.trim().split(/\s+/);
        if (oldWords.length === newWords.length) {
          oldWords.forEach((ow, idx) => {
            if (ow !== newWords[idx]) {
              nextCorrections[ow] = newWords[idx];
            }
          });
        }
      }
      return {
        ...pushHistory(s),
        corrections: nextCorrections,
        captions: s.captions.map((c) => (c.id === id ? { ...c, text } : c)),
      };
    }),

  updateCaptionTiming: (id, start, end) =>
    set((s) => ({
      ...pushHistory(s),
      captions: s.captions
        .map((c) =>
          c.id === id
            ? { ...c, start: Math.max(0, start), end: Math.max(start + 0.15, end) }
            : c,
        )
        .sort((a, b) => a.start - b.start),
    })),

  duplicateCaption: (id) =>
    set((s) => {
      const src = s.captions.find((c) => c.id === id);
      if (!src) return s;
      const dur = Math.max(0.5, src.end - src.start);
      const copy: CaptionCue = {
        ...src,
        id: `cap_${Date.now().toString(36)}`,
        start: Number(src.end.toFixed(3)),
        end: Number((src.end + dur).toFixed(3)),
      };
      const next = [...s.captions, copy].sort((a, b) => a.start - b.start);
      return { ...pushHistory(s), captions: next, activeCaptionId: copy.id };
    }),

  deleteCaption: (id) =>
    set((s) => {
      const next = s.captions.filter((c) => c.id !== id);
      return {
        ...pushHistory(s),
        captions: next,
        activeCaptionId: s.activeCaptionId === id ? next[0]?.id ?? null : s.activeCaptionId,
      };
    }),

  splitCaptionAtTime: (time) =>
    set((s) => {
      const target =
        s.captions.find((c) => time > c.start + 0.12 && time < c.end - 0.12) ||
        s.captions.find((c) => c.id === s.activeCaptionId);
      if (!target) {
        toast.info('Select a subtitle or position playhead inside a caption to split');
        return s;
      }
      const splitPoint =
        time > target.start + 0.12 && time < target.end - 0.12
          ? time
          : (target.start + target.end) / 2;
      const words = target.text.trim().split(/\s+/);
      const midIdx = Math.max(1, Math.floor(words.length / 2));
      const firstText = words.slice(0, midIdx).join(' ') || target.text;
      const secondText = words.slice(midIdx).join(' ') || target.text;
      const second: CaptionCue = {
        ...target,
        id: `cap_${Date.now().toString(36)}`,
        start: Number(splitPoint.toFixed(3)),
        end: target.end,
        text: secondText,
      };
      const next = s.captions
        .flatMap((c) =>
          c.id === target.id
            ? [{ ...c, end: Number(splitPoint.toFixed(3)), text: firstText }, second]
            : [c],
        )
        .sort((a, b) => a.start - b.start);
      toast.success('Subtitle split', `Split at ${splitPoint.toFixed(2)}s`);
      return { ...pushHistory(s), captions: next, activeCaptionId: second.id };
    }),

  addCaptionAtTime: (time, maxDuration) =>
    set((s) => {
      const start = Math.max(0, Number(time.toFixed(3)));
      const end = Math.min(Math.max(maxDuration, start + 2), Number((start + 2.0).toFixed(3)));
      const created: CaptionCue = {
        id: `cap_${Date.now().toString(36)}`,
        start,
        end,
        text: 'New subtitle line',
        styleName: 'Default',
      };
      const next = [...s.captions, created].sort((a, b) => a.start - b.start);
      toast.success('Subtitle added', `${start.toFixed(2)}s – ${end.toFixed(2)}s`);
      return {
        ...pushHistory(s),
        captions: next,
        subtitlePanelState: 'editor',
        activeCaptionId: created.id,
        selection: { kind: 'subtitle', id: created.id },
      };
    }),

  updateSubtitleBox: (patch, commitHistory = false) =>
    set((s) => ({
      ...(commitHistory ? pushHistory(s) : { dirtyDraft: true }),
      subtitleBox: { ...s.subtitleBox, ...patch },
    })),

  addTextOverlay: (item) =>
    set((s) => ({
      ...pushHistory(s),
      textOverlays: [...s.textOverlays, item],
      selection: { kind: 'text', id: item.id },
    })),

  updateTextOverlay: (id, patch, commitHistory = false) =>
    set((s) => ({
      ...(commitHistory ? pushHistory(s) : { dirtyDraft: true }),
      textOverlays: s.textOverlays.map((t) => (t.id === id ? { ...t, ...patch } : t)),
    })),

  deleteTextOverlay: (id) =>
    set((s) => ({
      ...pushHistory(s),
      textOverlays: s.textOverlays.filter((t) => t.id !== id),
      selection: s.selection?.kind === 'text' && s.selection.id === id ? null : s.selection,
    })),

  addCutRange: (range) =>
    set((s) => {
      const created: CutRange = {
        ...range,
        id: `cut_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 5)}`,
      };
      return {
        ...pushHistory(s),
        cutRanges: [...s.cutRanges, created].sort((a, b) => a.start - b.start),
      };
    }),

  removeCutRange: (id) =>
    set((s) => ({
      ...pushHistory(s),
      cutRanges: s.cutRanges.filter((r) => r.id !== id),
    })),

  undo: () =>
    set((s) => {
      if (!s.past.length) return s;
      const prev = s.past[s.past.length - 1];
      return {
        ...prev,
        past: s.past.slice(0, -1),
        future: [snapshotUndoable(s), ...s.future.slice(0, 30)],
        dirtyDraft: true,
      };
    }),

  redo: () =>
    set((s) => {
      if (!s.future.length) return s;
      const next = s.future[0];
      return {
        ...next,
        past: [...s.past.slice(-30), snapshotUndoable(s)],
        future: s.future.slice(1),
        dirtyDraft: true,
      };
    }),

  persistDraft: async (projectId) => {
    if (!projectId || projectId === DEMO_PROJECT_ID) {
      set({ dirtyDraft: false });
      return;
    }
    const s = get();
    try {
      await studioApi.saveEditorDraft(projectId, snapshotUndoable(s) as unknown as Record<string, unknown>);
      set({ dirtyDraft: false });
    } catch (e) {
      toast.error('Could not save draft', String(e));
    }
  },
}));
