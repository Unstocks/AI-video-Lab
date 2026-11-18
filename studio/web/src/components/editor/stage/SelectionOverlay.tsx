import { useRef, useState } from 'react';
import { RotateCw, Trash2 } from 'lucide-react';
import { cn } from '@/lib/format';
import type { SubtitleBoxTransform, TextOverlayItem } from '@/types/editor';
import type { SubtitlePreset } from '@/types/studio';

function clamp(v: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, v));
}

interface DraggableBoxProps {
  x: number;
  y: number;
  width: number;
  rotation: number;
  selected: boolean;
  onSelect: () => void;
  onChange: (patch: { x?: number; y?: number; width?: number; rotation?: number }, commit?: boolean) => void;
  onDelete?: () => void;
  label: string;
  accent?: 'lime' | 'violet';
  children: React.ReactNode;
}

function DraggableTransformBox({
  x,
  y,
  width,
  rotation,
  selected,
  onSelect,
  onChange,
  onDelete,
  label,
  accent = 'lime',
  children,
}: DraggableBoxProps) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [snapCenter, setSnapCenter] = useState(false);

  const startDrag = (e: React.PointerEvent) => {
    e.stopPropagation();
    onSelect();
    const parent = boxRef.current?.parentElement;
    if (!parent) return;
    const rect = parent.getBoundingClientRect();
    const startX = e.clientX;
    const startY = e.clientY;
    const origX = x;
    const origY = y;

    const onMove = (me: PointerEvent) => {
      const dx = (me.clientX - startX) / Math.max(rect.width, 1);
      const dy = (me.clientY - startY) / Math.max(rect.height, 1);
      let nextX = clamp(origX + dx, 0.1, 0.9);
      const nextY = clamp(origY + dy, 0.08, 0.92);
      if (Math.abs(nextX - 0.5) < 0.025) {
        nextX = 0.5;
        setSnapCenter(true);
      } else {
        setSnapCenter(false);
      }
      onChange({ x: Number(nextX.toFixed(4)), y: Number(nextY.toFixed(4)) }, false);
    };

    const onUp = () => {
      setSnapCenter(false);
      onChange({}, true);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const startResize = (e: React.PointerEvent, dir: -1 | 1) => {
    e.stopPropagation();
    const parent = boxRef.current?.parentElement;
    if (!parent) return;
    const rect = parent.getBoundingClientRect();
    const startX = e.clientX;
    const origW = width;

    const onMove = (me: PointerEvent) => {
      const dx = ((me.clientX - startX) / Math.max(rect.width, 1)) * 2 * dir;
      const nextW = clamp(origW + dx, 0.25, 0.96);
      onChange({ width: Number(nextW.toFixed(4)) }, false);
    };
    const onUp = () => {
      onChange({}, true);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const startRotate = (e: React.PointerEvent) => {
    e.stopPropagation();
    const el = boxRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;

    const onMove = (me: PointerEvent) => {
      const rad = Math.atan2(me.clientY - cy, me.clientX - cx);
      let deg = Math.round((rad * 180) / Math.PI + 90);
      if (Math.abs(deg) < 4) deg = 0;
      onChange({ rotation: clamp(deg, -45, 45) }, false);
    };
    const onUp = () => {
      onChange({}, true);
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const borderClass =
    accent === 'violet'
      ? 'border-[var(--track-sub-border)]'
      : 'border-[var(--accent-lime-border)]';
  const handleBg =
    accent === 'violet' ? 'bg-[var(--track-sub-border)]' : 'bg-[var(--accent-lime)]';

  return (
    <>
      {snapCenter && (
        <div className="pointer-events-none absolute inset-y-0 left-1/2 z-20 w-px border-l border-dashed border-[var(--accent-lime)]" />
      )}
      <div
        ref={boxRef}
        onPointerDown={startDrag}
        style={{
          left: `${x * 100}%`,
          top: `${y * 100}%`,
          width: `${width * 100}%`,
          transform: `translate(-50%, -50%) rotate(${rotation}deg)`,
        }}
        className={cn(
          'absolute z-20 cursor-move select-none rounded-md px-2 py-1 transition-shadow',
          selected
            ? `border-2 ${borderClass} bg-black/15 shadow-[0_0_0_1px_rgba(0,0,0,0.4)]`
            : 'border border-transparent hover:border-white/40',
        )}
      >
        {children}

        {selected && (
          <>
            {/* Label pill */}
            <div className="pointer-events-none absolute -top-6 left-0 flex items-center gap-1.5 rounded bg-zinc-950/85 px-1.5 py-0.5 font-mono text-[9px] text-white">
              <span>{label}</span>
              {rotation !== 0 && <span>{rotation}°</span>}
            </div>

            {onDelete && (
              <button
                type="button"
                aria-label="Delete overlay"
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete();
                }}
                className="absolute -right-2 -top-6 flex h-5 w-5 items-center justify-center rounded bg-red-600 text-white shadow cursor-pointer hover:bg-red-500"
              >
                <Trash2 className="h-3 w-3" />
              </button>
            )}

            {/* 4 Corner Resize Handles */}
            {(
              [
                ['-left-1.5 -top-1.5 cursor-nwse-resize', -1],
                ['-right-1.5 -top-1.5 cursor-nesw-resize', 1],
                ['-left-1.5 -bottom-1.5 cursor-nesw-resize', -1],
                ['-right-1.5 -bottom-1.5 cursor-nwse-resize', 1],
              ] as const
            ).map(([pos, dir], idx) => (
              <div
                key={idx}
                onPointerDown={(e) => startResize(e, dir)}
                className={cn(
                  'absolute h-3 w-3 rounded-full border border-zinc-950 shadow',
                  handleBg,
                  pos,
                )}
              />
            ))}

            {/* Bottom Rotation Handle */}
            <button
              type="button"
              aria-label="Rotate overlay"
              title="Drag to rotate"
              onPointerDown={startRotate}
              className="absolute -bottom-7 left-1/2 -translate-x-1/2 flex h-5 w-5 items-center justify-center rounded-full border border-zinc-950 bg-white text-zinc-900 shadow cursor-grab active:cursor-grabbing"
            >
              <RotateCw className="h-3 w-3" />
            </button>
          </>
        )}
      </div>
    </>
  );
}

export function SelectionOverlay({
  activeSubtitleText,
  activeSubtitleId,
  preset,
  isSplitSeam,
  subtitleBox,
  subtitleSelected,
  onSelectSubtitle,
  onChangeSubtitleBox,
  textOverlays,
  selectedTextId,
  onSelectText,
  onChangeText,
  onDeleteText,
}: {
  activeSubtitleText: string | null;
  activeSubtitleId: string | null;
  preset: SubtitlePreset | undefined;
  isSplitSeam: boolean;
  subtitleBox: SubtitleBoxTransform;
  subtitleSelected: boolean;
  onSelectSubtitle: () => void;
  onChangeSubtitleBox: (patch: Partial<SubtitleBoxTransform>, commit?: boolean) => void;
  textOverlays: TextOverlayItem[];
  selectedTextId: string | null;
  onSelectText: (id: string) => void;
  onChangeText: (id: string, patch: Partial<TextOverlayItem>, commit?: boolean) => void;
  onDeleteText: (id: string) => void;
}) {
  const [editingOverlayId, setEditingOverlayId] = useState<string | null>(null);

  const words = (activeSubtitleText || '').trim().split(/\s+/).filter(Boolean).slice(0, 6);
  const highlightIdx = words.length > 1 ? 1 : 0;

  return (
    <div className="pointer-events-auto absolute inset-0 overflow-hidden">
      {/* Draggable / Resizable / Rotatable Active Subtitle Box */}
      {words.length > 0 && preset && (
        <DraggableTransformBox
          x={subtitleBox.x}
          y={isSplitSeam ? 0.5 : subtitleBox.y}
          width={subtitleBox.width}
          rotation={subtitleBox.rotation}
          selected={subtitleSelected}
          onSelect={onSelectSubtitle}
          onChange={(patch, commit) => onChangeSubtitleBox(patch, commit)}
          label={isSplitSeam ? `Style: Seam · ${preset.display_name}` : preset.display_name}
          accent="violet"
        >
          <div
            data-caption-id={activeSubtitleId || undefined}
            style={{
              fontFamily: `"${preset.font_name}", "Noto Sans Devanagari", "Inter", sans-serif`,
              fontWeight: preset.bold ? 800 : 600,
              fontStyle: preset.italic ? 'italic' : 'normal',
              textTransform: preset.uppercase ? 'uppercase' : 'none',
              backgroundColor:
                preset.border_style === 3 ? preset.back_hex || 'rgba(0,0,0,0.75)' : 'transparent',
              textShadow:
                preset.border_style === 3
                  ? 'none'
                  : `0 2px ${Math.max(4, preset.outline * 2)}px ${preset.outline_hex || '#000'}, 0 0 2px #000`,
            }}
            className="flex flex-wrap items-center justify-center gap-x-1.5 rounded-md px-2 py-1 text-center text-base leading-tight tracking-tight"
          >
            {words.map((w, idx) => (
              <span
                key={idx}
                style={{
                  color: idx === highlightIdx ? preset.active_hex : preset.primary_hex,
                  transform:
                    idx === highlightIdx
                      ? `scale(${(preset.pop_scale_percent || 112) / 100})`
                      : undefined,
                }}
                className="inline-block"
              >
                {w}
              </span>
            ))}
          </div>
        </DraggableTransformBox>
      )}

      {/* Draggable / Resizable / Rotatable Text Overlays */}
      {textOverlays.map((ov) => {
        const isSel = selectedTextId === ov.id;
        const isEd = editingOverlayId === ov.id;
        return (
          <DraggableTransformBox
            key={ov.id}
            x={ov.x}
            y={ov.y}
            width={ov.width}
            rotation={ov.rotation}
            selected={isSel}
            onSelect={() => onSelectText(ov.id)}
            onChange={(patch, commit) => onChangeText(ov.id, patch, commit)}
            onDelete={() => onDeleteText(ov.id)}
            label={ov.category}
            accent="lime"
          >
            <div
              onDoubleClick={(e) => {
                e.stopPropagation();
                setEditingOverlayId(ov.id);
              }}
              style={{
                fontFamily: ov.fontFamily,
                fontSize: `${Math.max(14, Math.min(36, ov.fontSize))}px`,
                fontWeight: ov.fontWeight,
                fontStyle: ov.italic ? 'italic' : 'normal',
                textTransform: ov.uppercase ? 'uppercase' : 'none',
                color: ov.color,
                backgroundColor: ov.backgroundColor || 'transparent',
                letterSpacing: ov.letterSpacing,
              }}
              className="rounded-md px-2.5 py-1 text-center leading-tight drop-shadow-[0_2px_6px_rgba(0,0,0,0.7)]"
            >
              {isEd ? (
                <input
                  autoFocus
                  value={ov.text}
                  onPointerDown={(e) => e.stopPropagation()}
                  onChange={(e) => onChangeText(ov.id, { text: e.target.value }, false)}
                  onBlur={() => {
                    setEditingOverlayId(null);
                    onChangeText(ov.id, {}, true);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === 'Escape') {
                      setEditingOverlayId(null);
                      onChangeText(ov.id, {}, true);
                    }
                  }}
                  className="w-full bg-black/50 text-center outline-none rounded px-1"
                  style={{ color: ov.color }}
                />
              ) : (
                <>
                  <div>{ov.text}</div>
                  {ov.subtext && (
                    <div className="mt-0.5 text-[11px] font-medium opacity-85">{ov.subtext}</div>
                  )}
                </>
              )}
            </div>
          </DraggableTransformBox>
        );
      })}
    </div>
  );
}
