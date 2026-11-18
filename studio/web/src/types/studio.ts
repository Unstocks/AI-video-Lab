/**
 * Ground-Truth TypeScript contracts 1:1 with C:\AI-Video-Lab Core Brain:
 * - backlot/state.py (`load_board_state`, `_build_clip_studio`, `_build_stage_rail`)
 * - lib/reframe_v2.py (`apply_crop_overrides`)
 * - lib/layout_ranges.py (lowercase `"track" | "split" | "general" | "alternate"`)
 * - lib/models/clip_plan.py & lib/media_qa.py
 * - studio/catalog.py, studio/media_engine.py, studio/server.py
 */

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
  produces: string[];
  description?: string;
}

export interface PipelineSummary {
  name: string;
  display_name: string;
  description: string;
  stability: 'production' | 'beta' | 'test' | string;
  category: string;
  stage_count: number;
  gated_stages: string[];
  stages: PipelineStageMeta[];
  playbooks_compatible: string[];
  budget_default_usd: number;
  reference_video_supported: boolean;
}

export interface PlaybookSummary {
  slug: string;
  name: string;
  category: string;
  mood: string;
  best_for: string;
  pace: string;
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
  music_mood: string;
}

export interface MediaProfile {
  name: string;
  width: number;
  height: number;
  aspect_ratio: string;
  fps: number;
  video_codec: string;
  audio_codec: string;
  max_duration_seconds: number | null;
  platform: string;
  description: string;
}

export interface ToolRecord {
  name: string;
  capability: string;
  provider: string;
  tier: string;
  runtime: string;
  status: 'available' | 'degraded' | 'unavailable';
  best_for: string[];
  dependencies: string[];
  install_instructions: string;
  cost_tier: string;
  is_selector: boolean;
}

export interface CapabilityRollup {
  capability: string;
  configured: number;
  total: number;
  available_providers: string[];
  unavailable_providers: string[];
}

export interface ToolRegistrySnapshot {
  total: number;
  counts: {
    available: number;
    degraded: number;
    unavailable: number;
  };
  composition_runtimes: Record<string, boolean>;
  runtime_warnings: string[];
  setup_offers: Array<Record<string, unknown>>;
  capabilities: CapabilityRollup[];
  tools: ToolRecord[];
  cached_at: number;
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

export interface BundledFontInfo {
  filename: string;
  stem: string;
  url: string;
  size_bytes: number;
}

export interface ProjectSummary {
  project_id: string;
  id?: string;
  title: string;
  pipeline_type: string;
  style_playbook?: string | null;
  series?: string | null;
  poster?: string | null;
  poster_url?: string | null;
  last_activity?: number | null;
  live?: boolean;
  stalled?: boolean;
  awaiting_human?: boolean;
  active_stage?: string | null;
  completed_count?: number;
  render_count?: number;
  scene_count?: number;
  stage_states?: Array<{
    name: string;
    status: string;
    gated: boolean;
  }>;
}

export interface StageRailItem {
  name: string;
  status: 'pending' | 'in_progress' | 'awaiting_human' | 'completed' | 'failed' | string;
  gated: boolean;
  produces: string[];
  timestamp?: string | null;
  review?: Record<string, unknown> | null;
  cost_snapshot?: Record<string, unknown> | null;
  error?: string | null;
  human_approved?: boolean | null;
  partial_progress?: Record<string, unknown> | null;
  versions: number;
  history_entries?: Array<{ status: string; timestamp?: string }>;
  saw_awaiting_human?: boolean;
  gate_skipped?: boolean;
  undeclared?: boolean;
  stalled?: boolean;
  stalled_minutes?: number;
}

/** Exact lowercase layout values from lib/layout_ranges.py */
export type LayoutKind = 'track' | 'split' | 'general' | 'alternate';

export interface LayoutRange {
  start: number;
  end: number;
  layout: LayoutKind;
  /** Optional vertical band fractions [top, bottom] on "general" blurred pillarbox */
  content?: [number, number];
}

/**
 * Exact per-scene crop override contract accepted by `lib/reframe_v2.py:apply_crop_overrides()`.
 * Keys in CropOverridesMap are 0-based scene indices ("0", "1", ...).
 */
export interface CropPoint {
  x: number;
  y: number;
}

export type CropOverrideEntry =
  | number
  | { x: number }
  | { layout: 'general' }
  | { top: CropPoint | number; bottom: CropPoint | number };

export type CropOverridesMap = Record<string, CropOverrideEntry>;

export interface SpokenHookEvidence {
  text: string;
  speaker?: string | null;
  source_spans?: Array<{
    transcript_revision_id?: string;
    segment_id?: number;
    char_start?: number;
    char_end?: number;
  }>;
}

export interface ColdViewerAudit {
  subject_grounded?: boolean;
  entities_resolved?: boolean;
  pronouns_resolved?: boolean;
  premise_to_payoff_complete?: boolean;
  qualifiers_preserved?: boolean;
  passed?: boolean;
  notes?: string;
  context_expansion_applied?: boolean;
}

export type CheckStatus = 'PASS' | 'FAIL' | 'WARNING' | 'NOT_CHECKED' | 'INDETERMINATE';

export interface ClipQaSummary {
  status?: 'pass' | 'fail' | 'revise' | string | null;
  production_state?: string | null;
  resolution?: string | null;
  codec?: string | null;
  pix_fmt?: string | null;
  integrated_lufs?: number | null;
  true_peak_dbtp?: number | null;
  issues?: string[];
  check_statuses?: Record<string, CheckStatus | string>;
  video_sha256?: string | null;
}

/** Exact shape emitted by backlot/state.py:_build_clip_studio() */
export interface ClipStudioClip {
  candidate_id: string;
  editorial_title: string;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  validation_state?: string;
  eligibility_state?: string;
  review_state: string;
  production_state: string;
  spoken_hook: SpokenHookEvidence | null;
  spoken_opening?: string | null;
  original_spoken_dialogue?: string | null;
  cold_viewer_audit: ColdViewerAudit | null;
  video_path: string | null;
  video_mtime: number | null;
  subtitle_path: string | null;
  seam_subtitles_used: boolean;
  layout_ranges: LayoutRange[];
  punch_ins: number[];
  qa: ClipQaSummary | null;
  exported_paths: string[];
}

export interface ClipStudioProjection {
  source_video: string | null;
  source_manifest: Record<string, unknown> | null;
  plan_sha256_synced: boolean | null;
  awaiting_approval_count: number;
  approved_count: number;
  qa_passed_count: number;
  exported_count: number;
  clips: ClipStudioClip[];
}

export interface StoryboardScene {
  id: string | number;
  type?: string;
  description?: string;
  start_seconds?: number;
  end_seconds?: number;
  duration_seconds?: number;
  hero_moment?: boolean;
  narration?: string;
  section_label?: string;
  visual?: {
    id?: string;
    type?: string;
    path?: string;
    exists?: boolean;
    renderable?: boolean;
    snapshot?: boolean;
    prompt?: string;
    model?: string;
    provider?: string;
    cost_usd?: number;
  } | null;
  takes?: Array<Record<string, unknown>>;
  audio?: Array<{ path?: string; exists?: boolean; duration_seconds?: number }>;
  generating?: boolean;
  generating_tool?: string | null;
}

export interface BoardEvent {
  ts?: number | string;
  call_id?: string;
  tool?: string;
  scene_id?: string | number;
  depth?: number | null;
  event?: 'start' | 'finish' | 'error';
  type?: string;
  success?: boolean;
  duration_s?: number;
  error?: string;
}

export interface BoardState {
  project_id: string;
  title: string;
  pipeline: {
    pipeline_type: string;
    stages: Array<{ name: string; gated: boolean; produces: string[] }>;
    known: boolean;
  };
  style_playbook?: string | null;
  series?: string | null;
  created_at?: string | null;
  has_marker?: boolean;
  has_pipeline_state?: boolean;
  stages: StageRailItem[];
  artifacts: Record<string, unknown>;
  storyboard?: {
    scenes: StoryboardScene[];
    total_duration_seconds?: number;
    style_playbook?: string | null;
  } | null;
  media?: {
    renders: Array<{ path: string; size?: number; mtime?: number; at_root?: boolean }>;
    snapshots: Array<{ path: string }>;
    music: Array<{ path: string; at_root?: boolean }>;
  };
  clip_studio?: ClipStudioProjection | null;
  events?: BoardEvent[];
  cost?: {
    total_spent_usd?: number;
    total_reserved_usd?: number;
    budget_remaining_usd?: number;
  } | null;
  last_activity?: number | null;
  live?: boolean;
  poster?: string | null;
  crop_drafts?: Record<string, CropOverridesMap>;
  editor_draft?: Record<string, unknown>;
}

export interface TranscriptWord {
  word: string;
  start: number;
  end: number;
  speaker?: string | null;
}

export interface TranscriptResponse {
  candidate_id: string | null;
  clip_start_seconds: number | null;
  clip_end_seconds: number | null;
  window_start: number;
  window_end: number | null;
  evidence_quality: string;
  timing_source: string;
  words: TranscriptWord[];
}

export interface SubtitlesApiResponse {
  candidate_id: string | null;
  source: 'ass' | 'srt' | 'transcript_chunked' | string;
  evidence_quality: string;
  timing_source: string;
  language?: string;
  status?: string;
  captions: Array<{
    id: string;
    start: number;
    end: number;
    text: string;
    speaker?: string | null;
    style_name?: string;
  }>;
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

export interface SupervisorSession {
  session_id: string;
  claude_session_id: string | null;
  project_id: string | null;
  title: string;
  source_input: string | null;
  status: string;
  last_error: string | null;
  created_at: string;
  updated_at: string;
  running?: boolean;
  messages?: SupervisorMessage[];
}

export interface SupervisorMessage {
  id: number;
  session_id: string;
  role: 'user' | 'assistant' | 'tool_use' | 'tool_result' | 'system';
  content: Record<string, unknown>;
  created_at: string;
}

export interface ProjectFileItem {
  rel_path: string;
  name: string;
  extension: string;
  size_bytes: number;
  mtime: number;
  media_url: string;
}

export interface FsBrowseResult {
  path: string;
  parent: string | null;
  quick_roots: Array<{ label: string; path: string }>;
  dirs: Array<{ name: string; path: string }>;
  files: Array<{ name: string; path: string; kind: string; size_bytes: number }>;
}

export interface BrandKitRecord {
  item_id: string;
  category: 'saved' | 'video' | 'audio' | 'image' | 'subtitle' | 'font_color';
  name: string;
  payload: Record<string, unknown>;
  created_at: string;
}
