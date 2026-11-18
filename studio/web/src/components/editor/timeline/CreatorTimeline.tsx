import { useEffect, useRef } from 'react';
import {
  ArrowLeft,
  Maximize2,
  Plus,
  Scissors,
  Trash2,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { cn, formatTimecode } from '@/lib/format';
import { playbackHub, useNleStore } from '@/stores/useStudioStore';
import { useEditorStore } from '@/stores/useEditorStore';
import { Button } from '@/components/ui/Primitives';
import type { FilmstripData, LayoutRange, WaveformData } from '@/types/studio';

const LAYOUT_COLORS: Record<string, string> = {
  track: 'bg-sky-500/20 border-sky-500 text-sky-600 dark:text-sky-300',
  split: 'bg-violet-500/25 border-violet-500 text-violet-700 dark:text-violet-300',
  alternate: 'bg-amber-500/20 border-amber-500 text-amber-700 dark:text-amber-300',
  general: 'bg-zinc-500/20 border-zinc-400 text-zinc-700 dark:text-zinc-300',
};

export function CreatorTimeline({
  duration,
  waveform,
  filmstrip,
  layoutRanges,
  punchIns,
  fallbackPeaks,
  onSelectRange,
}: {
  duration: number;
  waveform: WaveformData | null;
  filmstrip: FilmstripData | null;
  layoutRanges: LayoutRange[];
  punchIns: number[];
  fallbackPeaks?: number[];
  onSelectRange: (idx: number, range: LayoutRange) => void;
}) {
  const { timelineZoom, setTimelineZoom, selectedRangeIdx } = useNleStore();
  const {
    activeTool,
    setActiveTool,
    captions,
    activeCaptionId,
    setActiveCaptionId,
    textOverlays,
    selection,
    setSelection,
    cutRanges,
    splitCaptionAtTime,
    addCaptionAtTime,
    deleteCaption,
    deleteTextOverlay,
  } = useEditorStore();

  const trackAreaRef = useRef<HTMLDivElement>(null);
  const playheadRef = useRef<HTMLDivElement>(null);
  const timeLabelRef = useRef<HTMLSpanElement>(null);

  const safeDur = Math.max(
    duration || waveform?.duration_seconds || filmstrip?.duration_seconds || 24,
    0.5,
  );

  // Zero-rerender 60fps playhead DOM transform synced to playbackHub
  useEffect(() => {
    const sync = (t: number, d: number) => {
      const denom = Math.max(d || safeDur, 0.1);
      const pct = Math.max(0, Math.min(100, (t / denom) * 100));
      if (playheadRef.current) {
        playheadRef.current.style.left = `${pct}%`;
      }
      if (timeLabelRef.current) {
        timeLabelRef.current.textContent = formatTimecode(t);
      }
    };
    sync(playbackHub.currentTime, playbackHub.duration || safeDur);
    return playbackHub.subscribe(sync);
  }, [safeDur]);

  const seekFromPointer = (clientX: number) => {
    const el = trackAreaRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / Math.max(rect.width, 1)));
    const t = ratio * safeDur;
    playbackHub.requestSeek(t);
    // Sync active caption row to scrub position
    const hit = captions.find((c) => t >= c.start && t <= c.end);
    if (hit && hit.id !== activeCaptionId) {
      setActiveCaptionId(hit.id);
    }
  };

  const handleScrubStart = (e: React.PointerEvent) => {
    e.preventDefault();
    seekFromPointer(e.clientX);
    const onMove = (me: PointerEvent) => seekFromPointer(me.clientX);
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const handleDeleteSelected = () => {
    if (!selection) return;
    if (selection.kind === 'subtitle') deleteCaption(selection.id);
    else if (selection.kind === 'text') deleteTextOverlay(selection.id);
  };

  const tickCount = Math.min(24, Math.max(6, Math.round(8 * timelineZoom)));
  const ticks = Array.from({ length: tickCount + 1 }, (_, i) => (i / tickCount) * safeDur);
  const peaks = waveform?.peaks?.length ? waveform.peaks : fallbackPeaks || [];

  return (
    <section
      aria-label="Timeline"
      className="flex shrink-0 flex-col border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] select-none"
    >
      {/* Timeline Toolbar: Back to Timeline, Split Subtitle, Add Subtitle, Zoom, Fit */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs">
        <div className="flex items-center gap-1.5">
          {(activeTool === 'subtitles' || activeTool === 'script') && (
            <Button
              size="xs"
              variant="ghost"
              onClick={() => setActiveTool('video')}
              className="font-medium"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Back to Timeline
            </Button>
          )}

          <Button
            size="xs"
            variant="secondary"
            onClick={() => splitCaptionAtTime(playbackHub.currentTime)}
            title="Split active subtitle at playhead"
          >
            <Scissors className="h-3.5 w-3.5" />
            Split Subtitle
          </Button>

          <Button
            size="xs"
            variant="secondary"
            onClick={() => addCaptionAtTime(playbackHub.currentTime, safeDur)}
            title="Add new subtitle block at playhead"
          >
            <Plus className="h-3.5 w-3.5" />
            Add Subtitle
          </Button>

          {selection && (
            <Button
              size="xs"
              variant="ghost"
              onClick={handleDeleteSelected}
              title="Delete selected item"
              aria-label="Delete selected item"
            >
              <Trash2 className="h-3.5 w-3.5 text-[var(--status-fail)]" />
            </Button>
          )}
        </div>

        {/* Center Live Timecode */}
        <div className="flex items-center gap-1.5 font-mono text-[11px] tabular-nums">
          <span
            ref={timeLabelRef}
            className="rounded bg-[var(--bg-panel)] px-2 py-0.5 font-semibold text-[var(--text-primary)] border border-[var(--border-subtle)]"
          >
            {formatTimecode(0)}
          </span>
          <span className="text-[var(--text-muted)]">/ {formatTimecode(safeDur)}</span>
        </div>

        {/* Right Zoom / Fit Controls */}
        <div className="flex items-center gap-1">
          <Button
            size="xs"
            variant="ghost"
            onClick={() => setTimelineZoom(1)}
            title="Fit timeline"
          >
            <Maximize2 className="h-3 w-3" />
            Fit
          </Button>
          <Button
            size="xs"
            variant="ghost"
            onClick={() => setTimelineZoom(timelineZoom - 1)}
            aria-label="Zoom out timeline"
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </Button>
          <span className="w-7 text-center font-mono text-[10px] text-[var(--text-muted)]">
            {timelineZoom}x
          </span>
          <Button
            size="xs"
            variant="ghost"
            onClick={() => setTimelineZoom(timelineZoom + 1)}
            aria-label="Zoom in timeline"
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Multi-Track Lanes */}
      <div className="flex overflow-x-auto">
        {/* Track Labels */}
        <div className="w-[88px] shrink-0 border-r border-[var(--border-subtle)] bg-[var(--bg-panel)]/60 font-mono text-[10px] text-[var(--text-muted)]">
          <div className="flex h-6 items-center border-b border-[var(--border-subtle)] px-2.5">
            RULER
          </div>
          <div className="flex h-8 items-center border-b border-[var(--border-subtle)] px-2.5 text-[var(--track-sub-border)] font-semibold">
            SUBS
          </div>
          {textOverlays.length > 0 && (
            <div className="flex h-7 items-center border-b border-[var(--border-subtle)] px-2.5 text-[var(--track-text-ink)] font-semibold">
              TEXT
            </div>
          )}
          <div className="flex h-11 items-center border-b border-[var(--border-subtle)] px-2.5">
            VIDEO
          </div>
          <div className="flex h-9 items-center border-b border-[var(--border-subtle)] px-2.5">
            AUDIO
          </div>
          {layoutRanges.length > 0 && (
            <div className="flex h-7 items-center px-2.5">REFRAME</div>
          )}
        </div>

        {/* Zoomable Tracks Canvas */}
        <div
          ref={trackAreaRef}
          style={{ width: `${timelineZoom * 100}%`, minWidth: '100%' }}
          className="relative flex-1"
        >
          {/* Time Ruler */}
          <div
            onPointerDown={handleScrubStart}
            className="relative h-6 cursor-ew-resize border-b border-[var(--border-subtle)] bg-[var(--bg-panel)]/40"
          >
            {ticks.map((t, i) => (
              <div
                key={i}
                style={{ left: `${(t / safeDur) * 100}%` }}
                className="absolute inset-y-0 border-l border-[var(--border-subtle)] pl-1"
              >
                <span className="font-mono text-[9px] text-[var(--text-muted)]">
                  {formatTimecode(t, false)}
                </span>
              </div>
            ))}
          </div>

          {/* Dedicated Purple Subtitle Track */}
          <div className="relative h-8 border-b border-[var(--border-subtle)] bg-[var(--bg-canvas)]/60">
            {captions.length > 0 ? (
              captions.map((cap) => {
                const left = Math.max(0, Math.min(100, (cap.start / safeDur) * 100));
                const width = Math.max(1.5, Math.min(100 - left, ((cap.end - cap.start) / safeDur) * 100));
                const active = activeCaptionId === cap.id;
                return (
                  <button
                    key={cap.id}
                    type="button"
                    onClick={() => {
                      setActiveCaptionId(cap.id);
                      playbackHub.requestSeek(cap.start + 0.05);
                    }}
                    style={{ left: `${left}%`, width: `${width}%` }}
                    title={`${cap.text} (${formatTimecode(cap.start)}–${formatTimecode(cap.end)})`}
                    className={cn(
                      'absolute top-1 bottom-1 overflow-hidden rounded-md border px-1.5 text-left text-[10px] font-medium truncate transition-all cursor-pointer',
                      'bg-[var(--track-sub-bg)] border-[var(--track-sub-border)] text-[var(--track-sub-text)]',
                      active && 'ring-2 ring-[var(--accent-lime-border)] font-semibold z-10',
                    )}
                  >
                    {cap.text}
                  </button>
                );
              })
            ) : (
              <div className="flex h-full items-center px-3 text-[10px] text-[var(--text-muted)]">
                No subtitle blocks yet — click Auto-subtitle or Add Subtitle
              </div>
            )}
          </div>

          {/* Optional Text Overlay Track */}
          {textOverlays.length > 0 && (
            <div className="relative h-7 border-b border-[var(--border-subtle)] bg-[var(--bg-canvas)]/40">
              {textOverlays.map((ov) => {
                const left = Math.max(0, Math.min(100, (ov.start / safeDur) * 100));
                const width = Math.max(2, Math.min(100 - left, ((ov.end - ov.start) / safeDur) * 100));
                const active = selection?.kind === 'text' && selection.id === ov.id;
                return (
                  <button
                    key={ov.id}
                    type="button"
                    onClick={() => {
                      setSelection({ kind: 'text', id: ov.id });
                      playbackHub.requestSeek(ov.start);
                    }}
                    style={{ left: `${left}%`, width: `${width}%` }}
                    className={cn(
                      'absolute top-1 bottom-1 overflow-hidden rounded-md border px-1.5 text-left text-[10px] font-medium truncate cursor-pointer',
                      'bg-[var(--track-text-bg)] border-[var(--track-text-border)] text-[var(--track-text-ink)]',
                      active && 'ring-2 ring-[var(--accent-lime-border)] z-10',
                    )}
                  >
                    T · {ov.text}
                  </button>
                );
              })}
            </div>
          )}

          {/* V1 Video Filmstrip Track + Visible Script Cut Markers */}
          <div
            onPointerDown={handleScrubStart}
            className="relative flex h-11 cursor-pointer overflow-hidden border-b border-[var(--border-subtle)] bg-[var(--bg-panel)]"
          >
            {filmstrip && filmstrip.frames.length > 0 ? (
              filmstrip.frames.map((fr) => (
                <div key={fr.index} className="h-full flex-1 overflow-hidden border-r border-black/20">
                  <img
                    src={fr.data_url || fr.url}
                    alt={`Frame ${fr.index}`}
                    draggable={false}
                    className="h-full w-full object-cover"
                  />
                </div>
              ))
            ) : (
              <div className="flex h-full w-full items-center px-2">
                <div className="flex h-8 w-full items-center justify-between rounded-md border border-[var(--accent-lime-border)]/70 bg-gradient-to-r from-slate-800 via-slate-700 to-slate-800 px-3 text-[10px] font-medium text-white">
                  <span>Main Video Track</span>
                  <span className="font-mono text-white/70">{formatTimecode(safeDur, false)}</span>
                </div>
              </div>
            )}

            {/* Script Editor Deleted Word Cut Markers */}
            {cutRanges.map((cut) => {
              const left = Math.max(0, Math.min(100, (cut.start / safeDur) * 100));
              const width = Math.max(0.8, Math.min(100 - left, ((cut.end - cut.start) / safeDur) * 100));
              return (
                <div
                  key={cut.id}
                  style={{ left: `${left}%`, width: `${width}%` }}
                  title={`Cut: "${cut.label}" (${formatTimecode(cut.start)}–${formatTimecode(cut.end)})`}
                  className="pointer-events-none absolute inset-y-0 border-x border-red-500 bg-red-500/35"
                />
              );
            })}
          </div>

          {/* A1 Audio PCM Waveform Track */}
          <div
            onPointerDown={handleScrubStart}
            className="relative flex h-9 cursor-pointer items-center gap-[1px] overflow-hidden border-b border-[var(--border-subtle)] bg-[var(--bg-canvas)]/50 px-0.5"
          >
            {peaks.length > 0 ? (
              peaks.map((amp, i) => (
                <div
                  key={i}
                  style={{ height: `${Math.max(10, Math.round(amp * 86))}%` }}
                  className="flex-1 rounded-full bg-[var(--accent-cyan)]/75"
                />
              ))
            ) : (
              <div className="w-full text-center font-mono text-[10px] text-[var(--text-muted)]">
                Audio waveform standby
              </div>
            )}
          </div>

          {/* Reframe v2 Layout Ranges & Punch-In Diamonds (exact lowercase contract) */}
          {layoutRanges.length > 0 && (
            <div className="relative h-7 bg-[var(--bg-canvas)]/40">
              {layoutRanges.map((r, idx) => {
                const startPct = Math.max(0, Math.min(100, (r.start / safeDur) * 100));
                const endPct = Math.max(startPct + 1.5, Math.min(100, (r.end / safeDur) * 100));
                const style = LAYOUT_COLORS[r.layout] || LAYOUT_COLORS.general;
                return (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => {
                      onSelectRange(idx, r);
                      playbackHub.requestSeek(r.start);
                    }}
                    style={{ left: `${startPct}%`, width: `${endPct - startPct}%` }}
                    className={cn(
                      'absolute top-1 bottom-1 overflow-hidden rounded border px-1.5 text-left font-mono text-[9px] font-bold uppercase truncate cursor-pointer',
                      style,
                      selectedRangeIdx === idx && 'ring-1 ring-[var(--accent-lime-border)]',
                    )}
                    title={`${r.layout.toUpperCase()} (${formatTimecode(r.start)}–${formatTimecode(r.end)})`}
                  >
                    {r.layout}
                  </button>
                );
              })}

              {punchIns.map((timeSec, idx) => {
                const pct = Math.max(0, Math.min(100, (timeSec / safeDur) * 100));
                return (
                  <button
                    key={`pi-${idx}`}
                    type="button"
                    title={`Punch-In 1.15x @ ${formatTimecode(timeSec)}`}
                    onClick={() => playbackHub.requestSeek(timeSec)}
                    style={{ left: `${pct}%` }}
                    className="absolute top-2 -ml-1.5 h-2.5 w-2.5 rotate-45 rounded-[2px] border border-zinc-950 bg-[var(--accent-lime)] cursor-pointer hover:scale-125"
                  />
                );
              })}
            </div>
          )}

          {/* 60fps Playhead Needle */}
          <div
            ref={playheadRef}
            style={{ left: '0%' }}
            className="pointer-events-none absolute inset-y-0 z-30 w-[2px] bg-[var(--text-primary)] shadow-sm"
          >
            <div className="absolute -left-[5px] top-0 h-3 w-3 rounded-b-sm bg-[var(--accent-lime)] border border-zinc-900" />
          </div>
        </div>
      </div>
    </section>
  );
}
