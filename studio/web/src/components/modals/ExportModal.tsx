import { useState, useMemo } from 'react';
import { X, Sparkles, Download, HardDrive, Check } from 'lucide-react';
import { Button, Badge } from '@/components/ui/Primitives';
import { estimateExportSizeBytes } from '@/lib/format';

export interface ExportConfig {
  resolution: '1080p' | '1440p' | '2160p' | '4k';
  codec: 'hevc' | 'h264' | 'auto';
  clarityPercent: number;
  audioBitrate: '192k' | '256k' | '320k';
}

interface ExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirmExport: (config: ExportConfig) => Promise<void>;
  clipCount: number;
  totalDurationSeconds: number;
  nvencAvailable?: boolean;
}

export function ExportModal({
  isOpen,
  onClose,
  onConfirmExport,
  clipCount,
  totalDurationSeconds,
  nvencAvailable = true,
}: ExportModalProps) {
  const [resolution, setResolution] = useState<'1080p' | '1440p' | '2160p'>('1440p');
  const [codec, setCodec] = useState<'hevc' | 'h264'>('hevc');
  const [clarityPercent, setClarityPercent] = useState<number>(45);
  const [audioBitrate, setAudioBitrate] = useState<'192k' | '256k' | '320k'>('256k');
  const [isExporting, setIsExporting] = useState(false);

  const estimatedBytes = useMemo(() => {
    return estimateExportSizeBytes(
      totalDurationSeconds,
      resolution,
      codec,
      'balanced',
      parseInt(audioBitrate),
    );
  }, [totalDurationSeconds, resolution, codec, audioBitrate]);

  const estimatedMb = (estimatedBytes / (1024 * 1024)).toFixed(1);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div className="w-full max-w-xl rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-6 shadow-2xl space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--accent-lime-soft)] text-[var(--accent-lime-strong)]">
              <Download className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-[var(--text-primary)]">
                Export Master Video Package
              </h2>
              <p className="text-xs text-[var(--text-muted)]">
                Bundling {clipCount} verified clip(s) · {Math.round(totalDurationSeconds)}s total
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close export dialog"
            className="rounded-lg p-1.5 text-[var(--text-muted)] hover:bg-[var(--bg-panel)] cursor-pointer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Resolution Ladder Selection */}
        <div className="space-y-2">
          <label className="text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
            Resolution Ladder (Vertical 9:16)
          </label>
          <div className="grid grid-cols-3 gap-2.5">
            {[
              { id: '1080p', label: '1080p HD', sub: '1080x1920', badge: 'Fast' },
              { id: '1440p', label: '2K QHD', sub: '1440x2560', badge: 'VP9 Gate ★' },
              { id: '2160p', label: '4K UHD', sub: '2160x3840', badge: 'Archive' },
            ].map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setResolution(item.id as '1080p' | '1440p' | '2160p')}
                className={`flex flex-col items-start p-3 rounded-xl border text-left transition-all cursor-pointer ${
                  resolution === item.id
                    ? 'border-[var(--accent-lime-border)] bg-[var(--accent-lime-soft)]/20 shadow-xs'
                    : 'border-[var(--border-subtle)] bg-[var(--bg-panel)] hover:border-[var(--border-strong)]'
                }`}
              >
                <div className="flex items-center justify-between w-full">
                  <span className="font-bold text-xs">{item.label}</span>
                  <Badge tone={resolution === item.id ? 'pass' : 'neutral'} className="text-[9px]">
                    {item.badge}
                  </Badge>
                </div>
                <span className="text-[11px] font-mono text-[var(--text-muted)] mt-1">
                  {item.sub}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Codec & Hardware Accelerators */}
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div>
            <label className="font-semibold text-[var(--text-secondary)]">Codec Target</label>
            <select
              value={codec}
              onChange={(e) => setCodec(e.target.value as 'hevc' | 'h264')}
              className="mt-1 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-2 text-xs font-medium text-[var(--text-primary)] cursor-pointer"
            >
              <option value="hevc">HEVC / H.265 (40% Smaller · Universal hvc1)</option>
              <option value="h264">H.264 / AVC (Legacy Compatibility)</option>
            </select>
          </div>
          <div>
            <label className="font-semibold text-[var(--text-secondary)]">Audio Bitrate</label>
            <select
              value={audioBitrate}
              onChange={(e) => setAudioBitrate(e.target.value as '192k' | '256k' | '320k')}
              className="mt-1 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-2 text-xs font-medium text-[var(--text-primary)] cursor-pointer"
            >
              <option value="192k">192 kbps (Standard Mobile)</option>
              <option value="256k">256 kbps (High Fidelity)</option>
              <option value="320k">320 kbps (Master Studio)</option>
            </select>
          </div>
        </div>

        {/* Detail Recovery & Clarity (FidelityFX CAS) */}
        <div className="space-y-2 rounded-xl bg-[var(--bg-panel)] p-3.5 border border-[var(--border-subtle)]">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-semibold">
              <Sparkles className="h-3.5 w-3.5 text-[var(--accent-lime-strong)]" />
              Detail Recovery &amp; Unblur (AMD FidelityFX CAS)
            </span>
            <span className="font-mono text-xs font-bold">{clarityPercent}%</span>
          </div>
          <input
            type="range"
            min="0"
            max="100"
            value={clarityPercent}
            onChange={(e) => setClarityPercent(Number(e.target.value))}
            className="w-full accent-[var(--accent-lime-strong)] cursor-pointer"
          />
          <div className="flex justify-between text-[10px] text-[var(--text-muted)]">
            <span>Natural Passthrough (0%)</span>
            <span>Balanced Detail (45%)</span>
            <span>Max Recovery (100%)</span>
          </div>
        </div>

        {/* Real-time File Size & Hardware Summary */}
        <div className="flex items-center justify-between rounded-xl bg-[var(--bg-canvas)] px-4 py-3 border border-[var(--border-subtle)] text-xs">
          <div className="flex items-center gap-2">
            <HardDrive className="h-4 w-4 text-[var(--text-muted)]" />
            <span className="text-[var(--text-secondary)]">Est. Output Size:</span>
            <span className="font-mono font-bold text-[var(--text-primary)]">~{estimatedMb} MB</span>
          </div>
          <div className="flex items-center gap-1.5 text-[var(--text-muted)] text-[11px]">
            <Check className="h-3.5 w-3.5 text-[var(--status-pass)]" />
            <span>Tag: hvc1 · Rec.709 · -14 LUFS {nvencAvailable ? '· NVENC GPU' : '· CPU'}</span>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <Button variant="ghost" onClick={onClose} disabled={isExporting}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={async () => {
              setIsExporting(true);
              try {
                await onConfirmExport({ resolution, codec, clarityPercent, audioBitrate });
                onClose();
              } finally {
                setIsExporting(false);
              }
            }}
            disabled={isExporting}
            className="rounded-full px-5"
          >
            {isExporting ? 'Dispatching...' : `Export ${clipCount} Clip(s) in ${resolution.toUpperCase()}`}
          </Button>
        </div>
      </div>
    </div>
  );
}
