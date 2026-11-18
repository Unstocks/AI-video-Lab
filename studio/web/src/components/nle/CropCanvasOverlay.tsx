import { useRef, useState } from 'react';
import { cn } from '@/lib/format';
import type { CropOverrideEntry } from '@/types/studio';

interface CropCanvasOverlayProps {
  mode: 'single' | 'split';
  override: CropOverrideEntry;
  showSafeZones: boolean;
  onChange: (next: CropOverrideEntry) => void;
}

type BoxKey = 'crop' | 'top' | 'bottom';

const DEFAULT_SINGLE: [number, number, number, number] = [0.34, 0.0, 0.316, 1.0];
const DEFAULT_TOP: [number, number, number, number] = [0.05, 0.05, 0.42, 0.85];
const DEFAULT_BOTTOM: [number, number, number, number] = [0.53, 0.05, 0.42, 0.85];

function clampBox([x, y, w, h]: [number, number, number, number]): [number, number, number, number] {
  const nw = Math.max(0.14, Math.min(1.0, w));
  const nh = Math.max(0.18, Math.min(1.0, h));
  const nx = Math.max(0.0, Math.min(1.0 - nw, x));
  const ny = Math.max(0.0, Math.min(1.0 - nh, y));
  return [
    Number(nx.toFixed(4)),
    Number(ny.toFixed(4)),
    Number(nw.toFixed(4)),
    Number(nh.toFixed(4)),
  ];
}

export function CropCanvasOverlay({
  mode,
  override,
  showSafeZones,
  onChange,
}: CropCanvasOverlayProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<string | null>(null);

  const boxes: Array<{
    key: BoxKey;
    label: string;
    color: string;
    box: [number, number, number, number];
  }> =
    mode === 'split'
      ? [
          {
            key: 'top',
            label: 'TOP SPEAKER',
            color: 'var(--accent-cyan)',
            box: override.top ?? DEFAULT_TOP,
          },
          {
            key: 'bottom',
            label: 'BOTTOM SPEAKER',
            color: 'var(--accent-amber)',
            box: override.bottom ?? DEFAULT_BOTTOM,
          },
        ]
      : [
          {
            key: 'crop',
            label: '9:16 CROP',
            color: 'var(--accent-amber)',
            box: override.crop ?? DEFAULT_SINGLE,
          },
        ];

  const startDrag = (
    e: React.PointerEvent,
    key: BoxKey,
    action: 'move' | 'resize-br',
    initialBox: [number, number, number, number],
  ) => {
    e.preventDefault();
    e.stopPropagation();
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return;

    const startX = e.clientX;
    const startY = e.clientY;
    setDragging(`${key}:${action}`);

    const onMove = (me: PointerEvent) => {
      const dx = (me.clientX - startX) / rect.width;
      const dy = (me.clientY - startY) / rect.height;
      const [bx, by, bw, bh] = initialBox;
      const updated =
        action === 'move'
          ? clampBox([bx + dx, by + dy, bw, bh])
          : clampBox([bx, by, bw + dx, bh + dy]);

      onChange({
        ...override,
        layout: mode === 'split' ? 'SPLIT' : 'TRACK',
        [key]: updated,
      });
    };

    const onUp = () => {
      setDragging(null);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  return (
    <div
      ref={containerRef}
      className="pointer-events-auto absolute inset-0 select-none overflow-hidden"
      aria-label="Interactive Reframe Crop Overlay"
    >
      {/* Subtle darkened letterbox veil */}
      <div className="pointer-events-none absolute inset-0 bg-black/35" />

      {boxes.map(({ key, label, color, box }) => {
        const [x, y, w, h] = box;
        const isActive = dragging?.startsWith(key);
        return (
          <div
            key={key}
            style={{
              left: `${x * 100}%`,
              top: `${y * 100}%`,
              width: `${w * 100}%`,
              height: `${h * 100}%`,
              borderColor: color,
              boxShadow: isActive ? `0 0 0 2px ${color}` : undefined,
            }}
            onPointerDown={(e) => startDrag(e, key, 'move', box)}
            className={cn(
              'absolute cursor-move border-2 bg-white/5 transition-shadow',
              isActive && 'bg-white/10',
            )}
          >
            {/* Rule of thirds grid */}
            <div className="pointer-events-none absolute inset-0 grid grid-cols-3 grid-rows-3 opacity-35">
              <div className="border-r border-b border-white/40" />
              <div className="border-r border-b border-white/40" />
              <div className="border-b border-white/40" />
              <div className="border-r border-b border-white/40" />
              <div className="border-r border-b border-white/40" />
              <div className="border-b border-white/40" />
              <div className="border-r border-white/40" />
              <div className="border-r border-white/40" />
              <div />
            </div>

            {/* Social Safe-Zone Danger Guides (TikTok/Reels/Shorts) */}
            {showSafeZones && (
              <>
                <div className="pointer-events-none absolute inset-x-0 top-0 h-[14%] bg-red-500/20 border-b border-dashed border-red-400/70" />
                <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[22%] bg-red-500/20 border-t border-dashed border-red-400/70" />
                <div className="pointer-events-none absolute right-0 top-[14%] bottom-[22%] w-[16%] bg-red-500/15 border-l border-dashed border-red-400/60" />
              </>
            )}

            {/* Label pill */}
            <div
              style={{ backgroundColor: color }}
              className="pointer-events-none absolute left-1 top-1 rounded px-1.5 py-0.5 font-mono text-[9px] font-bold text-zinc-950 shadow-xs"
            >
              {label} · {Math.round(w * 100)}%×{Math.round(h * 100)}%
            </div>

            {/* Bottom-right resize handle */}
            <button
              type="button"
              aria-label={`Resize ${label}`}
              onPointerDown={(e) => startDrag(e, key, 'resize-br', box)}
              style={{ backgroundColor: color }}
              className="absolute -bottom-1.5 -right-1.5 h-3.5 w-3.5 cursor-nwse-resize rounded-sm border border-zinc-950 shadow"
            />
          </div>
        );
      })}
    </div>
  );
}
