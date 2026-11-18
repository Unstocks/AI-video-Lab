import { useRef } from 'react';
import type { CropOverrideEntry, CropPoint } from '@/types/studio';

interface CropCanvasOverlayProps {
  mode: 'single' | 'split' | 'general';
  override: CropOverrideEntry | undefined;
  showSafeZones: boolean;
  onChange: (entry: CropOverrideEntry) => void;
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

/**
 * Locked 9:16 single crop width on a 16:9 canvas: (9/16) / (16/9) = 0.3164.
 * Matches `lib/reframe_v2.py` exact horizontal center fraction `{"x": cx}`!
 */
const SINGLE_BOX_W = 0.3164;
/**
 * Locked 9:8 half-frame split crop box on a 16:9 canvas:
 * Each speaker pane is 1080×960 -> aspect 1.125; height 0.72 -> width ~0.455.
 */
const SPLIT_BOX_W = 0.44;
const SPLIT_BOX_H = 0.78;

function extractSingleX(entry: CropOverrideEntry | undefined): number {
  if (typeof entry === 'number') return clamp(entry, 0.16, 0.84);
  if (entry && typeof entry === 'object' && 'x' in entry && typeof entry.x === 'number') {
    return clamp(entry.x, 0.16, 0.84);
  }
  return 0.5;
}

function extractSplitPoint(
  half: CropPoint | number | undefined,
  fallbackX: number,
  fallbackY = 0.5,
): CropPoint {
  if (typeof half === 'number') return { x: clamp(half, 0.22, 0.78), y: fallbackY };
  if (half && typeof half === 'object') {
    return {
      x: clamp(typeof half.x === 'number' ? half.x : fallbackX, 0.22, 0.78),
      y: clamp(typeof half.y === 'number' ? half.y : fallbackY, 0.39, 0.61),
    };
  }
  return { x: fallbackX, y: fallbackY };
}

/**
 * Interactive 16:9 On-Canvas Reframe v2 Crop Editor.
 * Emits 100% exact `lib/reframe_v2.py:apply_crop_overrides()` JSON payloads:
 * - Single: `{ "x": centerX }`
 * - Split:  `{ "top": { "x": cx, "y": cy }, "bottom": { "x": cx, "y": cy } }`
 * - General: `{ "layout": "general" }`
 */
export function CropCanvasOverlay({
  mode,
  override,
  showSafeZones,
  onChange,
}: CropCanvasOverlayProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  const singleCx = extractSingleX(override);
  const splitObj =
    override && typeof override === 'object' && 'top' in override ? override : undefined;
  const topPt = extractSplitPoint(splitObj?.top, 0.28, 0.48);
  const botPt = extractSplitPoint(splitObj?.bottom, 0.72, 0.48);

  const startSingleDrag = (e: React.PointerEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const container = containerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const startClientX = e.clientX;
    const origCx = singleCx;

    const onMove = (me: PointerEvent) => {
      const dx = (me.clientX - startClientX) / Math.max(rect.width, 1);
      const nextCx = Number(clamp(origCx + dx, SINGLE_BOX_W / 2, 1 - SINGLE_BOX_W / 2).toFixed(4));
      onChange({ x: nextCx });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const startSplitDrag = (e: React.PointerEvent, which: 'top' | 'bottom') => {
    e.preventDefault();
    e.stopPropagation();
    const container = containerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const startClientX = e.clientX;
    const startClientY = e.clientY;
    const orig = which === 'top' ? topPt : botPt;

    const onMove = (me: PointerEvent) => {
      const dx = (me.clientX - startClientX) / Math.max(rect.width, 1);
      const dy = (me.clientY - startClientY) / Math.max(rect.height, 1);
      const updated: CropPoint = {
        x: Number(clamp(orig.x + dx, SPLIT_BOX_W / 2, 1 - SPLIT_BOX_W / 2).toFixed(4)),
        y: Number(clamp(orig.y + dy, SPLIT_BOX_H / 2, 1 - SPLIT_BOX_H / 2).toFixed(4)),
      };
      onChange({
        top: which === 'top' ? updated : topPt,
        bottom: which === 'bottom' ? updated : botPt,
      });
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  if (mode === 'general') {
    return (
      <div
        ref={containerRef}
        className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-black/25"
      >
        <div className="rounded-lg border border-dashed border-[var(--accent-lime)] bg-black/75 px-3 py-1.5 font-mono text-[11px] text-[var(--accent-lime)]">
          GENERAL · Blurred Backdrop Pillarbox (Full 16:9 Preserved)
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="pointer-events-none absolute inset-0 z-10 select-none">
      {mode === 'single' ? (
        <div
          onPointerDown={startSingleDrag}
          style={{
            left: `${(singleCx - SINGLE_BOX_W / 2) * 100}%`,
            top: '0%',
            width: `${SINGLE_BOX_W * 100}%`,
            height: '100%',
          }}
          className="pointer-events-auto absolute cursor-ew-resize border-2 border-[var(--accent-lime)] bg-[var(--accent-lime)]/10 shadow-[0_0_0_9999px_rgba(0,0,0,0.45)]"
        >
          <div className="absolute left-1.5 top-1.5 rounded bg-[var(--accent-lime)] px-1.5 py-0.5 font-mono text-[9px] font-bold text-zinc-950">
            9:16 TRACK · x={Math.round(singleCx * 100)}%
          </div>
          {/* Rule of thirds */}
          <div className="pointer-events-none absolute inset-0 grid grid-cols-3 grid-rows-3 opacity-35">
            {Array.from({ length: 9 }).map((_, i) => (
              <div key={i} className="border border-white/25" />
            ))}
          </div>
          {showSafeZones && (
            <>
              <div className="pointer-events-none absolute inset-x-0 top-0 h-[13%] border-b border-dashed border-red-400/75 bg-red-500/20" />
              <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[22%] border-t border-dashed border-red-400/75 bg-red-500/20" />
            </>
          )}
        </div>
      ) : (
        <>
          {/* TOP SPEAKER (Cyan — Locked 9:8 Split Half-Frame) */}
          <div
            onPointerDown={(e) => startSplitDrag(e, 'top')}
            style={{
              left: `${(topPt.x - SPLIT_BOX_W / 2) * 100}%`,
              top: `${(topPt.y - SPLIT_BOX_H / 2) * 100}%`,
              width: `${SPLIT_BOX_W * 100}%`,
              height: `${SPLIT_BOX_H * 100}%`,
            }}
            className="pointer-events-auto absolute cursor-move rounded-sm border-2 border-sky-400 bg-sky-400/12"
          >
            <div className="absolute left-1.5 top-1.5 rounded bg-sky-400 px-1.5 py-0.5 font-mono text-[9px] font-bold text-zinc-950">
              TOP SPEAKER · {Math.round(topPt.x * 100)}%,{Math.round(topPt.y * 100)}%
            </div>
            <div className="pointer-events-none absolute inset-0 grid grid-cols-3 grid-rows-3 opacity-30">
              {Array.from({ length: 9 }).map((_, i) => (
                <div key={i} className="border border-white/25" />
              ))}
            </div>
          </div>

          {/* BOTTOM SPEAKER (Amber — Locked 9:8 Split Half-Frame) */}
          <div
            onPointerDown={(e) => startSplitDrag(e, 'bottom')}
            style={{
              left: `${(botPt.x - SPLIT_BOX_W / 2) * 100}%`,
              top: `${(botPt.y - SPLIT_BOX_H / 2) * 100}%`,
              width: `${SPLIT_BOX_W * 100}%`,
              height: `${SPLIT_BOX_H * 100}%`,
            }}
            className="pointer-events-auto absolute cursor-move rounded-sm border-2 border-amber-400 bg-amber-400/12"
          >
            <div className="absolute left-1.5 top-1.5 rounded bg-amber-400 px-1.5 py-0.5 font-mono text-[9px] font-bold text-zinc-950">
              BOTTOM SPEAKER · {Math.round(botPt.x * 100)}%,{Math.round(botPt.y * 100)}%
            </div>
            <div className="pointer-events-none absolute inset-0 grid grid-cols-3 grid-rows-3 opacity-30">
              {Array.from({ length: 9 }).map((_, i) => (
                <div key={i} className="border border-white/25" />
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
