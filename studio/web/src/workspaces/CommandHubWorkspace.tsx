import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  ArrowRight,
  Clapperboard,
  Film,
  FolderOpen,
  Layers,
  Link2,
  Loader2,
  Play,
  Scissors,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  Wand2,
  X,
} from 'lucide-react';
import { studioApi } from '@/lib/api';
import { cn, formatBytes, formatRelativeTime, formatUsd } from '@/lib/format';
import {
  toast,
  useProjectStore,
  useSupervisorStore,
  useSystemStore,
} from '@/stores/useStudioStore';
import { Badge, Button, EmptyState, Panel, StatusDot } from '@/components/ui/Primitives';
import type { FsBrowseResult, ProjectSummary } from '@/types/studio';

type LaunchMode = 'clip-factory' | 'all-pipelines' | 'reference-remix';

function LocalFileBrowserModal({
  open,
  onClose,
  onSelect,
}: {
  open: boolean;
  onClose: () => void;
  onSelect: (path: string) => void;
}) {
  const [data, setData] = useState<FsBrowseResult | null>(null);
  const [loading, setLoading] = useState(false);

  const loadDir = async (dirPath?: string) => {
    setLoading(true);
    try {
      const res = await studioApi.browseFs(dirPath);
      setData(res);
    } catch (e) {
      toast.error('Cannot browse folder', String(e));
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;
  if (!data && !loading) {
    void loadDir();
  }

  return (
    <div
      className="fixed inset-0 z-[95] flex items-center justify-center bg-black/70 backdrop-blur-xs p-4"
      onMouseDown={onClose}
    >
      <div
        className="flex max-h-[75vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-[var(--border-strong)] bg-[var(--bg-surface)] shadow-[var(--shadow-float)]"
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Browse local media files"
      >
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
          <div className="flex items-center gap-2">
            <FolderOpen className="h-4 w-4 text-[var(--accent-amber)]" />
            <span className="text-sm font-semibold">Select Local Media File</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {data && (
          <div className="flex flex-wrap items-center gap-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-canvas)]/60 px-4 py-2">
            {data.quick_roots.map((r) => (
              <Button key={r.path} size="xs" variant="secondary" onClick={() => loadDir(r.path)}>
                {r.label}
              </Button>
            ))}
            {data.parent && (
              <Button size="xs" variant="ghost" onClick={() => loadDir(data.parent!)}>
                ↑ Up
              </Button>
            )}
            <span className="ml-auto font-mono text-[11px] text-[var(--text-muted)] truncate max-w-xs">
              {data.path}
            </span>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-3 space-y-1">
          {loading ? (
            <div className="flex items-center justify-center py-12 text-xs text-[var(--text-muted)]">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Scanning directory…
            </div>
          ) : (
            <>
              {data?.dirs.map((d) => (
                <button
                  key={d.path}
                  type="button"
                  onClick={() => loadDir(d.path)}
                  className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs hover:bg-[var(--bg-elevated)] transition-colors cursor-pointer"
                >
                  <FolderOpen className="h-4 w-4 text-[var(--accent-amber)] shrink-0" />
                  <span className="font-medium text-[var(--text-primary)]">{d.name}</span>
                </button>
              ))}
              {data?.files.map((f) => (
                <button
                  key={f.path}
                  type="button"
                  onClick={() => {
                    onSelect(f.path);
                    onClose();
                  }}
                  className="flex w-full items-center justify-between gap-2.5 rounded-lg px-3 py-2 text-left text-xs hover:bg-[var(--accent-cyan-soft)] transition-colors cursor-pointer"
                >
                  <span className="flex items-center gap-2.5 min-w-0">
                    <Film className="h-4 w-4 text-[var(--accent-cyan)] shrink-0" />
                    <span className="truncate font-medium text-[var(--text-primary)]">{f.name}</span>
                    <Badge tone="neutral">{f.kind}</Badge>
                  </span>
                  <span className="font-mono text-[10px] text-[var(--text-muted)] shrink-0">
                    {formatBytes(f.size_bytes)}
                  </span>
                </button>
              ))}
              {data && data.dirs.length === 0 && data.files.length === 0 && (
                <div className="py-10 text-center text-xs text-[var(--text-muted)]">
                  No media files or subfolders in this directory.
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ProjectCard({
  project,
  onOpen,
}: {
  project: ProjectSummary;
  onOpen: (tab: 'nle' | 'board' | 'qa') => void;
}) {
  const pid = project.project_id || project.id || '';
  const stages = Array.isArray(project.stage_states)
    ? project.stage_states
    : Array.isArray(project.stages)
      ? project.stages
      : [];
  const completedCount =
    typeof project.completed_count === 'number'
      ? project.completed_count
      : stages.filter((s) => s.status === 'completed').length;
  const awaiting = Boolean(project.awaiting_human || stages.some((s) => s.status === 'awaiting_human'));
  const isClip =
    project.pipeline_type === 'clip-factory' || project.pipeline_type === 'podcast-repurpose';
  const thumbSrc =
    project.thumbnail_url ||
    (project.poster && pid ? `/thumb/${encodeURIComponent(pid)}/${project.poster}` : null);
  const lastActivity = project.last_activity ?? project.updated_at;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className="group flex flex-col overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-strong)] transition-all shadow-xs"
    >
      {/* Thumbnail Banner */}
      <div
        onClick={() => onOpen(isClip ? 'nle' : 'board')}
        className="relative h-36 w-full cursor-pointer overflow-hidden bg-[var(--bg-canvas)] border-b border-[var(--border-subtle)]"
      >
        {thumbSrc ? (
          <img
            src={thumbSrc}
            alt={project.title || pid}
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-[var(--bg-panel)] to-[var(--bg-canvas)]">
            <Clapperboard className="h-9 w-9 text-[var(--text-muted)]/40" />
          </div>
        )}

        <div className="absolute inset-x-0 top-0 flex items-center justify-between p-2.5 bg-gradient-to-b from-black/70 to-transparent">
          <Badge tone="neutral" className="bg-black/65 text-zinc-100 border-white/15 backdrop-blur-xs">
            {project.pipeline_type || 'unknown'}
          </Badge>
          {project.live ? (
            <Badge tone="cyan" className="bg-black/70 backdrop-blur-xs">
              <StatusDot tone="cyan" pulse /> LIVE
            </Badge>
          ) : awaiting ? (
            <Badge tone="amber" className="bg-black/75 backdrop-blur-xs">
              <StatusDot tone="amber" pulse /> AWAITING GATE
            </Badge>
          ) : project.stalled ? (
            <Badge tone="fail" className="bg-black/75 backdrop-blur-xs">
              STALLED
            </Badge>
          ) : null}
        </div>
      </div>

      {/* Card Body */}
      <div className="flex flex-1 flex-col p-3.5">
        <div className="flex items-start justify-between gap-2">
          <h3 className="text-sm font-semibold text-[var(--text-primary)] truncate">
            {project.title || pid}
          </h3>
          {typeof project.cost_usd === 'number' && project.cost_usd > 0 && (
            <span className="font-mono text-[11px] text-[var(--text-muted)] shrink-0">
              {formatUsd(project.cost_usd)}
            </span>
          )}
        </div>
        <div className="mt-0.5 font-mono text-[11px] text-[var(--text-muted)] truncate">
          {pid} · {formatRelativeTime(lastActivity)}
        </div>

        {/* Mini Stage Progress Rail */}
        {stages.length > 0 && (
          <div className="mt-3">
            <div className="flex items-center justify-between text-[10px] text-[var(--text-muted)] mb-1">
              <span>Stages</span>
              <span className="font-mono">
                {completedCount}/{stages.length}
              </span>
            </div>
            <div className="flex gap-1">
              {stages.map((st) => (
                <div
                  key={st.name}
                  title={`${st.name}: ${st.status}`}
                  className={cn(
                    'h-1.5 flex-1 rounded-full',
                    st.status === 'completed'
                      ? 'bg-[var(--status-pass)]'
                      : st.status === 'awaiting_human'
                        ? 'bg-[var(--accent-amber)]'
                        : st.status === 'in_progress'
                          ? 'bg-[var(--accent-cyan)]'
                          : st.status === 'failed'
                            ? 'bg-[var(--status-fail)]'
                            : 'bg-[var(--bg-elevated)]',
                  )}
                />
              ))}
            </div>
          </div>
        )}

        {/* Quick Workspace Actions */}
        <div className="mt-auto pt-3.5 flex items-center gap-1.5">
          <Button
            variant={isClip ? 'primary' : 'secondary'}
            size="xs"
            className="flex-1"
            onClick={() => onOpen('nle')}
          >
            <Scissors className="h-3 w-3" /> NLE
          </Button>
          <Button
            variant={!isClip ? 'primary' : 'secondary'}
            size="xs"
            className="flex-1"
            onClick={() => onOpen('board')}
          >
            <Layers className="h-3 w-3" /> Board
          </Button>
          <Button variant="secondary" size="xs" onClick={() => onOpen('qa')} title="Broadcast QA & Export">
            <ShieldCheck className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>
    </motion.div>
  );
}

export function CommandHubWorkspace() {
  const navigate = useNavigate();
  const { pipelines, playbooks, mediaProfiles, presets, setDockOpen } = useSystemStore();
  const { projects, projectsLoading, loadProjects } = useProjectStore();
  const { loadSessions, selectSession, setRunning } = useSupervisorStore();

  const [mode, setMode] = useState<LaunchMode>('clip-factory');
  const [selectedPipeline, setSelectedPipeline] = useState('animated-explainer');
  const [sourceInput, setSourceInput] = useState('');
  const [referenceUrl, setReferenceUrl] = useState('');
  const [briefPrompt, setBriefPrompt] = useState('');
  const [projectSlug, setProjectSlug] = useState('');
  const [selectedPlaybook, setSelectedPlaybook] = useState('clean-professional');
  const [selectedProfile, setSelectedProfile] = useState('youtube_landscape');
  const [renderRuntime, setRenderRuntime] = useState('auto');
  const [stylePreset, setStylePreset] = useState('hinglish_impact');
  const [layoutMode, setLayoutMode] = useState<
    'auto' | 'single_crop' | 'blurred_pillarbox' | 'stacked_split' | 'speaker_cut'
  >('auto');
  const [clipCount, setClipCount] = useState(3);
  const [enablePunchIn, setEnablePunchIn] = useState(true);
  const [budgetUsd, setBudgetUsd] = useState(3.0);

  const [uploading, setUploading] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [browserOpen, setBrowserOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [pipelineFilter, setPipelineFilter] = useState<string>('all');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const productionPipelines = useMemo(
    () => pipelines.filter((p) => p.name !== 'framework-smoke'),
    [pipelines],
  );

  const filteredProjects = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return projects.filter((p) => {
      const pid = p.project_id || p.id || '';
      if (pipelineFilter !== 'all' && p.pipeline_type !== pipelineFilter) return false;
      if (!q) return true;
      return (
        pid.toLowerCase().includes(q) ||
        String(p.title || '').toLowerCase().includes(q) ||
        String(p.pipeline_type || '').toLowerCase().includes(q)
      );
    });
  }, [pipelineFilter, projects, searchQuery]);

  const handleFileUpload = async (file: File) => {
    setUploading(true);
    try {
      const res = await studioApi.uploadMediaFile(file);
      setSourceInput(res.path);
      toast.success('Media uploaded', `${res.filename} (${formatBytes(res.size_bytes)}) ready.`);
    } catch (e) {
      toast.error('Upload failed', String(e));
    } finally {
      setUploading(false);
    }
  };

  const handleLaunch = async () => {
    setLaunching(true);
    try {
      const effectivePipeline =
        mode === 'clip-factory' ? 'clip-factory' : selectedPipeline;
      const session = await studioApi.startProduction({
        pipeline_type: effectivePipeline,
        brief_prompt: briefPrompt,
        project_id: projectSlug.trim() || null,
        source_input: sourceInput.trim() || null,
        reference_url: mode === 'reference-remix' ? referenceUrl.trim() || null : null,
        style_playbook: mode !== 'clip-factory' ? selectedPlaybook : null,
        media_profile: mode !== 'clip-factory' ? selectedProfile : 'youtube_shorts',
        render_runtime: renderRuntime === 'auto' ? null : renderRuntime,
        style_preset: stylePreset,
        budget_usd: budgetUsd,
        clip_count: clipCount,
        layout_mode: layoutMode,
        enable_punch_in: enablePunchIn,
      });
      await loadSessions();
      await selectSession(session.session_id);
      setRunning(true);
      setDockOpen(true);
      toast.success(
        'Production launched',
        `Top Supervisor started ${effectivePipeline} — watch live progress in the Executive Producer dock.`,
      );
      if (session.project_id) {
        await loadProjects();
        navigate(
          `/project/${session.project_id}/${effectivePipeline === 'clip-factory' ? 'nle' : 'board'}`,
        );
      }
    } catch (e) {
      toast.error('Launch failed', String(e));
    } finally {
      setLaunching(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1360px] space-y-6 p-5">
      {/* Universal Production Launcher */}
      <Panel className="overflow-hidden shadow-[var(--shadow-panel)]">
        {/* Mode Header Tabs */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border-subtle)] bg-[var(--bg-panel)]/70 px-5 py-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-[var(--accent-amber)]" />
            <h1 className="text-sm font-semibold tracking-tight">Production Command Hub</h1>
            <Badge tone="neutral" className="font-mono">
              {productionPipelines.length || 12} Pipelines
            </Badge>
          </div>

          <div className="flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-0.5">
            {(
              [
                ['clip-factory', 'Clip Factory · 9:16', Scissors],
                ['all-pipelines', 'Full Production · 12 Pipelines', Wand2],
                ['reference-remix', 'Reference Video Remix', Link2],
              ] as const
            ).map(([id, label, Icon]) => (
              <button
                key={id}
                type="button"
                onClick={() => setMode(id)}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all cursor-pointer',
                  mode === id
                    ? 'bg-[var(--accent-amber)] text-zinc-950 font-semibold shadow-xs'
                    : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="p-5 space-y-5">
          {/* Mode 1: Clip Factory */}
          {mode === 'clip-factory' && (
            <div className="grid gap-5 lg:grid-cols-12">
              <div className="lg:col-span-7 space-y-3">
                <label className="block text-xs font-medium text-[var(--text-secondary)]">
                  Source Video URL or Local Media File
                </label>
                <div className="flex gap-2">
                  <input
                    value={sourceInput}
                    onChange={(e) => setSourceInput(e.target.value)}
                    placeholder="Paste YouTube / podcast URL, or upload / browse a local .mp4 / .mov…"
                    className="flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-cyan)] focus:outline-none"
                  />
                  <Button variant="secondary" onClick={() => setBrowserOpen(true)}>
                    <FolderOpen className="h-3.5 w-3.5" /> Browse
                  </Button>
                  <Button
                    variant="secondary"
                    disabled={uploading}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    {uploading ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Upload className="h-3.5 w-3.5" />
                    )}
                    Upload
                  </Button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="video/*,audio/*"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (f) void handleFileUpload(f);
                      e.target.value = '';
                    }}
                  />
                </div>

                {/* Drag & Drop Zone */}
                <div
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    const f = e.dataTransfer.files?.[0];
                    if (f) void handleFileUpload(f);
                  }}
                  className="flex items-center justify-between rounded-xl border border-dashed border-[var(--border-strong)] bg-[var(--bg-canvas)]/50 px-4 py-3 text-xs text-[var(--text-muted)]"
                >
                  <span>Drop any local podcast / interview video here for instant streaming upload</span>
                  <span className="font-mono text-[10px]">RTX 3050 NVENC · YuNet · -14 LUFS</span>
                </div>

                {/* Subtitle Preset Visual Strip */}
                <div>
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs font-medium text-[var(--text-secondary)]">
                      Bundled Subtitle Style Preset ({presets.length || 8} DirectWrite Verified)
                    </span>
                    <span className="font-mono text-[10px] text-[var(--text-muted)]">
                      {stylePreset}
                    </span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {presets.map((p) => (
                      <button
                        key={p.name}
                        type="button"
                        onClick={() => setStylePreset(p.name)}
                        className={cn(
                          'rounded-lg border p-2 text-left transition-all cursor-pointer',
                          stylePreset === p.name
                            ? 'border-[var(--accent-amber)] bg-[var(--accent-amber-soft)]'
                            : 'border-[var(--border-subtle)] bg-[var(--bg-canvas)]/60 hover:border-[var(--border-strong)]',
                        )}
                      >
                        <div
                          className="truncate text-xs font-bold"
                          style={{
                            fontFamily: `"${p.font_name}", "Inter", sans-serif`,
                            color: p.active_hex || '#facc15',
                          }}
                        >
                          {p.display_name}
                        </div>
                        <div className="mt-0.5 truncate font-mono text-[10px] text-[var(--text-muted)]">
                          {p.font_name}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Right Framing & Render Settings */}
              <div className="lg:col-span-5 flex flex-col justify-between rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)]/50 p-4 space-y-3">
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-medium text-[var(--text-secondary)] mb-1">
                        Target Clips (1–10)
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        value={clipCount}
                        onChange={(e) => setClipCount(Number(e.target.value) || 2)}
                        className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 py-1.5 font-mono text-xs"
                      />
                    </div>
                    <div>
                      <label className="block text-[11px] font-medium text-[var(--text-secondary)] mb-1">
                        Project Slug (optional)
                      </label>
                      <input
                        value={projectSlug}
                        onChange={(e) => setProjectSlug(e.target.value)}
                        placeholder="auto-slug"
                        className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 py-1.5 font-mono text-xs"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-[var(--text-secondary)] mb-1">
                      Reframe v2 Cinematography Mode
                    </label>
                    <select
                      value={layoutMode}
                      onChange={(e) => setLayoutMode(e.target.value as typeof layoutMode)}
                      className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 py-1.5 text-xs"
                    >
                      <option value="auto">Auto (Smart YuNet Single + 2-Speaker Split)</option>
                      <option value="stacked_split">Stacked 2-Speaker Split (Style: Seam)</option>
                      <option value="single_crop">Single Active-Speaker Track</option>
                      <option value="speaker_cut">Fast Active-Speaker Cut</option>
                      <option value="blurred_pillarbox">Blurred Backdrop Pillarbox</option>
                    </select>
                  </div>

                  <label className="flex items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-xs cursor-pointer">
                    <span>Auto Emphasis Punch-In (1.0x → 1.15x)</span>
                    <input
                      type="checkbox"
                      checked={enablePunchIn}
                      onChange={(e) => setEnablePunchIn(e.target.checked)}
                      className="h-4 w-4 accent-[var(--accent-amber)]"
                    />
                  </label>
                </div>

                <Button
                  variant="primary"
                  size="md"
                  className="w-full"
                  disabled={launching || !sourceInput.trim()}
                  onClick={handleLaunch}
                >
                  {launching ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="h-4 w-4 fill-current" />
                  )}
                  Extract Viral Clips &amp; Stop at Gate
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}

          {/* Mode 2 & 3: All 12 OpenMontage Pipelines & Reference Remix */}
          {mode !== 'clip-factory' && (
            <div className="space-y-4">
              {/* Pipeline Grid */}
              <div>
                <div className="mb-2 text-xs font-medium text-[var(--text-secondary)]">
                  Select Pipeline ({productionPipelines.length} available)
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                  {productionPipelines.map((p) => (
                    <button
                      key={p.name}
                      type="button"
                      onClick={() => {
                        setSelectedPipeline(p.name);
                        setBudgetUsd(p.budget_default_usd || 2.0);
                      }}
                      className={cn(
                        'rounded-xl border p-2.5 text-left transition-all cursor-pointer',
                        selectedPipeline === p.name
                          ? 'border-[var(--accent-amber)] bg-[var(--accent-amber-soft)]'
                          : 'border-[var(--border-subtle)] bg-[var(--bg-canvas)]/50 hover:border-[var(--border-strong)]',
                      )}
                    >
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-xs font-semibold text-[var(--text-primary)] truncate">
                          {p.name}
                        </span>
                        <Badge tone={p.stability === 'production' ? 'pass' : 'neutral'}>
                          {p.stage_count} stg
                        </Badge>
                      </div>
                      <p className="mt-1 line-clamp-2 text-[11px] text-[var(--text-muted)] leading-snug">
                        {p.description}
                      </p>
                    </button>
                  ))}
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-12">
                <div className="lg:col-span-7 space-y-3">
                  {mode === 'reference-remix' && (
                    <div>
                      <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1">
                        Inspiration / Reference Video URL
                      </label>
                      <input
                        value={referenceUrl}
                        onChange={(e) => setReferenceUrl(e.target.value)}
                        placeholder="https://youtube.com/shorts/… or Reel URL to analyze pacing & structure"
                        className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 text-xs"
                      />
                    </div>
                  )}

                  <div>
                    <label className="block text-xs font-medium text-[var(--text-secondary)] mb-1">
                      Creative Brief / Production Direction
                    </label>
                    <textarea
                      rows={3}
                      value={briefPrompt}
                      onChange={(e) => setBriefPrompt(e.target.value)}
                      placeholder="Describe topic, audience, tone, duration, visual treatment, or specific scenes…"
                      className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 py-2 text-xs"
                    />
                  </div>

                  {/* Style Playbook Visual Swatches */}
                  <div>
                    <div className="mb-1.5 text-xs font-medium text-[var(--text-secondary)]">
                      Visual Style Playbook <span className="font-mono text-[10px] text-[var(--text-muted)]">styles/*.yaml</span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {playbooks.map((pb) => (
                        <button
                          key={pb.slug}
                          type="button"
                          onClick={() => setSelectedPlaybook(pb.slug)}
                          className={cn(
                            'rounded-lg border p-2 text-left transition-all cursor-pointer',
                            selectedPlaybook === pb.slug
                              ? 'border-[var(--accent-cyan)] bg-[var(--accent-cyan-soft)]'
                              : 'border-[var(--border-subtle)] bg-[var(--bg-canvas)]/50 hover:border-[var(--border-strong)]',
                          )}
                        >
                          <div className="flex items-center justify-between gap-1">
                            <span className="truncate text-xs font-semibold">{pb.name}</span>
                            <div className="flex items-center gap-0.5 shrink-0">
                              {[
                                pb.palette.background,
                                pb.palette.primary[0],
                                pb.palette.accent[0],
                              ]
                                .filter(Boolean)
                                .map((hex, i) => (
                                  <span
                                    key={i}
                                    className="h-3 w-3 rounded-full border border-white/20"
                                    style={{ backgroundColor: hex }}
                                  />
                                ))}
                            </div>
                          </div>
                          <div className="mt-0.5 truncate text-[10px] text-[var(--text-muted)]">
                            {pb.typography.heading_font} · {pb.pace}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Right Production Parameters */}
                <div className="lg:col-span-5 flex flex-col justify-between rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-canvas)]/50 p-4 space-y-3">
                  <div className="space-y-3">
                    <div>
                      <label className="block text-[11px] font-medium text-[var(--text-secondary)] mb-1">
                        Platform Media Profile
                      </label>
                      <select
                        value={selectedProfile}
                        onChange={(e) => setSelectedProfile(e.target.value)}
                        className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 py-1.5 text-xs"
                      >
                        {mediaProfiles.map((mp) => (
                          <option key={mp.name} value={mp.name}>
                            {mp.name} ({mp.width}×{mp.height} · {mp.aspect_ratio} · {mp.fps}fps)
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[11px] font-medium text-[var(--text-secondary)] mb-1">
                          Composition Runtime
                        </label>
                        <select
                          value={renderRuntime}
                          onChange={(e) => setRenderRuntime(e.target.value)}
                          className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 py-1.5 text-xs"
                        >
                          <option value="auto">Auto Select</option>
                          <option value="ffmpeg">FFmpeg NVENC</option>
                          <option value="remotion">Remotion React</option>
                          <option value="hyperframes">HyperFrames HTML</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-[11px] font-medium text-[var(--text-secondary)] mb-1">
                          Budget Cap ({formatUsd(budgetUsd)})
                        </label>
                        <input
                          type="range"
                          min={0}
                          max={25}
                          step={0.5}
                          value={budgetUsd}
                          onChange={(e) => setBudgetUsd(Number(e.target.value))}
                          className="mt-2 w-full accent-[var(--accent-amber)]"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-[11px] font-medium text-[var(--text-secondary)] mb-1">
                        Optional Source Media Path
                      </label>
                      <div className="flex gap-1.5">
                        <input
                          value={sourceInput}
                          onChange={(e) => setSourceInput(e.target.value)}
                          placeholder="Optional footage URL or local path"
                          className="flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 py-1.5 text-xs"
                        />
                        <Button size="xs" variant="secondary" onClick={() => setBrowserOpen(true)}>
                          Browse
                        </Button>
                      </div>
                    </div>
                  </div>

                  <Button
                    variant="primary"
                    size="md"
                    className="w-full"
                    disabled={
                      launching ||
                      (!briefPrompt.trim() && !sourceInput.trim() && !referenceUrl.trim())
                    }
                    onClick={handleLaunch}
                  >
                    {launching ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Sparkles className="h-4 w-4" />
                    )}
                    Launch {selectedPipeline}
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </Panel>

      {/* Project Library Header + Filters */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <h2 className="text-sm font-semibold tracking-tight">Project Library</h2>
          <Badge tone="neutral" className="font-mono">
            {filteredProjects.length} / {projects.length}
          </Badge>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-[var(--text-muted)]" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Filter projects…"
              className="h-8 w-52 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] pl-8 pr-3 text-xs focus:border-[var(--accent-cyan)] focus:outline-none"
            />
          </div>
          <select
            aria-label="Filter by pipeline"
            value={pipelineFilter}
            onChange={(e) => setPipelineFilter(e.target.value)}
            className="h-8 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 text-xs"
          >
            <option value="all">All Pipelines</option>
            {productionPipelines.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
          </select>
          <Button variant="secondary" size="sm" onClick={() => loadProjects()}>
            Refresh
          </Button>
        </div>
      </div>

      {/* Project Grid */}
      {projectsLoading && projects.length === 0 ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-64 animate-pulse rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-surface)]"
            />
          ))}
        </div>
      ) : filteredProjects.length === 0 ? (
        <EmptyState
          icon={<Clapperboard className="h-5 w-5" />}
          title="No matching studio projects"
          description="Launch a new Clip Factory run or any of the 12 OpenMontage production pipelines above — every workspace automatically syncs live via SSE."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filteredProjects.map((project) => {
            const pid = project.project_id || project.id || '';
            return (
              <ProjectCard
                key={pid}
                project={project}
                onOpen={(tab) => navigate(`/project/${pid}/${tab}`)}
              />
            );
          })}
        </div>
      )}

      <LocalFileBrowserModal
        open={browserOpen}
        onClose={() => setBrowserOpen(false)}
        onSelect={(p) => setSourceInput(p)}
      />
    </div>
  );
}
