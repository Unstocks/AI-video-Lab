import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowUp,
  ChevronDown,
  Loader2,
  Paperclip,
  Sparkles,
} from 'lucide-react';
import { studioApi } from '@/lib/api';
import {
  toast,
  useSupervisorStore,
  useSystemStore,
} from '@/stores/useStudioStore';

export interface ComposerSeed {
  pipeline_type: string;
  style_playbook?: string;
  style_preset?: string;
  media_profile?: string;
  prompt?: string;
}

const QUICK_FORMAT_OPTIONS = [
  { id: 'instagram_reels', label: '10s · Instagram Reels · Portrait', profile: 'instagram_reels' },
  { id: 'youtube_shorts', label: '60s · YouTube Shorts · Portrait', profile: 'youtube_shorts' },
  { id: 'tiktok_vertical', label: '30s · TikTok · Portrait', profile: 'tiktok_vertical' },
  { id: 'youtube_landscape', label: '2m · YouTube · Landscape', profile: 'youtube_landscape' },
  { id: 'linkedin_square', label: '45s · LinkedIn · Square 1:1', profile: 'linkedin_square' },
];

export function TalkingVideoComposer({
  seed,
  inputRef,
}: {
  seed?: ComposerSeed | null;
  inputRef?: React.RefObject<HTMLInputElement | null>;
}) {
  const navigate = useNavigate();
  const { pipelines, mediaProfiles, setDockOpen } = useSystemStore();
  const { loadSessions, selectSession, setRunning } = useSupervisorStore();

  const fileRef = useRef<HTMLInputElement>(null);
  const [prompt, setPrompt] = useState(seed?.prompt ?? '');
  const [pipeline, setPipeline] = useState(seed?.pipeline_type ?? 'clip-factory');
  const [formatId, setFormatId] = useState(seed?.media_profile ?? 'instagram_reels');
  const [runtime, setRuntime] = useState<'auto' | 'ffmpeg' | 'hyperframes' | 'remotion'>('auto');
  const [compMode, setCompMode] = useState<'templated' | 'atelier'>('templated');
  const [uploadedPath, setUploadedPath] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Sync seed when user clicks a Template Gallery card
  const effectivePipeline = seed?.pipeline_type || pipeline;
  const effectiveProfile = seed?.media_profile || formatId;

  const productionPipelines = pipelines.filter((p) => p.name !== 'framework-smoke');

  const handleFileUpload = async (file: File) => {
    setUploading(true);
    try {
      const res = await studioApi.uploadMediaFile(file);
      setUploadedPath(res.path);
      if (!prompt.trim()) setPrompt(res.path);
      toast.success('Media uploaded', res.filename);
    } catch (e) {
      toast.error('Upload failed', String(e));
    } finally {
      setUploading(false);
    }
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const raw = prompt.trim();
    if (!raw && !uploadedPath) {
      toast.info('Enter a topic, prompt, or YouTube URL to start');
      return;
    }

    setSubmitting(true);
    try {
      const looksLikeUrl = /^https?:\/\//i.test(raw);
      const isClipFactory = effectivePipeline === 'clip-factory' && (looksLikeUrl || Boolean(uploadedPath));
      const session = isClipFactory
        ? await studioApi.startJob({
            source_input: uploadedPath || raw,
            clip_count: 3,
            style_preset: seed?.style_preset || 'hinglish_impact',
            layout_mode: 'auto',
            enable_punch_in: true,
          })
        : await studioApi.startProduction({
            pipeline_type: effectivePipeline,
            brief_prompt: raw || `Produce ${effectivePipeline} from uploaded source`,
            source_input: uploadedPath || (looksLikeUrl ? raw : undefined),
            style_playbook: seed?.style_playbook,
            media_profile: effectiveProfile,
            render_runtime: runtime === 'auto' ? undefined : runtime,
            composition_mode: compMode,
            style_preset: seed?.style_preset || 'hinglish_impact',
          });

      await loadSessions();
      await selectSession(session.session_id);
      setRunning(true);
      setDockOpen(true);
      toast.success('Production launched', `Executive Producer started ${effectivePipeline}.`);
      if (session.project_id) {
        navigate(`/editor/${encodeURIComponent(session.project_id)}`);
      }
    } catch (err) {
      toast.error('Could not launch production', String(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section aria-label="Create a talking video" className="mx-auto w-full max-w-[860px] text-center">
      <h1 className="text-[28px] font-bold tracking-tight text-[var(--text-primary)]">
        Create a talking video
      </h1>

      <form
        onSubmit={handleSubmit}
        className="mt-5 rounded-[24px] border border-[var(--border-strong)] bg-[var(--bg-surface)] p-2.5 shadow-[var(--shadow-panel)] transition-shadow focus-within:border-[var(--accent-lime-border)] focus-within:ring-2 focus-within:ring-[var(--accent-lime)]/30"
      >
        {/* Top Row: Avatar/Pipeline Pill + Prompt/URL Input + Submit Circle */}
        <div className="flex items-center gap-2">
          {/* Pipeline / Presenter Dropdown Pill */}
          <div className="relative shrink-0">
            <select
              aria-label="Select production pipeline"
              value={effectivePipeline}
              onChange={(e) => setPipeline(e.target.value)}
              className="h-10 appearance-none rounded-full border border-[var(--border-subtle)] bg-[var(--bg-panel)] pl-3.5 pr-8 text-xs font-semibold text-[var(--text-primary)] cursor-pointer hover:border-[var(--border-strong)]"
            >
              {productionPipelines.length > 0 ? (
                productionPipelines.map((p) => (
                  <option key={p.name} value={p.name}>
                    {p.name} ({p.stage_count} stg)
                  </option>
                ))
              ) : (
                <>
                  <option value="clip-factory">clip-factory</option>
                  <option value="talking-head">talking-head</option>
                  <option value="animated-explainer">animated-explainer</option>
                  <option value="avatar-spokesperson">avatar-spokesperson</option>
                  <option value="cinematic">cinematic</option>
                </>
              )}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2.5 top-3 h-3.5 w-3.5 text-[var(--text-muted)]" />
          </div>

          {/* Prompt / YouTube URL Input */}
          <input
            ref={inputRef}
            type="text"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="What should your video talk about? Or paste a YouTube URL…"
            className="h-10 min-w-0 flex-1 bg-transparent px-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none"
          />

          {/* Local Media Upload Button */}
          <input
            ref={fileRef}
            type="file"
            accept="video/*,audio/*,.srt,.vtt,.ass"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleFileUpload(f);
              e.target.value = '';
            }}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            title="Attach local video or audio file"
            aria-label="Attach local media file"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[var(--text-muted)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)] transition-colors cursor-pointer"
          >
            {uploading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Paperclip className="h-4 w-4" />
            )}
          </button>

          {/* Circular Submit Arrow Button */}
          <button
            type="submit"
            disabled={submitting}
            aria-label="Start production"
            title="Launch production with Executive Producer"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[var(--cta-primary)] text-[var(--cta-primary-text)] hover:bg-[var(--cta-primary-hover)] transition-all disabled:opacity-50 cursor-pointer"
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ArrowUp className="h-4 w-4 stroke-[2.5]" />
            )}
          </button>
        </div>

        {/* Bottom Compact Metadata Controls: Duration · Platform · Orientation + Runtime & Mode */}
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--border-subtle)]/70 pt-2 px-1 text-xs">
          <div className="flex flex-wrap items-center gap-2">
            {/* Duration · Platform · Orientation Dropdown */}
            <div className="relative">
              <select
                aria-label="Duration, platform and orientation"
                value={effectiveProfile}
                onChange={(e) => setFormatId(e.target.value)}
                className="h-7 appearance-none rounded-full border border-[var(--border-subtle)] bg-[var(--bg-panel)] pl-3 pr-7 text-[11px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] cursor-pointer"
              >
                {QUICK_FORMAT_OPTIONS.map((opt) => (
                  <option key={opt.id} value={opt.profile}>
                    {opt.label}
                  </option>
                ))}
                {mediaProfiles
                  .filter((mp) => !QUICK_FORMAT_OPTIONS.some((q) => q.profile === mp.name))
                  .map((mp) => (
                    <option key={mp.name} value={mp.name}>
                      {mp.name} · {mp.aspect_ratio} ({mp.width}×{mp.height})
                    </option>
                  ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-1.5 h-3.5 w-3.5 text-[var(--text-muted)]" />
            </div>

            {/* Composition Runtime (AGENT_GUIDE HARD RULE visibility) */}
            <select
              aria-label="Composition runtime"
              value={runtime}
              onChange={(e) => setRuntime(e.target.value as typeof runtime)}
              className="h-7 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-panel)] px-2.5 text-[11px] text-[var(--text-secondary)] cursor-pointer"
            >
              <option value="auto">Runtime: Auto</option>
              <option value="ffmpeg">FFmpeg NVENC</option>
              <option value="hyperframes">HyperFrames HTML/GSAP</option>
              <option value="remotion">Remotion React</option>
            </select>

            {/* Authoring Mode (Templated vs Atelier) */}
            <select
              aria-label="Composition authoring mode"
              value={compMode}
              onChange={(e) => setCompMode(e.target.value as typeof compMode)}
              className="h-7 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-panel)] px-2.5 text-[11px] text-[var(--text-secondary)] cursor-pointer"
            >
              <option value="templated">Mode: Templated</option>
              <option value="atelier">Mode: Atelier (Hero Bespoke)</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
            {uploadedPath ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-[var(--accent-lime-soft)] px-2 py-0.5 font-mono text-[10px] text-[var(--accent-lime-strong)]">
                Attached: {uploadedPath.split(/[\\/]/).pop()}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1">
                <Sparkles className="h-3 w-3 text-[var(--accent-lime-strong)]" />
                13 Pipelines · 169 Tools Ready
              </span>
            )}
          </div>
        </div>
      </form>
    </section>
  );
}
