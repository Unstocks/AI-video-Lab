import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Check,
  CheckCircle2,
  Columns2,
  Crop,
  Film,
  Pause,
  Play,
  Redo2,
  RotateCcw,
  Scissors,
  ShieldAlert,
  Sparkles,
  Subtitles,
  Undo2,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { studioApi } from '@/lib/api';
import { cn, formatTimecode, lufsStatus, stripMediaPrefix } from '@/lib/format';
import {
  playbackHub,
  toast,
  useNleStore,
  useProjectStore,
  useSupervisorStore,
  useSystemStore,
} from '@/stores/useStudioStore';
import { Badge, Button, EmptyState, Panel } from '@/components/ui/Primitives';
import { CropCanvasOverlay } from '@/components/nle/CropCanvasOverlay';
import { MultiTrackTimeline } from '@/components/nle/MultiTrackTimeline';
import type { ClipStudioClip, LayoutRange, SubtitlePreset, TranscriptWord } from '@/types/studio';

function LiveSubtitlePreview({
  preset,
  text,
  isSplit,
}: {
  preset: SubtitlePreset | undefined;
  text: string;
  isSplit: boolean;
}) {
  if (!preset || !text.trim()) return null;
  const words = text.trim().split(/\s+/).slice(0, 5);
  const activeIdx = Math.min(1, Math.max(0, words.length - 1));
  return (
    <div
      className={cn(
        'pointer-events-none absolute inset-x-3 flex justify-center text-center',
        isSplit ? 'top-1/2 -translate-y-1/2' : 'bottom-[15%]',
      )}
    >
      <div
        style={{
          fontFamily: `"${preset.font_name}", "Noto Sans Devanagari", "Inter", sans-serif`,
          fontWeight: preset.bold ? 800 : 600,
          fontStyle: preset.italic ? 'italic' : 'normal',
          textTransform: preset.uppercase ? 'uppercase' : 'none',
          backgroundColor: preset.border_style === 3 ? preset.back_hex || 'rgba(0,0,0,0.75)' : 'transparent',
          textShadow:
            preset.border_style === 3
              ? 'none'
              : `0 2px ${Math.max(4, preset.outline * 2)}px ${preset.outline_hex || '#000'}, 0 0 2px #000`,
        }}
        className="inline-flex flex-wrap items-center justify-center gap-x-1.5 rounded-md px-2.5 py-1 text-base leading-tight tracking-tight"
      >
        {words.map((w, i) => (
          <span
            key={i}
            style={{
              color: i === activeIdx ? preset.active_hex : preset.primary_hex,
              transform: i === activeIdx ? `scale(${(preset.pop_scale_percent || 110) / 100})` : undefined,
            }}
            className="inline-block transition-transform"
          >
            {w}
          </span>
        ))}
      </div>
    </div>
  );
}

export function NleStudioWorkspace() {
  const { projectId } = useParams();
  const { presets } = useSystemStore();
  const {
    boardState,
    boardLoading,
    activeClipId,
    setActiveClipId,
    transcript,
    loadTranscript,
    waveforms,
    filmstrips,
    ensureWaveform,
    ensureFilmstrip,
  } = useProjectStore();
  const {
    previewMode,
    setPreviewMode,
    activePreset,
    setActivePreset,
    layoutMode,
    setLayoutMode,
    enablePunchIn,
    setEnablePunchIn,
    showSafeZones,
    setShowSafeZones,
    showSubtitlesOverlay,
    setShowSubtitlesOverlay,
    selectedRangeIdx,
    setSelectedRangeIdx,
    drafts,
    past,
    future,
    updateRangeOverride,
    undo,
    redo,
    recutStart,
    recutEnd,
    setRecutBounds,
  } = useNleStore();
  const { ensureSessionForProject, setRunning } = useSupervisorStore();

  const videoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [videoDuration, setVideoDuration] = useState(0);
  const [selectedBatch, setSelectedBatch] = useState<Record<string, boolean>>({});
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [cropEditMode, setCropEditMode] = useState<'single' | 'split'>('single');
  const [discoveredSourceRel, setDiscoveredSourceRel] = useState<string | null>(null);

  const clips: ClipStudioClip[] = useMemo(
    () => boardState?.clip_studio?.clips ?? [],
    [boardState],
  );
  const activeClip = useMemo(
    () => clips.find((c) => c.candidate_id === activeClipId) ?? clips[0] ?? null,
    [clips, activeClipId],
  );

  // Discover source/*.mp4 or renders/*.mp4 when clip_studio is not yet populated
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    studioApi
      .getProjectFiles(projectId)
      .then((res) => {
        if (cancelled) return;
        const vid =
          res.files.find((f) => f.rel_path.startsWith('renders/') && f.extension === 'mp4') ||
          res.files.find((f) => f.rel_path.startsWith('source/') && ['mp4', 'mov', 'webm'].includes(f.extension)) ||
          res.files.find((f) => ['mp4', 'mov', 'webm'].includes(f.extension));
        setDiscoveredSourceRel(vid ? vid.rel_path : null);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Fallback master video for early-stage or non-clip-factory projects
  const fallbackMasterUrl = useMemo(() => {
    const renders = boardState?.media?.renders || [];
    const firstRender = renders[0];
    if (firstRender?.url) return firstRender.url;
    if (firstRender?.rel_path && projectId) return `/media/${projectId}/${firstRender.rel_path}`;
    if (discoveredSourceRel && projectId) return `/media/${projectId}/${discoveredSourceRel}`;
    return null;
  }, [boardState, discoveredSourceRel, projectId]);

  const activeRenderUrl = activeClip?.render_url || fallbackMasterUrl || null;
  const activeSourceUrl =
    activeClip?.source_url ||
    boardState?.clip_studio?.source_url ||
    (discoveredSourceRel && projectId ? `/media/${projectId}/${discoveredSourceRel}` : null) ||
    activeRenderUrl;

  const activeMediaUrl =
    previewMode === 'source_crop' ? activeSourceUrl : activeRenderUrl || activeSourceUrl;

  const activeRelPath = useMemo(() => {
    if (!projectId) return null;
    const raw =
      (previewMode === 'source_crop' ? activeClip?.source_path || boardState?.clip_studio?.source_video : activeClip?.render_path) ||
      stripMediaPrefix(activeMediaUrl, projectId);
    return raw || null;
  }, [activeClip, activeMediaUrl, boardState, previewMode, projectId]);

  // Hydrate preset & recut bounds when active clip changes
  useEffect(() => {
    if (!activeClip) return;
    if (activeClip.style_preset) setActivePreset(activeClip.style_preset);
    setRecutBounds(activeClip.start_seconds ?? 0, activeClip.end_seconds ?? 0);
    const firstRange = activeClip.layout_sidecar?.ranges?.[0];
    setCropEditMode(firstRange?.layout === 'SPLIT' ? 'split' : 'single');
    setSelectedRangeIdx(0);
  }, [activeClip, setActivePreset, setRecutBounds, setSelectedRangeIdx]);

  // Load transcript, waveform & filmstrip
  useEffect(() => {
    if (!projectId) return;
    void loadTranscript(projectId, activeClip?.candidate_id);
  }, [projectId, activeClip?.candidate_id, loadTranscript]);

  useEffect(() => {
    if (!projectId || !activeRelPath) return;
    void ensureWaveform(projectId, activeRelPath);
    void ensureFilmstrip(projectId, activeRelPath);
  }, [projectId, activeRelPath, ensureWaveform, ensureFilmstrip]);

  // Sync video element <-> playbackHub
  useEffect(() => {
    const unsub = playbackHub.onSeekRequest((t) => {
      const v = videoRef.current;
      if (v && Number.isFinite(t)) {
        v.currentTime = t;
      }
    });
    return unsub;
  }, []);

  useEffect(() => {
    let raf = 0;
    const tick = () => {
      const v = videoRef.current;
      if (v) {
        playbackHub.emit(v.currentTime || 0, v.duration || 0, !v.paused);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const togglePlay = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      void v.play();
      setPlaying(true);
    } else {
      v.pause();
      setPlaying(false);
    }
  }, []);

  // Pro NLE Keyboard Shortcuts: J/K/L, Space, Ctrl+Z, Ctrl+Y
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
        e.preventDefault();
        redo();
        return;
      }
      if (e.code === 'Space' || e.key.toLowerCase() === 'k') {
        e.preventDefault();
        togglePlay();
      } else if (e.key.toLowerCase() === 'j') {
        e.preventDefault();
        playbackHub.requestSeek(Math.max(0, playbackHub.currentTime - 5));
      } else if (e.key.toLowerCase() === 'l') {
        e.preventDefault();
        playbackHub.requestSeek(playbackHub.currentTime + 5);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [redo, togglePlay, undo]);

  const layoutRanges: LayoutRange[] = activeClip?.layout_sidecar?.ranges ?? [];
  const punchIns = activeClip?.layout_sidecar?.punch_ins ?? [];
  const currentRangeKey = String(selectedRangeIdx);
  const activeDraftKey = activeClip?.candidate_id || 'source';
  const clipDrafts = drafts[activeDraftKey] || {};
  const activeRangeOverride = clipDrafts[currentRangeKey] || {};
  const activePresetObj = presets.find((p) => p.name === activePreset) ?? presets[0];

  const wfData = projectId && activeRelPath ? waveforms[`${projectId}:${activeRelPath}`] ?? null : null;
  const fsData = projectId && activeRelPath ? filmstrips[`${projectId}:${activeRelPath}`] ?? null : null;

  const dispatchAction = async (label: string, fn: (sid: string) => Promise<unknown>) => {
    if (!projectId) return;
    setBusyAction(label);
    try {
      const sid = await ensureSessionForProject(projectId);
      await fn(sid);
      setRunning(true);
      toast.success(label, 'Directive sent to Top Supervisor.');
    } catch (e) {
      toast.error(`${label} failed`, String(e));
    } finally {
      setBusyAction(null);
    }
  };

  const handleWordClick = (w: TranscriptWord, kind: 'in' | 'out') => {
    if (kind === 'in') {
      setRecutBounds(w.start, recutEnd && recutEnd > w.start ? recutEnd : w.end + 5);
    } else {
      setRecutBounds(recutStart != null && recutStart < w.end ? recutStart : Math.max(0, w.start - 5), w.end);
    }
  };

  const approvedSelectionIds = clips
    .filter((c) => selectedBatch[c.candidate_id])
    .map((c) => c.candidate_id);

  if (boardLoading && !boardState) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-[var(--text-muted)]">
        Loading NLE Workstation…
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Main 3-Column NLE Upper Deck */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Left Rail: Clip Candidates */}
        <div className="hidden lg:flex w-64 shrink-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-surface)]">
          <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-3 py-2.5">
            <div className="flex items-center gap-1.5">
              <Scissors className="h-3.5 w-3.5 text-[var(--accent-amber)]" />
              <span className="text-xs font-semibold">Clip Candidates</span>
            </div>
            <Badge tone="neutral" className="font-mono">
              {clips.length}
            </Badge>
          </div>

          <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
            {clips.length === 0 ? (
              <div className="p-3 text-center text-[11px] text-[var(--text-muted)]">
                No clip-factory candidates yet. Playing master project media if available.
              </div>
            ) : (
              clips.map((c) => {
                const isSel = activeClip?.candidate_id === c.candidate_id;
                const checked = Boolean(selectedBatch[c.candidate_id]);
                const qaOk = c.qa_report?.passed || c.production_state === 'QA_PASSED';
                return (
                  <div
                    key={c.candidate_id}
                    onClick={() => setActiveClipId(c.candidate_id)}
                    className={cn(
                      'rounded-xl border p-2.5 cursor-pointer transition-all',
                      isSel
                        ? 'border-[var(--accent-amber)] bg-[var(--accent-amber-soft)]/60'
                        : 'border-[var(--border-subtle)] bg-[var(--bg-canvas)]/50 hover:border-[var(--border-strong)]',
                    )}
                  >
                    <div className="flex items-center justify-between gap-1.5">
                      <label
                        className="flex items-center gap-1.5 cursor-pointer"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={(e) =>
                            setSelectedBatch((s) => ({ ...s, [c.candidate_id]: e.target.checked }))
                          }
                          className="h-3.5 w-3.5 accent-[var(--accent-amber)]"
                        />
                        <span className="font-mono text-[11px] font-bold text-[var(--text-primary)]">
                          {c.candidate_id}
                        </span>
                      </label>
                      {c.virality_score != null && (
                        <Badge tone="amber" className="font-mono">
                          {Math.round(c.virality_score)}
                        </Badge>
                      )}
                    </div>

                    <p className="mt-1 line-clamp-2 text-[11px] text-[var(--text-secondary)] leading-snug">
                      {c.spoken_hook || c.hook_text || c.title || 'Untitled clip'}
                    </p>

                    <div className="mt-2 flex flex-wrap items-center justify-between gap-1 font-mono text-[10px] text-[var(--text-muted)]">
                      <span>
                        {formatTimecode(c.start_seconds, false)}–{formatTimecode(c.end_seconds, false)}
                      </span>
                      <Badge tone={qaOk ? 'pass' : c.review_state === 'HUMAN_APPROVED' ? 'cyan' : 'neutral'}>
                        {qaOk ? 'QA PASS' : c.review_state || 'REVIEW'}
                      </Badge>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {clips.length > 0 && (
            <div className="border-t border-[var(--border-subtle)] p-2.5 space-y-1.5">
              <Button
                variant="primary"
                size="xs"
                className="w-full"
                disabled={busyAction !== null || approvedSelectionIds.length === 0}
                onClick={() =>
                  dispatchAction('Approve & Render Clips', (sid) =>
                    studioApi.approveClips(sid, {
                      approved_ids: approvedSelectionIds,
                      rejected_ids: clips
                        .filter((c) => !selectedBatch[c.candidate_id])
                        .map((c) => c.candidate_id),
                      style_preset: activePreset,
                      layout_mode: layoutMode,
                      enable_punch_in: enablePunchIn,
                      project_id: projectId,
                    }),
                  )
                }
              >
                <CheckCircle2 className="h-3.5 w-3.5" />
                Approve &amp; Render ({approvedSelectionIds.length})
              </Button>
            </div>
          )}
        </div>

        {/* Center Preview Monitor Stage */}
        <div className="flex min-w-0 flex-1 flex-col bg-[var(--bg-canvas)]">
          {/* Monitor Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2">
            <div className="flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-0.5">
              {(
                [
                  ['rendered', '9:16 Master', Film],
                  ['source_crop', '16:9 Crop Editor', Crop],
                  ['compare', 'Split Compare', Columns2],
                ] as const
              ).map(([id, label, Icon]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setPreviewMode(id)}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium transition-all cursor-pointer',
                    previewMode === id
                      ? 'bg-[var(--bg-elevated)] text-[var(--text-primary)] shadow-xs'
                      : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]',
                  )}
                >
                  <Icon className="h-3 w-3" />
                  {label}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-1.5">
              {previewMode === 'source_crop' && (
                <>
                  <Button
                    size="xs"
                    variant={cropEditMode === 'single' ? 'cyan' : 'secondary'}
                    onClick={() => setCropEditMode('single')}
                  >
                    Single 9:16
                  </Button>
                  <Button
                    size="xs"
                    variant={cropEditMode === 'split' ? 'cyan' : 'secondary'}
                    onClick={() => setCropEditMode('split')}
                  >
                    2-Speaker Split
                  </Button>
                  <Button size="xs" variant="ghost" disabled={past.length === 0} onClick={undo} title="Undo (Ctrl+Z)">
                    <Undo2 className="h-3.5 w-3.5" />
                  </Button>
                  <Button size="xs" variant="ghost" disabled={future.length === 0} onClick={redo} title="Redo (Ctrl+Y)">
                    <Redo2 className="h-3.5 w-3.5" />
                  </Button>
                </>
              )}
              <Button
                size="xs"
                variant={showSafeZones ? 'cyan' : 'ghost'}
                onClick={() => setShowSafeZones(!showSafeZones)}
                title="Toggle TikTok/Reels/Shorts Safe Zones"
              >
                <ShieldAlert className="h-3.5 w-3.5" />
                Safe Zones
              </Button>
              <Button
                size="xs"
                variant={showSubtitlesOverlay ? 'cyan' : 'ghost'}
                onClick={() => setShowSubtitlesOverlay(!showSubtitlesOverlay)}
                title="Toggle Live 8-Preset Subtitle Preview"
              >
                <Subtitles className="h-3.5 w-3.5" />
                Subs
              </Button>
            </div>
          </div>

          {/* Monitor Canvas */}
          <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden p-4">
            {activeMediaUrl ? (
              <div
                className={cn(
                  'relative flex items-center justify-center gap-4 h-full max-h-full',
                  previewMode === 'compare' ? 'w-full' : '',
                )}
              >
                {/* Primary Video Frame */}
                <div
                  className={cn(
                    'relative overflow-hidden rounded-xl border border-[var(--border-strong)] bg-black shadow-[var(--shadow-panel)]',
                    previewMode === 'source_crop'
                      ? 'aspect-video max-h-full max-w-full'
                      : 'aspect-[9/16] h-full max-h-[520px]',
                  )}
                >
                  <video
                    ref={videoRef}
                    src={activeMediaUrl}
                    muted={muted}
                    playsInline
                    onLoadedMetadata={(e) => setVideoDuration(e.currentTarget.duration || 0)}
                    onPlay={() => setPlaying(true)}
                    onPause={() => setPlaying(false)}
                    className="h-full w-full object-contain"
                  />

                  {/* Interactive On-Canvas Crop Editor (16:9 mode) */}
                  {previewMode === 'source_crop' && (
                    <CropCanvasOverlay
                      mode={cropEditMode}
                      override={activeRangeOverride}
                      showSafeZones={showSafeZones}
                      onChange={(entry) =>
                        updateRangeOverride(activeDraftKey, currentRangeKey, entry)
                      }
                    />
                  )}

                  {/* Safe zones overlay in 9:16 mode */}
                  {previewMode !== 'source_crop' && showSafeZones && (
                    <div className="pointer-events-none absolute inset-0">
                      <div className="absolute inset-x-0 top-0 h-[13%] bg-red-500/20 border-b border-dashed border-red-400/70 flex items-end justify-center pb-1 font-mono text-[9px] text-red-200">
                        TOP SAFE ZONE
                      </div>
                      <div className="absolute inset-x-0 bottom-0 h-[22%] bg-red-500/20 border-t border-dashed border-red-400/70 flex items-start justify-center pt-1 font-mono text-[9px] text-red-200">
                        CAPTION / UI DANGER ZONE
                      </div>
                      <div className="absolute right-0 top-[13%] bottom-[22%] w-[16%] bg-red-500/15 border-l border-dashed border-red-400/60" />
                    </div>
                  )}

                  {/* Live WYSIWYG Subtitle Overlay */}
                  {previewMode !== 'source_crop' && showSubtitlesOverlay && (
                    <LiveSubtitlePreview
                      preset={activePresetObj}
                      text={
                        activeClip?.spoken_hook ||
                        activeClip?.hook_text ||
                        transcript?.words?.slice(0, 5).map((w) => w.word).join(' ') ||
                        'Broadcast 8-Preset Live Preview'
                      }
                      isSplit={layoutRanges[selectedRangeIdx]?.layout === 'SPLIT'}
                    />
                  )}
                </div>

                {/* Compare Mode Second Monitor (Source 16:9 beside 9:16 Master) */}
                {previewMode === 'compare' && activeSourceUrl && (
                  <div className="relative aspect-video max-h-[380px] flex-1 overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-black">
                    <video
                      src={activeSourceUrl}
                      muted
                      controls
                      className="h-full w-full object-contain"
                    />
                    <div className="absolute left-2 top-2 rounded bg-black/70 px-2 py-0.5 font-mono text-[10px] text-zinc-200">
                      16:9 SOURCE
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <EmptyState
                icon={<Film className="h-5 w-5" />}
                title="No rendered video yet"
                description="Once a clip or master video is rendered into renders/ or source/, this broadcast monitor activates with live 60fps scrubbing, waveform, filmstrip, and on-canvas Reframe v2 crop handles."
              />
            )}
          </div>

          {/* Transport Controls Bar */}
          <div className="flex items-center justify-between border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-1.5 text-xs">
            <div className="flex items-center gap-1.5">
              <Button size="xs" variant="ghost" onClick={() => playbackHub.requestSeek(0)} title="Return to start">
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
              <Button size="xs" variant="primary" onClick={togglePlay} aria-label={playing ? 'Pause' : 'Play'}>
                {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5 fill-current" />}
                {playing ? 'Pause' : 'Play'}
              </Button>
              <Button
                size="xs"
                variant="ghost"
                onClick={() => setMuted((m) => !m)}
                aria-label={muted ? 'Unmute' : 'Mute'}
              >
                {muted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
              </Button>
            </div>

            <div className="hidden sm:flex items-center gap-2 font-mono text-[10px] text-[var(--text-muted)]">
              <span>J −5s</span>
              <span>·</span>
              <span>Space/K Play</span>
              <span>·</span>
              <span>L +5s</span>
              <span>·</span>
              <span>Ctrl+Z Undo</span>
            </div>
          </div>
        </div>

        {/* Right NLE Inspector */}
        <div className="hidden xl:flex w-72 shrink-0 flex-col border-l border-[var(--border-subtle)] bg-[var(--bg-surface)] overflow-y-auto p-3.5 space-y-4">
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold">Subtitle Style Preset</span>
              <Badge tone="neutral" className="font-mono text-[10px]">
                {activePreset}
              </Badge>
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {presets.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => setActivePreset(p.name)}
                  className={cn(
                    'rounded-lg border p-2 text-left transition-all cursor-pointer',
                    activePreset === p.name
                      ? 'border-[var(--accent-amber)] bg-[var(--accent-amber-soft)]'
                      : 'border-[var(--border-subtle)] bg-[var(--bg-canvas)]/50 hover:border-[var(--border-strong)]',
                  )}
                >
                  <div
                    className="truncate text-[11px] font-bold"
                    style={{
                      fontFamily: `"${p.font_name}", "Inter", sans-serif`,
                      color: p.active_hex || '#facc15',
                    }}
                  >
                    {p.display_name}
                  </div>
                  <div className="truncate font-mono text-[9px] text-[var(--text-muted)]">
                    {p.font_name}
                  </div>
                </button>
              ))}
            </div>
            {activeClip && (
              <Button
                variant="secondary"
                size="xs"
                className="mt-2 w-full"
                disabled={busyAction !== null}
                onClick={() =>
                  dispatchAction('Burn Style Preset', (sid) =>
                    studioApi.changeStylePreset(sid, {
                      candidate_id: activeClip.candidate_id,
                      style_preset: activePreset,
                      layout_mode: layoutMode,
                      project_id: projectId,
                    }),
                  )
                }
              >
                <Sparkles className="h-3 w-3 text-[var(--accent-amber)]" />
                Re-Render with “{activePreset}”
              </Button>
            )}
          </div>

          <div className="border-t border-[var(--border-subtle)] pt-3 space-y-2.5">
            <div className="text-xs font-semibold">Reframe v2 &amp; Framing</div>
            <select
              aria-label="Layout mode override"
              value={layoutMode}
              onChange={(e) => setLayoutMode(e.target.value as typeof layoutMode)}
              className="w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 py-1.5 text-xs"
            >
              <option value="auto">Auto (YuNet + Split)</option>
              <option value="stacked_split">Stacked 2-Speaker Split</option>
              <option value="single_crop">Single Active Track</option>
              <option value="speaker_cut">Fast Speaker Cut</option>
              <option value="blurred_pillarbox">Blurred Pillarbox</option>
            </select>

            <label className="flex items-center justify-between text-xs text-[var(--text-secondary)] cursor-pointer">
              <span>Emphasis Punch-In (1.15x)</span>
              <input
                type="checkbox"
                checked={enablePunchIn}
                onChange={(e) => setEnablePunchIn(e.target.checked)}
                className="h-3.5 w-3.5 accent-[var(--accent-amber)]"
              />
            </label>

            {activeClip && (
              <Button
                variant="cyan"
                size="xs"
                className="w-full"
                disabled={busyAction !== null}
                onClick={() =>
                  dispatchAction('Apply Crop Override', (sid) =>
                    studioApi.reframeClip(sid, {
                      candidate_id: activeClip.candidate_id,
                      crop_overrides: clipDrafts,
                      project_id: projectId,
                      style_preset: activePreset,
                      enable_punch_in: enablePunchIn,
                    }),
                  )
                }
              >
                <Crop className="h-3.5 w-3.5" />
                Apply Crop &amp; Re-Render
              </Button>
            )}
          </div>

          {/* Word-Snapped Recut Commit */}
          {activeClip && recutStart != null && recutEnd != null && recutEnd > recutStart && (
            <div className="border-t border-[var(--border-subtle)] pt-3 space-y-2">
              <div className="text-xs font-semibold">Word-Snapped Recut</div>
              <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
                <div className="rounded border border-[var(--border-subtle)] bg-[var(--bg-canvas)] px-2 py-1">
                  IN: {formatTimecode(recutStart)}
                </div>
                <div className="rounded border border-[var(--border-subtle)] bg-[var(--bg-canvas)] px-2 py-1">
                  OUT: {formatTimecode(recutEnd)}
                </div>
              </div>
              <Button
                variant="secondary"
                size="xs"
                className="w-full"
                disabled={busyAction !== null}
                onClick={() =>
                  dispatchAction('Commit Word-Snapped Recut', (sid) =>
                    studioApi.recutClip(sid, {
                      candidate_id: activeClip.candidate_id,
                      start_seconds: recutStart,
                      end_seconds: recutEnd,
                      project_id: projectId,
                      style_preset: activePreset,
                      layout_mode: layoutMode,
                    }),
                  )
                }
              >
                <Check className="h-3.5 w-3.5" />
                Commit Recut ({(recutEnd - recutStart).toFixed(1)}s)
              </Button>
            </div>
          )}

          {/* Quick Clip Telemetry */}
          {activeClip?.qa_report && (
            <Panel className="p-2.5 bg-[var(--bg-canvas)]/60 space-y-1.5 text-[11px]">
              <div className="font-semibold text-[var(--text-secondary)]">Broadcast Probe</div>
              <div className="flex justify-between font-mono text-[10px]">
                <span className="text-[var(--text-muted)]">Resolution</span>
                <span>
                  {activeClip.qa_report.technical_probe?.width || '—'}×
                  {activeClip.qa_report.technical_probe?.height || '—'}
                </span>
              </div>
              <div className="flex justify-between font-mono text-[10px]">
                <span className="text-[var(--text-muted)]">Loudness</span>
                <span
                  className={cn(
                    lufsStatus(activeClip.qa_report.audio_spotcheck?.integrated_lufs) === 'pass'
                      ? 'text-[var(--status-pass)]'
                      : 'text-[var(--status-warn)]',
                  )}
                >
                  {activeClip.qa_report.audio_spotcheck?.integrated_lufs != null
                    ? `${activeClip.qa_report.audio_spotcheck.integrated_lufs.toFixed(1)} LUFS`
                    : '—'}
                </span>
              </div>
            </Panel>
          )}
        </div>
      </div>

      {/* Bottom Full-Width Multi-Track NLE Timeline */}
      <MultiTrackTimeline
        duration={videoDuration || activeClip?.duration_seconds || 0}
        clipStartOffset={activeClip?.start_seconds || 0}
        waveform={wfData}
        filmstrip={fsData}
        layoutRanges={layoutRanges}
        punchIns={punchIns}
        transcriptWords={transcript?.words ?? []}
        onSelectRange={(idx, r) => {
          setSelectedRangeIdx(idx);
          setCropEditMode(r.layout === 'SPLIT' ? 'split' : 'single');
        }}
        onWordClick={handleWordClick}
      />
    </div>
  );
}
