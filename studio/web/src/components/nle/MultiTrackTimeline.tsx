import { useEffect, useRef } from 'react';
import { ZoomIn, ZoomOut } from 'lucide-react';
import { cn, formatTimecode } from '@/lib/format';
import { playbackHub, useNleStore } from '@/stores/useStudioStore';
import { Button } from '@/components/ui/Primitives';
import type { FilmstripData, LayoutRange, TranscriptWord, WaveformData } from '@/types/studio';

interface MultiTrackTimelineProps {
  duration: number;
  clipStartOffset?: number;
  waveform: WaveformData | null;
  filmstrip: FilmstripData | null;
  layoutRanges: LayoutRange[];
  punchIns: Array<{ time: number; scale?: number }>;
  transcriptWords: TranscriptWord[];
  onSelectRange: (index: number, range: LayoutRange) => void;
  onWordClick: (word: TranscriptWord, kind: 'in' | 'out') => void;
}

const LAYOUT_COLORS: Record<string, string> = {
  TRACK: 'bg-[var(--accent-cyan)]/25 border-[var(--accent-cyan)] text-[var(--accent-cyan)]',
  SPLIT: 'bg-[var(--accent-violet)]/25 border-[var(--accent-violet)] text-[var(--accent-violet)]',
  ALTERNATE: 'bg-[var(--accent-amber)]/25 border-[var(--accent-amber)] text-[var(--accent-amber)]',
  GENERAL: 'bg-zinc-500/25 border-zinc-400 text-zinc-200',
};

export function MultiTrackTimeline({
  duration,
  clipStartOffset = 0,
  waveform,
  filmstrip,
  layoutRanges,
  punchIns,
  transcriptWords,
  onSelectRange,
  onWordClick,
}: MultiTrackTimelineProps) {
  const { timelineZoom, setTimelineZoom, selectedRangeIdx, recutStart, recutEnd } = useNleStore();
  const trackAreaRef = useRef<HTMLDivElement>(null);
  const playheadRef = useRef<HTMLDivElement>(null);
  const timeLabelRef = useRef<HTMLSpanElement>(null);

  const safeDur = Math.max(duration || waveform?.duration_seconds || filmstrip?.duration_seconds || 10, 0.5);

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
    playbackHub.requestSeek(ratio * safeDur);
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

  const tickCount = Math.min(24, Math.max(6, Math.round(8 * timelineZoom)));
  const ticks = Array.from({ length: tickCount + 1 }, (_, i) => (i / tickCount) * safeDur);
  const peaks = waveform?.peaks ?? [];

  return (
    <div className="flex flex-col border-t border-[var(--border-subtle)] bg-[var(--bg-surface)]">
      {/* Timeline Toolbar */}
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-panel)]/70 px-3 py-1.5 text-[11px]">
        <div className="flex items-center gap-3">
          <span className="font-semibold text-[var(--text-secondary)]">NLE Multi-Track Timeline</span>
          <span
            ref={timeLabelRef}
            className="rounded bg-[var(--bg-canvas)] px-2 py-0.5 font-mono text-[11px] text-[var(--accent-cyan)] border border-[var(--border-subtle)]"
          >
            {formatTimecode(0)}
          </span>
          <span className="font-mono text-[10px] text-[var(--text-muted)]">
            / {formatTimecode(safeDur)}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="hidden sm:inline text-[10px] text-[var(--text-muted)] mr-1">
            Click word = In · Shift+Click = Out
          </span>
          <Button size="xs" variant="ghost" onClick={() => setTimelineZoom(timelineZoom - 1)} aria-label="Zoom out timeline">
            <ZoomOut className="h-3.5 w-3.5" />
          </Button>
          <span className="font-mono text-[10px] w-7 text-center">{timelineZoom}x</span>
          <Button size="xs" variant="ghost" onClick={() => setTimelineZoom(timelineZoom + 1)} aria-label="Zoom in timeline">
            <ZoomIn className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Scrollable Multi-Track Lane Canvas */}
      <div className="flex overflow-x-auto">
        {/* Track Labels Column */}
        <div className="w-24 shrink-0 border-r border-[var(--border-subtle)] bg-[var(--bg-panel)]/40 text-[10px] font-mono text-[var(--text-muted)] select-none">
          <div className="h-6 border-b border-[var(--border-subtle)] px-2 flex items-center">TIMECODE</div>
          <div className="h-12 border-b border-[var(--border-subtle)] px-2 flex items-center">V1 VIDEO</div>
          <div className="h-12 border-b border-[var(--border-subtle)] px-2 flex items-center">A1 AUDIO</div>
          <div className="h-8 border-b border-[var(--border-subtle)] px-2 flex items-center">REFRAME</div>
          <div className="h-6 px-2 flex items-center">PUNCH-IN</div>
        </div>

        {/* Zoomable Tracks */}
        <div
          ref={trackAreaRef}
          style={{ width: `${timelineZoom * 100}%`, minWidth: '100%' }}
          className="relative flex-1 select-none"
        >
          {/* Ruler */}
          <div
            onPointerDown={handleScrubStart}
            className="relative h-6 cursor-ew-resize border-b border-[var(--border-subtle)] bg-[var(--bg-canvas)]/80"
          >
            {ticks.map((t, i) => (
              <div
                key={i}
                style={{ left: `${(t / safeDur) * 100}%` }}
                className="absolute top-0 bottom-0 flex flex-col justify-between border-l border-[var(--border-subtle)] pl-1"
              >
                <span className="font-mono text-[9px] text-[var(--text-muted)]">
                  {formatTimecode(t, false)}
                </span>
              </div>
            ))}
          </div>

          {/* V1 Filmstrip Track */}
          <div
            onPointerDown={handleScrubStart}
            className="relative flex h-12 cursor-pointer overflow-hidden border-b border-[var(--border-subtle)] bg-[var(--bg-canvas)]"
          >
            {filmstrip && filmstrip.frames.length > 0 ? (
              filmstrip.frames.map((fr) => (
                <div key={fr.index} className="h-full flex-1 overflow-hidden border-r border-black/30">
                  <img
                    src={fr.data_url || fr.url}
                    alt={`Frame ${fr.index}`}
                    draggable={false}
                    className="h-full w-full object-cover opacity-90"
                  />
                </div>
              ))
            ) : (
              <div className="flex h-full w-full items-center justify-center font-mono text-[10px] text-[var(--text-muted)]">
                Video filmstrip ready when media is rendered
              </div>
            )}
          </div>

          {/* A1 Waveform Track (Real FFmpeg PCM Peaks) */}
          <div
            onPointerDown={handleScrubStart}
            className="relative flex h-12 cursor-pointer items-center gap-[1px] overflow-hidden border-b border-[var(--border-subtle)] bg-[var(--bg-canvas)]/70 px-0.5"
          >
            {peaks.length > 0 ? (
              peaks.map((amp, i) => (
                <div
                  key={i}
                  style={{ height: `${Math.max(8, Math.round(amp * 92))}%` }}
                  className="flex-1 rounded-full bg-[var(--accent-cyan)]/75"
                />
              ))
            ) : (
              <div className="w-full text-center font-mono text-[10px] text-[var(--text-muted)]">
                Audio waveform standby
              </div>
            )}
          </div>

          {/* Layout Ranges Track (TRACK / SPLIT / GENERAL / ALTERNATE) */}
          <div className="relative h-8 border-b border-[var(--border-subtle)] bg-[var(--bg-canvas)]/50">
            {layoutRanges.length > 0 ? (
              layoutRanges.map((r, idx) => {
                const startPct = Math.max(0, Math.min(100, (r.start / safeDur) * 100));
                const endPct = Math.max(startPct + 1, Math.min(100, (r.end / safeDur) * 100));
                const style = LAYOUT_COLORS[r.layout] || LAYOUT_COLORS.GENERAL;
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
                      'absolute top-1 bottom-1 overflow-hidden rounded border px-1.5 text-left font-mono text-[9px] font-bold transition-all cursor-pointer truncate',
                      style,
                      selectedRangeIdx === idx && 'ring-1 ring-white',
                    )}
                    title={`${r.layout} (${formatTimecode(r.start)} – ${formatTimecode(r.end)})`}
                  >
                    {r.layout}
                  </button>
                );
              })
            ) : (
              <div className="flex h-full items-center px-2 font-mono text-[10px] text-[var(--text-muted)]">
                AUTO · Single/Split layout ranges populate after Reframe v2 pass
              </div>
            )}
          </div>

          {/* Punch-In Keyframe Markers Track */}
          <div className="relative h-6 bg-[var(--bg-canvas)]/40">
            {punchIns.map((pi, idx) => {
              const pct = Math.max(0, Math.min(100, (pi.time / safeDur) * 100));
              return (
                <button
                  key={idx}
                  type="button"
                  title={`Punch-in ${pi.scale ?? 1.15}x @ ${formatTimecode(pi.time)}`}
                  onClick={() => playbackHub.requestSeek(pi.time)}
                  style={{ left: `${pct}%` }}
                  className="absolute top-1.5 -ml-1.5 h-3 w-3 rotate-45 rounded-[2px] border border-zinc-950 bg-[var(--accent-amber)] cursor-pointer hover:scale-125 transition-transform"
                />
              );
            })}
          </div>

          {/* Recut In/Out Shaded Selection Window */}
          {recutStart != null && recutEnd != null && recutEnd > recutStart && (
            <div
              style={{
                left: `${Math.max(0, ((recutStart - clipStartOffset) / safeDur) * 100)}%`,
                width: `${Math.min(100, ((recutEnd - recutStart) / safeDur) * 100)}%`,
              }}
              className="pointer-events-none absolute inset-y-6 border-x-2 border-[var(--accent-amber)] bg-[var(--accent-amber)]/10"
            />
          )}

          {/* 60fps Playhead Needle */}
          <div
            ref={playheadRef}
            style={{ left: '0%' }}
            className="pointer-events-none absolute inset-y-0 z-20 w-[2px] bg-[var(--accent-cyan)] shadow-[0_0_8px_var(--accent-cyan)]"
          >
            <div className="absolute -left-[5px] top-0 h-2.5 w-3 rounded-b-sm bg-[var(--accent-cyan)]" />
          </div>
        </div>
      </div>

      {/* Word-Snapped Transcript Strip */}
      {transcriptWords.length > 0 && (
        <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-canvas)]/70 px-3 py-2">
          <div className="mb-1 flex items-center justify-between text-[10px] text-[var(--text-muted)]">
            <span className="font-mono uppercase tracking-wider">
              Word-Snapped Transcript ({transcriptWords.length} words)
            </span>
            {recutStart != null && recutEnd != null && (
              <span className="font-mono text-[var(--accent-amber)]">
                In {formatTimecode(recutStart)} → Out {formatTimecode(recutEnd)} (
                {(recutEnd - recutStart).toFixed(2)}s)
              </span>
            )}
          </div>
          <div className="flex max-h-20 flex-wrap gap-1 overflow-y-auto">
            {transcriptWords.slice(0, 180).map((w, idx) => {
              const inWindow =
                recutStart != null && recutEnd != null && w.start >= recutStart && w.end <= recutEnd;
              return (
                <button
                  key={`${w.start}-${idx}`}
                  type="button"
                  onClick={(e) => onWordClick(w, e.shiftKey ? 'out' : 'in')}
                  title={`${formatTimecode(w.start)} – ${formatTimecode(w.end)} (Click=In, Shift+Click=Out)`}
                  className={cn(
                    'rounded px-1.5 py-0.5 text-[11px] transition-colors cursor-pointer',
                    inWindow
                      ? 'bg-[var(--accent-amber-soft)] text-[var(--accent-amber)] font-medium'
                      : 'bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] hover:text-[var(--text-primary)]',
                  )}
                >
                  {w.word}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
