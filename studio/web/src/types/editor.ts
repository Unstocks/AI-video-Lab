/**
 * Normalized Creator Video Editor domain state models (`MASTER_06 v2.0`).
 * Centralizes project, clips, captions, text layers, cut ranges, and AI toggles
 * so switching ToolRail panels NEVER resets editor state.
 */

export type ToolId =
  | 'ai-tools'
  | 'video'
  | 'audio'
  | 'image'
  | 'subtitles'
  | 'text'
  | 'elements'
  | 'script'
  | 'brand-kit'
  | 'settings';

export type AspectRatioId = '9:16' | '16:9' | '1:1' | '4:5';
export type StageViewMode = 'preview' | 'reframe_crop' | 'split_compare';
export type SubtitlePanelState = 'setup' | 'processing' | 'editor';
export type SubtitleEditorTab = 'edit' | 'style';
export type SubtitleStyleGroup = 'dynamic' | 'content-aware';

export interface CaptionCue {
  id: string;
  start: number;
  end: number;
  text: string;
  originalText?: string;
  speaker?: string | null;
  stylePreset?: string;
  styleName?: 'Default' | 'Seam' | string;
}

export interface TextOverlayItem {
  id: string;
  templateId: string;
  category: 'Simple' | 'Title' | 'Lower Third' | 'Other';
  text: string;
  subtext?: string;
  start: number;
  end: number;
  /** Normalized 0..1 position of box center on stage */
  x: number;
  y: number;
  /** Normalized 0..1 width/height relative to stage */
  width: number;
  height: number;
  rotation: number;
  fontFamily: string;
  fontSize: number;
  fontWeight: number;
  italic?: boolean;
  uppercase?: boolean;
  color: string;
  backgroundColor?: string;
  letterSpacing?: string;
}

export interface CutRange {
  id: string;
  start: number;
  end: number;
  label: string;
  intersectsHook?: boolean;
}

export interface SubtitleBoxTransform {
  /** Normalized 0..1 center X/Y and width */
  x: number;
  y: number;
  width: number;
  rotation: number;
  fontScale: number;
}

export interface AiToolsSettings {
  layoutMode: 'auto' | 'single_crop' | 'blurred_pillarbox' | 'stacked_split' | 'speaker_cut';
  enablePunchIn: boolean;
  magicSilenceCut: boolean;
  broadcastLoudnorm: boolean;
  voiceDenoise: boolean;
  seamSubtitles: boolean;
  eyeContactAssist: boolean;
}

export type CanvasSelection =
  | { kind: 'subtitle'; id: string }
  | { kind: 'text'; id: string }
  | { kind: 'clip'; id: string }
  | null;

export interface EditorUndoableState {
  captions: CaptionCue[];
  textOverlays: TextOverlayItem[];
  cutRanges: CutRange[];
  subtitleBox: SubtitleBoxTransform;
  activeSubtitlePreset: string;
  aspectRatio: AspectRatioId;
  canvasBg: string;
  corrections: Record<string, string>;
}
