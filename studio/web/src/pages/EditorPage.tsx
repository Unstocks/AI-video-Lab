import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  Columns2,
  Crop,
  Film,
  Pause,
  Play,
  RotateCcw,
  ShieldAlert,
  SkipBack,
  SkipForward,
  Subtitles,
  Volume2,
  VolumeX,
} from 'lucide-react';
import { buildMediaUrl, studioApi } from '@/lib/api';
import { DEMO_DURATION, DEMO_WAVEFORM_PEAKS } from '@/data/demoProjectSeed';
import { cn } from '@/lib/format';
import {
  playbackHub,
  toast,
  useNleStore,
  useProjectStore,
  useSupervisorStore,
  useSystemStore,
} from '@/stores/useStudioStore';
import { useEditorStore } from '@/stores/useEditorStore';
import { ToolRail } from '@/components/editor/ToolRail';
import { ToolPanelRouter } from '@/components/editor/ToolPanelRouter';
import { SelectionOverlay } from '@/components/editor/stage/SelectionOverlay';
import { CropCanvasOverlay } from '@/components/nle/CropCanvasOverlay';
import { CreatorTimeline } from '@/components/editor/timeline/CreatorTimeline';
import { Button } from '@/components/ui/Primitives';
import type { ClipStudioClip, LayoutRange } from '@/types/studio';

export function EditorPage() {
  const { projectId = 'demo' } = useParams();
  const { presets, setDockOpen } = useSystemStore();
  const {
    boardState,
    activeClipId,
    loadTranscript,
    waveforms,
    filmstrips,
    ensureWaveform,
    ensureFilmstrip,
  } = useProjectStore();
  const {
    selectedRangeIdx,
    setSelectedRangeIdx,
    showSafeZones,
    setShowSafeZones,
    drafts,
    updateRangeOverride,
  } = useNleStore();
  const { ensureSessionForProject, setRunning } = useSupervisorStore();
  const {
    aspectRatio,
    canvasBg,
    stageViewMode,
    setStageViewMode,
    showSubtitles,
    setShowSubtitles,
    captions,
    activeCaptionId,
    setActiveCaptionId,
    activeSubtitlePreset,
    subtitleBox,
    updateSubtitleBox,
    textOverlays,
    updateTextOverlay,
    deleteTextOverlay,
    selection,
    setSelection,
    cutRanges,
    aiTools,
  } = useEditorStore();

  const videoRef = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [videoDuration, setVideoDuration] = useState(0);
  const [discoveredSourceRel, setDiscoveredSourceRel] = useState<string | null>(null);
  const [cropEditMode, setCropEditMode] = useState<'single' | 'split' | 'general'>('single');
  const [applyingCrop, setApplyingCrop] = useState(false);

  const clips: ClipStudioClip[] = useMemo(
    () => boardState?.clip_studio?.clips ?? [],
    [boardState],
  );
  const activeClip = useMemo(
    () => clips.find((c) => c.candidate_id === activeClipId) ?? clips[0] ?? null,
    [clips, activeClipId],
  );

  // Discover fallback video file when clip_studio is not populated yet
  useEffect(() => {
    if (!projectId || projectId === 'demo') {
      setDiscoveredSourceRel(null);
      return;
    }
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

  // Exact backlot/state.py media paths + video_mtime cache-busting (DRIFT-02 fixed!)
  const renderRelPath =
    activeClip?.video_path ||
    boardState?.media?.renders?.[0]?.path ||
    discoveredSourceRel ||
    null;
  const sourceRelPath =
    boardState?.clip_studio?.source_video || discoveredSourceRel || renderRelPath;

  const activeRelPath =
    stageViewMode === 'reframe_crop' ? sourceRelPath : renderRelPath || sourceRelPath;

  const activeMediaUrl = useMemo(() => {
    if (projectId === 'demo' || !activeRelPath) return null;
    const mtime =
      activeRelPath === activeClip?.video_path
        ? activeClip?.video_mtime
        : boardState?.media?.renders?.find((r) => r.path === activeRelPath)?.mtime;
    return buildMediaUrl(projectId, activeRelPath, mtime);
  }, [activeClip, activeRelPath, boardState, projectId]);

  const sourceMediaUrl = useMemo(() => {
    if (projectId === 'demo' || !sourceRelPath) return null;
    return buildMediaUrl(projectId, sourceRelPath);
  }, [projectId, sourceRelPath]);

  // Load real transcript, waveform & inline filmstrip
  useEffect(() => {
    if (!projectId || projectId === 'demo') return;
    void loadTranscript(projectId, activeClip?.candidate_id);
  }, [projectId, activeClip?.candidate_id, loadTranscript]);

  useEffect(() => {
    if (!projectId || projectId === 'demo' || !activeRelPath) return;
    void ensureWaveform(projectId, activeRelPath);
    void ensureFilmstrip(projectId, activeRelPath);
  }, [projectId, activeRelPath, ensureWaveform, ensureFilmstrip]);

  // Sync video <-> playbackHub + skip deleted Script cut ranges during playback
  useEffect(() => {
    return playbackHub.onSeekRequest((t) => {
      const v = videoRef.current;
      if (v && Number.isFinite(t)) {
        v.currentTime = t;
      }
    });
  }, []);

  useEffect(() => {
    let raf = 0;
    let demoStartWall = performance.now();
    let demoBaseTime = playbackHub.currentTime;

    const tick = () => {
      const v = videoRef.current;
      if (v && activeMediaUrl) {
        let t = v.currentTime || 0;
        const d = v.duration || 0;
        // Skip deleted script cut ranges during playback
        if (!v.paused && cutRanges.length > 0) {
          const hitCut = cutRanges.find((r) => t >= r.start && t < r.end - 0.05);
          if (hitCut) {
            v.currentTime = hitCut.end + 0.02;
            t = v.currentTime;
          }
        }
        playbackHub.emit(t, d, !v.paused);
      } else if (playing) {
        // Demo sandbox virtual clock
        const elapsed = (performance.now() - demoStartWall) / 1000;
        let nextT = (demoBaseTime + elapsed) % DEMO_DURATION;
        const hitCut = cutRanges.find((r) => nextT >= r.start && nextT < r.end - 0.05);
        if (hitCut) {
          nextT = hitCut.end + 0.02;
          demoBaseTime = nextT;
          demoStartWall = performance.now();
        }
        playbackHub.emit(nextT, DEMO_DURATION, true);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [activeMediaUrl, cutRanges, playing]);

  const togglePlay = useCallback(() => {
    const v = videoRef.current;
    if (v && activeMediaUrl) {
      if (v.paused) {
        void v.play();
        setPlaying(true);
      } else {
        v.pause();
        setPlaying(false);
      }
    } else {
      setPlaying((p) => !p);
    }
  }, [activeMediaUrl]);

  // Keyboard playback shortcuts (J/K/L, Space)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
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
  }, [togglePlay]);

  const layoutRanges: LayoutRange[] = activeClip?.layout_ranges ?? [];
  const punchIns: number[] = activeClip?.punch_ins ?? [];
  const activeDraftKey = activeClip?.candidate_id || 'source';
  const clipDrafts = drafts[activeDraftKey] || {};
  const currentRangeKey = String(selectedRangeIdx);
  const activeRangeOverride = clipDrafts[currentRangeKey];

  const activePresetObj =
    presets.find((p) => p.name === activeSubtitlePreset) ?? presets[0];

  const activeCaption =
    captions.find((c) => c.id === activeCaptionId) ?? captions[0] ?? null;

  // Exact lowercase 'split' check (DRIFT-04 fixed!)
  const isSplitSeam =
    aiTools.seamSubtitles &&
    (layoutRanges[selectedRangeIdx]?.layout === 'split' ||
      activeCaption?.styleName === 'Seam');

  const wfData =
    projectId !== 'demo' && activeRelPath
      ? waveforms[`${projectId}:${activeRelPath}`] ?? null
      : null;
  const fsData =
    projectId !== 'demo' && activeRelPath
      ? filmstrips[`${projectId}:${activeRelPath}`] ?? null
      : null;

  const totalDuration =
    videoDuration ||
    wfData?.duration_seconds ||
    fsData?.duration_seconds ||
    activeClip?.duration_seconds ||
    DEMO_DURATION;

  const aspectClass =
    stageViewMode === 'reframe_crop'
      ? 'aspect-video max-w-full max-h-full'
      : aspectRatio === '16:9'
        ? 'aspect-video w-full max-w-[680px]'
        : aspectRatio === '1:1'
          ? 'aspect-square h-full max-h-[440px]'
          : aspectRatio === '4:5'
            ? 'aspect-[4/5] h-full max-h-[460px]'
            : 'aspect-[9/16] h-full max-h-[470px]';

  const handleApplyCrop = async () => {
    if (projectId === 'demo') {
      toast.info('Demo crop preview updated', 'Open a real project to re-render via Reframe v2.');
      return;
    }
    setApplyingCrop(true);
    try {
      await studioApi.saveCropDraft(projectId, activeDraftKey, clipDrafts);
      if (activeClip) {
        const sid = await ensureSessionForProject(projectId);
        await studioApi.reframeClip(sid, {
          candidate_id: activeClip.candidate_id,
          crop_overrides: clipDrafts,
          project_id: projectId,
          style_preset: activeSubtitlePreset,
          enable_punch_in: aiTools.enablePunchIn,
        });
        setRunning(true);
        setDockOpen(true);
        toast.success('Reframe v2 override dispatched', 'Exact center-point crop sent to Producer.');
      } else {
        toast.success('Crop draft saved', 'Stored in .studio/sessions.sqlite');
      }
    } catch (e) {
      toast.error('Reframe override failed', String(e));
    } finally {
      setApplyingCrop(false);
    }
  };

  return (
    <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
      {/* Fixed 68px Left Tool Rail */}
      <ToolRail />

      {/* Contextual Left Tool Panel (364px default -> 512px for Script) */}
      <ToolPanelRouter duration={totalDuration} />

      {/* Center Flexible Stage + Lower Multi-Track Timeline */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[var(--bg-canvas)]">
        {/* Stage Mode & Reframe Controls Sub-Bar */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-1.5">
          <div className="flex items-center gap-1 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-0.5">
            {(
              [
                ['preview', 'Preview', Film],
                ['reframe_crop', '16:9 Reframe Crop', Crop],
                ['split_compare', 'Split Compare', Columns2],
              ] as const
            ).map(([id, label, Icon]) => (
              <button
                key={id}
                type="button"
                onClick={() => setStageViewMode(id)}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold transition-all cursor-pointer',
                  stageViewMode === id
                    ? 'bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-2xs'
                    : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]',
                )}
              >
                <Icon className="h-3 w-3" />
                <span>{label}</span>
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1.5">
            {stageViewMode === 'reframe_crop' && (
              <>
                <Button
                  size="xs"
                  variant={cropEditMode === 'single' ? 'lime' : 'secondary'}
                  onClick={() => {
                    setCropEditMode('single');
                    updateRangeOverride(activeDraftKey, currentRangeKey, { x: 0.5 });
                  }}
                >
                  Single 9:16
                </Button>
                <Button
                  size="xs"
                  variant={cropEditMode === 'split' ? 'lime' : 'secondary'}
                  onClick={() => {
                    setCropEditMode('split');
                    updateRangeOverride(activeDraftKey, currentRangeKey, {
                      top: { x: 0.28, y: 0.48 },
                      bottom: { x: 0.72, y: 0.48 },
                    });
                  }}
                >
                  2-Speaker Split
                </Button>
                <Button
                  size="xs"
                  variant={cropEditMode === 'general' ? 'lime' : 'secondary'}
                  onClick={() => {
                    setCropEditMode('general');
                    updateRangeOverride(activeDraftKey, currentRangeKey, { layout: 'general' });
                  }}
                >
                  General Blur
                </Button>
                <Button
                  size="xs"
                  variant="primary"
                  disabled={applyingCrop}
                  onClick={() => void handleApplyCrop()}
                >
                  Apply Crop
                </Button>
              </>
            )}

            <Button
              size="xs"
              variant={showSafeZones ? 'lime' : 'ghost'}
              onClick={() => setShowSafeZones(!showSafeZones)}
              title="Toggle mobile safe zones"
            >
              <ShieldAlert className="h-3.5 w-3.5" />
              Safe Zones
            </Button>

            <Button
              size="xs"
              variant={showSubtitles ? 'lime' : 'ghost'}
              onClick={() => setShowSubtitles(!showSubtitles)}
              title="Toggle live subtitle overlay"
            >
              <Subtitles className="h-3.5 w-3.5" />
              Subs
            </Button>
          </div>
        </div>

        {/* Flexible Preview Canvas Stage */}
        <div
          onClick={() => setSelection(null)}
          className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden p-4"
        >
          <div className="flex h-full max-h-full w-full items-center justify-center gap-4">
            {/* Primary Preview Frame */}
            <div
              style={{ backgroundColor: canvasBg }}
              className={cn(
                'relative overflow-hidden rounded-[14px] border border-[var(--border-strong)] shadow-[var(--shadow-panel)]',
                aspectClass,
              )}
            >
              {activeMediaUrl ? (
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
              ) : (
                /* Local Speaker Portrait Stage Backdrop for Demo Sandbox (zero external assets) */
                <div
                  className="flex h-full w-full flex-col items-center justify-center p-6 text-center"
                  style={{
                    background:
                      'radial-gradient(circle at 50% 35%, #334155 0%, #1e293b 48%, #0f172a 100%)',
                  }}
                >
                  <div className="h-24 w-24 rounded-full border-2 border-white/25 bg-gradient-to-b from-amber-200/80 to-amber-300/50 shadow-lg" />
                  <div className="mt-2 h-24 w-44 rounded-t-[44px] bg-gradient-to-b from-slate-600/80 to-slate-900/90 border-t border-white/15" />
                  <div className="mt-3 rounded-full bg-black/50 px-3 py-1 font-mono text-[10px] text-white/75">
                    Interactive Creator Preview · {aspectRatio}
                  </div>
                </div>
              )}

              {/* Mode 1: Interactive Draggable / Resizable / Rotatable Subtitle & Text Overlay */}
              {stageViewMode !== 'reframe_crop' && (
                <SelectionOverlay
                  activeSubtitleText={showSubtitles ? activeCaption?.text ?? null : null}
                  activeSubtitleId={activeCaption?.id ?? null}
                  preset={activePresetObj}
                  isSplitSeam={isSplitSeam}
                  subtitleBox={subtitleBox}
                  subtitleSelected={selection?.kind === 'subtitle'}
                  onSelectSubtitle={() =>
                    setSelection({ kind: 'subtitle', id: activeCaption?.id || 'sub' })
                  }
                  onChangeSubtitleBox={(patch, commit) => updateSubtitleBox(patch, commit)}
                  textOverlays={textOverlays}
                  selectedTextId={selection?.kind === 'text' ? selection.id : null}
                  onSelectText={(id) => setSelection({ kind: 'text', id })}
                  onChangeText={(id, patch, commit) => updateTextOverlay(id, patch, commit)}
                  onDeleteText={(id) => deleteTextOverlay(id)}
                />
              )}

              {/* Mode 2: Fixed Aspect-Locked Reframe v2 Crop Editor */}
              {stageViewMode === 'reframe_crop' && (
                <CropCanvasOverlay
                  mode={cropEditMode}
                  override={activeRangeOverride}
                  showSafeZones={showSafeZones}
                  onChange={(entry) =>
                    updateRangeOverride(activeDraftKey, currentRangeKey, entry)
                  }
                />
              )}

              {/* Safe Zones Overlay */}
              {stageViewMode !== 'reframe_crop' && showSafeZones && (
                <div className="pointer-events-none absolute inset-0 z-10">
                  <div className="absolute inset-x-0 top-0 flex h-[13%] items-end justify-center border-b border-dashed border-red-400/80 bg-red-500/20 pb-1 font-mono text-[9px] text-red-100">
                    TOP SAFE ZONE
                  </div>
                  <div className="absolute inset-x-0 bottom-0 flex h-[22%] items-start justify-center border-t border-dashed border-red-400/80 bg-red-500/20 pt-1 font-mono text-[9px] text-red-100">
                    UI / CAPTION DANGER ZONE
                  </div>
                  <div className="absolute bottom-[22%] right-0 top-[13%] w-[16%] border-l border-dashed border-red-400/70 bg-red-500/15" />
                </div>
              )}
            </div>

            {/* Split Compare Second Monitor */}
            {stageViewMode === 'split_compare' && sourceMediaUrl && (
              <div className="relative aspect-video max-h-[360px] flex-1 overflow-hidden rounded-[14px] border border-[var(--border-subtle)] bg-black">
                <video
                  src={sourceMediaUrl}
                  muted
                  controls
                  className="h-full w-full object-contain"
                />
                <span className="absolute left-2.5 top-2.5 rounded bg-black/75 px-2 py-0.5 font-mono text-[10px] text-white">
                  16:9 SOURCE
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Preview Control Bar */}
        <div className="flex items-center justify-between border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-1.5">
          <div className="flex items-center gap-1.5">
            <Button
              size="xs"
              variant="ghost"
              aria-label="Return to start"
              onClick={() => playbackHub.requestSeek(0)}
            >
              <RotateCcw className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="xs"
              variant="ghost"
              aria-label="Back 5 seconds"
              onClick={() => playbackHub.requestSeek(Math.max(0, playbackHub.currentTime - 5))}
            >
              <SkipBack className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="xs"
              variant="primary"
              onClick={togglePlay}
              aria-label={playing ? 'Pause' : 'Play'}
              className="rounded-full px-3.5"
            >
              {playing ? (
                <Pause className="h-3.5 w-3.5" />
              ) : (
                <Play className="h-3.5 w-3.5 fill-current" />
              )}
              {playing ? 'Pause' : 'Play'}
            </Button>
            <Button
              size="xs"
              variant="ghost"
              aria-label="Forward 5 seconds"
              onClick={() => playbackHub.requestSeek(playbackHub.currentTime + 5)}
            >
              <SkipForward className="h-3.5 w-3.5" />
            </Button>
            <Button
              size="xs"
              variant="ghost"
              aria-label={muted ? 'Unmute' : 'Mute'}
              onClick={() => setMuted((m) => !m)}
            >
              {muted ? <VolumeX className="h-3.5 w-3.5" /> : <Volume2 className="h-3.5 w-3.5" />}
            </Button>
          </div>

          <div className="hidden sm:flex items-center gap-2 font-mono text-[10px] text-[var(--text-muted)]">
            <span>Space/K Play</span>
            <span>·</span>
            <span>J/L ±5s</span>
            <span>·</span>
            <span>Ctrl+Z Undo</span>
            <span>·</span>
            <span>Ctrl+J Producer</span>
          </div>
        </div>

        {/* Lower Multi-Track Creator Timeline (Purple Subtitle Track + Filmstrip + Waveform) */}
        <CreatorTimeline
          duration={totalDuration}
          waveform={wfData}
          filmstrip={fsData}
          layoutRanges={layoutRanges}
          punchIns={punchIns}
          fallbackPeaks={projectId === 'demo' ? DEMO_WAVEFORM_PEAKS : undefined}
          onSelectRange={(idx, range: LayoutRange) => {
            setSelectedRangeIdx(idx);
            setCropEditMode(
              range.layout === 'split'
                ? 'split'
                : range.layout === 'general'
                  ? 'general'
                  : 'single',
            );
          }}
        />
      </div>
    </div>
  );
}
