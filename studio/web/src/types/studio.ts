export interface StudioHealth {
  ok: boolean;
  app: string;
  fcc_online: boolean;
  fcc_base_url: string;
  fcc_active_model: string | null;
  fcc_models: string[];
  nvenc_available: boolean;
  face_detector: string;
  supervisor_bin: string | null;
}

export interface SubtitlePreset {
  name: string;
  display_name: string;
  description: string;
  font_name: string;
  font_size: number;
  primary_hex: string;
  active_hex: string;
  outline_hex: string;
  back_hex: string;
  bold: boolean;
  italic: boolean;
  border_style: number;
  outline: number;
  shadow: number;
  uppercase: boolean;
  active_word_mode: string;
  pop_scale_percent: number;
  glow_blur: number;
  recommended_for: string[];
}

export interface PipelineStageMeta {
  name: string;
  gated: boolean;
  checkpoint_required: boolean;
  produces: string[];
}

export interface PipelineSummary {
  name: string;
  version: string;
  description: string;
  category: string;
  stability: string;
  default_checkpoint_policy: string;
  budget_default_usd: number;
  reference_input_supported: boolean;
  compatible_playbooks: {
    recommended: string[];
    also_works: string[];
    custom_allowed: boolean;
  };
  stages: PipelineStageMeta[];
  stage_count: number;
  gated_stages: string[];
}

export interface PlaybookSummary {
  slug: string;
  name: string;
  category: string;
  mood: string;
  pace: string;
  best_for: string;
  palette: {
    primary: string[];
    accent: string[];
    background: string;
    text: string;
    muted: string;
  };
  typography: {
    heading_font: string;
    body_font: string;
    code_font: string;
  };
  motion_style: string;
  music_mood: string;
}

export interface MediaProfile {
  name: string;
  width: number;
  height: number;
  aspect_ratio: string;
  fps: number;
  codec: string;
  audio_codec: string;
  crf: number;
  pixel_format: string;
  max_file_size_mb: number | null;
  max_duration_seconds: number | null;
  caption_format: string;
  notes: string;
}

export interface ToolCapabilityRollup {
  capability: string;
  configured: number;
  total: number;
  available_providers: string[];
  unavailable_providers: string[];
}

export interface ToolEntry {
  name: string;
  capability: string;
  provider: string;
  tier: string;
  runtime: string;
  stability: string;
  status: 'available' | 'degraded' | 'unavailable' | string;
  best_for: string[];
  dependencies: string[];
  install_instructions: string;
}

export interface ToolRegistrySnapshot {
  total: number;
  counts: { available: number; degraded: number; unavailable: number; [k: string]: number };
  composition_runtimes: Record<string, boolean>;
  runtime_warnings: string[];
  capabilities: ToolCapabilityRollup[];
  setup_offers: Array<{ capability: string; tool: string; install_instructions: string }>;
  tiers: Record<string, { available: number; unavailable: number; degraded: number }>;
  tools: ToolEntry[];
}

export interface MusicTrack {
  name: string;
  filename: string;
  rel_path: string;
  extension: string;
  size_bytes: number;
  stream_url: string;
}

export interface MusicLibrarySnapshot {
  library_dir: string;
  exists: boolean;
  count: number;
  tracks: MusicTrack[];
}

export interface ProjectSummary {
  project_id: string;
  id?: string;
  title?: string;
  pipeline_type?: string;
  status?: string;
  live?: boolean;
  stalled?: boolean;
  awaiting_human?: boolean;
  active_stage?: string | null;
  stage_states?: Array<{ name: string; status: string; gated?: boolean }>;
  stages?: Array<{ name: string; status: string; gated?: boolean }>;
  poster?: string | null;
  thumbnail_url?: string | null;
  last_activity?: number | null;
  updated_at?: number | null;
  completed_count?: number;
  render_count?: number;
  scene_count?: number;
  cost_usd?: number;
  [k: string]: unknown;
}

export interface StageRailItem {
  name: string;
  gated: boolean;
  produces: string[];
  status: string;
  timestamp: string | null;
  review: Record<string, unknown> | null;
  cost_snapshot: Record<string, unknown> | null;
  error: string | null;
  human_approved: boolean | null;
  partial_progress: Record<string, unknown> | null;
  versions: number;
  gate_skipped?: boolean;
  history_entries?: Array<{ status: string; timestamp: string | null }>;
}

export interface LayoutRange {
  start: number;
  end: number;
  layout: 'TRACK' | 'SPLIT' | 'GENERAL' | 'ALTERNATE' | string;
  scene_index?: number;
  crop_box?: [number, number, number, number];
  top_box?: [number, number, number, number];
  bottom_box?: [number, number, number, number];
  punch_ins?: Array<{ time: number; scale: number; duration?: number }>;
  [k: string]: unknown;
}

export interface CropOverrideEntry {
  layout?: 'TRACK' | 'SPLIT' | 'GENERAL' | 'ALTERNATE' | string;
  /** Normalized 0..1 [x, y, w, h] for single crop */
  crop?: [number, number, number, number];
  /** Normalized 0..1 [x, y, w, h] for 2-speaker top panel */
  top?: [number, number, number, number];
  /** Normalized 0..1 [x, y, w, h] for 2-speaker bottom panel */
  bottom?: [number, number, number, number];
}

export type CropOverridesMap = Record<string, CropOverrideEntry>;

export interface ClipStudioClip {
  candidate_id: string;
  clip_id?: string;
  title?: string;
  hook_text?: string;
  spoken_hook?: string;
  start_seconds: number;
  end_seconds: number;
  duration_seconds?: number;
  virality_score?: number;
  review_state?: string;
  production_state?: string;
  style_preset?: string;
  layout_mode?: string;
  render_path?: string | null;
  render_url?: string | null;
  source_path?: string | null;
  source_url?: string | null;
  thumb_url?: string | null;
  layout_sidecar?: {
    ranges?: LayoutRange[];
    punch_ins?: Array<{ time: number; scale?: number; duration?: number }>;
    source_width?: number;
    source_height?: number;
    [k: string]: unknown;
  } | null;
  qa_report?: {
    passed?: boolean;
    status?: string;
    checks?: Array<{ name: string; passed: boolean; detail?: string; severity?: string }>;
    technical_probe?: {
      width?: number;
      height?: number;
      fps?: number;
      video_codec?: string;
      audio_codec?: string;
      pix_fmt?: string;
      duration?: number;
      faststart?: boolean;
      metadata_scrubbed?: boolean;
      [k: string]: unknown;
    };
    audio_spotcheck?: {
      integrated_lufs?: number;
      true_peak_dbtp?: number;
      lra?: number;
      [k: string]: unknown;
    };
    [k: string]: unknown;
  } | null;
  cold_viewer_audit?: Record<string, boolean | string> | null;
  exported?: boolean;
  export_path?: string | null;
  [k: string]: unknown;
}

export interface BoardState {
  project_id: string;
  title?: string;
  pipeline_type?: string;
  pipeline?: {
    pipeline_type?: string;
    stages?: Array<{ name: string; gated?: boolean; produces?: string[] }>;
    known?: boolean;
  };
  live?: boolean;
  stalled?: boolean;
  stages: StageRailItem[];
  artifacts: Record<string, unknown>;
  storyboard?: { scenes?: Array<Record<string, unknown>> } | null;
  scenes?: Array<Record<string, unknown>>;
  decisions?: Array<Record<string, unknown>>;
  events?: Array<Record<string, unknown>>;
  cost?: { total_usd?: number; budget_usd?: number; by_stage?: Record<string, number>; [k: string]: unknown } | null;
  media?: {
    renders?: Array<{ rel_path?: string; name?: string; url?: string }>;
    snapshots?: Array<{ rel_path?: string; name?: string; url?: string }>;
    music?: Array<{ rel_path?: string; name?: string; url?: string }>;
    [k: string]: unknown;
  };
  clip_studio?: {
    source_video?: string | null;
    source_url?: string | null;
    plan_sha256?: string | null;
    awaiting_approval?: boolean;
    clips: ClipStudioClip[];
    export_manifest?: Record<string, unknown> | null;
  } | null;
  crop_drafts?: Record<string, CropOverridesMap>;
  [k: string]: unknown;
}

export interface TranscriptWord {
  word: string;
  start: number;
  end: number;
}

export interface TranscriptResponse {
  candidate_id: string | null;
  clip_start_seconds: number | null;
  clip_end_seconds: number | null;
  window_start: number;
  window_end: number | null;
  words: TranscriptWord[];
}

export interface WaveformData {
  duration_seconds: number;
  bins: number;
  has_audio: boolean;
  peaks: number[];
}

export interface FilmstripFrame {
  index: number;
  timestamp: number;
  file: string;
  url: string;
  data_url?: string;
}

export interface FilmstripData {
  cache_key: string;
  duration_seconds: number;
  count: number;
  width: number;
  frames: FilmstripFrame[];
}

export interface ProjectFileItem {
  rel_path: string;
  name: string;
  extension: string;
  size_bytes: number;
  mtime: number;
  media_url: string;
}

export interface SupervisorMessage {
  id: number;
  session_id: string;
  role: 'user' | 'assistant' | 'tool_use' | 'tool_result' | 'system' | string;
  content: Record<string, unknown>;
  created_at: string;
}

export interface SupervisorSession {
  session_id: string;
  claude_session_id: string | null;
  project_id: string | null;
  title: string;
  source_input: string | null;
  status: 'idle' | 'running' | 'awaiting_human' | 'completed' | 'stopped' | 'error' | string;
  last_error: string | null;
  created_at: string;
  updated_at: string;
  running?: boolean;
  messages?: SupervisorMessage[];
}

export interface FsBrowseResult {
  path: string;
  parent: string | null;
  quick_roots: Array<{ label: string; path: string }>;
  dirs: Array<{ name: string; path: string }>;
  files: Array<{ name: string; path: string; kind: string; size_bytes: number }>;
}
