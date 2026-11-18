import { useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Cpu,
  Image as ImageIcon,
  Layers,
  Music,
  ShieldAlert,
  Sparkles,
  Upload,
  Volume2,
} from 'lucide-react';
import { buildMediaUrl, studioApi } from '@/lib/api';
import { cn, formatBytes } from '@/lib/format';
import {
  toast,
  useNleStore,
  useProjectStore,
  useSupervisorStore,
  useSystemStore,
} from '@/stores/useStudioStore';
import { useEditorStore } from '@/stores/useEditorStore';
import { useBrandKitStore } from '@/stores/useBrandKitStore';
import { Badge, Button } from '@/components/ui/Primitives';
import type { AspectRatioId } from '@/types/editor';

export function AudioPanel() {
  const { projectId = 'demo' } = useParams();
  const { musicLibrary, loadMusicLibrary, setDockOpen } = useSystemStore();
  const { boardState } = useProjectStore();
  const { ensureSessionForProject, setRunning } = useSupervisorStore();
  const { aiTools, updateAiTools } = useEditorStore();

  useEffect(() => {
    void loadMusicLibrary();
  }, [loadMusicLibrary]);

  const activeClip = boardState?.clip_studio?.clips?.[0] ?? null;
  const lufs = activeClip?.qa?.integrated_lufs;
  const truePeak = activeClip?.qa?.true_peak_dbtp;

  const attachTrack = async (relPath: string, name: string) => {
    if (projectId === 'demo') {
      toast.info(`Auditioning "${name}"`, 'Open a real project to mix via audio_mixer.');
      return;
    }
    try {
      const sid = await ensureSessionForProject(projectId);
      await studioApi.sendToolAction(sid, {
        action: 'audio_mixer',
        params: { music_track: `music_library/${relPath}`, duck_under_speech: true },
        project_id: projectId,
      });
      setRunning(true);
      setDockOpen(true);
      toast.success('Music mix directive sent', name);
    } catch (e) {
      toast.error('Could not dispatch audio mix', String(e));
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-[var(--border-subtle)] px-4 py-3">
        <h2 className="text-base font-bold text-[var(--text-primary)]">Audio</h2>
        <p className="mt-0.5 text-xs text-[var(--text-muted)]">
          Local royalty-free music library, EBU R128 loudness &amp; TTS narration.
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3.5 space-y-4">
        {/* Broadcast Loudness Telemetry */}
        <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-3 space-y-2">
          <div className="flex items-center justify-between text-xs font-bold">
            <span className="inline-flex items-center gap-1.5">
              <Volume2 className="h-3.5 w-3.5 text-[var(--accent-cyan)]" />
              EBU R128 Broadcast Target
            </span>
            <Badge tone="neutral" className="font-mono text-[10px]">
              −14 LUFS
            </Badge>
          </div>
          <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-2.5 py-1.5">
              <div className="text-[9px] text-[var(--text-muted)]">INTEGRATED</div>
              <div className="font-bold">
                {lufs != null ? `${lufs.toFixed(1)} LUFS` : 'UNMEASURED'}
              </div>
            </div>
            <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-2.5 py-1.5">
              <div className="text-[9px] text-[var(--text-muted)]">TRUE PEAK</div>
              <div className="font-bold">
                {truePeak != null ? `${truePeak.toFixed(1)} dBTP` : 'UNMEASURED'}
              </div>
            </div>
          </div>
          <label className="flex items-center justify-between text-xs cursor-pointer pt-1">
            <span className="text-[var(--text-secondary)]">Enforce single-pass loudnorm</span>
            <input
              type="checkbox"
              checked={aiTools.broadcastLoudnorm}
              onChange={(e) => updateAiTools({ broadcastLoudnorm: e.target.checked })}
              className="h-3.5 w-3.5 accent-[var(--accent-lime-strong)]"
            />
          </label>
        </div>

        {/* Local music_library/ Tracks */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-[var(--text-primary)]">
              Local Music Library ({musicLibrary?.count ?? 0})
            </span>
          </div>
          {!musicLibrary || musicLibrary.tracks.length === 0 ? (
            <div className="rounded-[10px] border border-dashed border-[var(--border-strong)] p-5 text-center space-y-1">
              <Music className="mx-auto h-4 w-4 text-[var(--text-muted)]" />
              <div className="text-xs font-semibold">No local tracks yet</div>
              <p className="text-[11px] text-[var(--text-muted)]">
                Drop .mp3 or .wav files into <code className="font-mono">music_library/</code> to
                audition &amp; mix free.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {musicLibrary.tracks.map((tr) => (
                <div
                  key={tr.rel_path}
                  className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-2.5 space-y-1.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-xs font-semibold">{tr.name}</span>
                    <Button
                      size="xs"
                      variant="secondary"
                      onClick={() => void attachTrack(tr.rel_path, tr.name)}
                    >
                      Use
                    </Button>
                  </div>
                  <div className="font-mono text-[10px] text-[var(--text-muted)]">
                    {formatBytes(tr.size_bytes)}
                  </div>
                  <audio controls preload="none" src={tr.stream_url} className="h-7 w-full" />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function ImagePanel() {
  const { projectId = 'demo' } = useParams();
  const { boardState } = useProjectStore();
  const { saveItem } = useBrandKitStore();
  const fileRef = useRef<HTMLInputElement>(null);

  const scenes = boardState?.storyboard?.scenes ?? [];

  const handleUpload = async (file: File) => {
    try {
      const res = await studioApi.uploadMediaFile(file);
      await saveItem('image', res.filename, { path: res.path, size_bytes: res.size_bytes });
      toast.success('Image uploaded', res.filename);
    } catch (e) {
      toast.error('Image upload failed', String(e));
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void handleUpload(f);
          e.target.value = '';
        }}
      />
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
        <h2 className="text-base font-bold text-[var(--text-primary)]">Images &amp; Scenes</h2>
        <Button size="xs" variant="secondary" onClick={() => fileRef.current?.click()}>
          <Upload className="h-3.5 w-3.5" /> Upload
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-3.5 space-y-2.5">
        {scenes.length === 0 ? (
          <div className="rounded-[10px] border border-dashed border-[var(--border-strong)] p-6 text-center space-y-1.5">
            <ImageIcon className="mx-auto h-5 w-5 text-[var(--text-muted)]" />
            <div className="text-xs font-bold">No storyboard images yet</div>
            <p className="text-[11px] text-[var(--text-muted)]">
              Generated scene visuals, B-roll stills, and Atelier snapshots appear here automatically.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {scenes.map((sc, idx) => {
              const imgPath = sc.visual?.path;
              const src =
                imgPath && projectId !== 'demo' ? buildMediaUrl(projectId, imgPath) : null;
              return (
                <div
                  key={String(sc.id ?? idx)}
                  className="overflow-hidden rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-panel)]"
                >
                  <div className="aspect-video bg-zinc-900">
                    {src ? (
                      <img src={src} alt={`Scene ${idx + 1}`} className="h-full w-full object-cover" />
                    ) : (
                      <div className="flex h-full items-center justify-center font-mono text-[10px] text-zinc-400">
                        Scene {idx + 1}
                      </div>
                    )}
                  </div>
                  <div className="p-2 text-[11px] font-medium truncate">
                    {sc.section_label || sc.description || `Scene ${idx + 1}`}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

export function ElementsPanel() {
  const { showSafeZones, setShowSafeZones } = useNleStore();
  const { aiTools, updateAiTools } = useEditorStore();

  const remotionBlocks = [
    { id: 'stat_card', label: 'Stat Reveal Card', desc: 'Animated KPI number with spring entrance' },
    { id: 'progress_bar', label: 'Top Progress Bar', desc: 'Synced playback bar for Shorts retention' },
    { id: 'callout', label: 'Callout Badge', desc: 'Highlighted key insight banner' },
    { id: 'terminal_scene', label: 'Synthetic Terminal', desc: 'Deterministic CLI recording scene' },
  ];

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-[var(--border-subtle)] px-4 py-3">
        <h2 className="text-base font-bold text-[var(--text-primary)]">Elements</h2>
        <p className="mt-0.5 text-xs text-[var(--text-muted)]">
          Safe zones, motion overlays, and OpenMontage scene elements.
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3.5 space-y-4">
        <div className="space-y-2">
          <div className="text-xs font-bold">Broadcast Guides</div>
          <button
            type="button"
            onClick={() => setShowSafeZones(!showSafeZones)}
            className={cn(
              'flex w-full items-center justify-between rounded-[10px] border p-3 text-left text-xs font-semibold cursor-pointer',
              showSafeZones
                ? 'border-[var(--accent-lime-border)] bg-[var(--accent-lime-soft)]'
                : 'border-[var(--border-subtle)] bg-[var(--bg-surface)]',
            )}
          >
            <span className="inline-flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-[var(--accent-amber)]" />
              TikTok / Reels / Shorts Safe Zones
            </span>
            <Badge tone={showSafeZones ? 'lime' : 'neutral'}>{showSafeZones ? 'ON' : 'OFF'}</Badge>
          </button>

          <button
            type="button"
            onClick={() => updateAiTools({ enablePunchIn: !aiTools.enablePunchIn })}
            className={cn(
              'flex w-full items-center justify-between rounded-[10px] border p-3 text-left text-xs font-semibold cursor-pointer',
              aiTools.enablePunchIn
                ? 'border-[var(--accent-lime-border)] bg-[var(--accent-lime-soft)]'
                : 'border-[var(--border-subtle)] bg-[var(--bg-surface)]',
            )}
          >
            <span className="inline-flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-[var(--accent-lime-strong)]" />
              Punch-In Beat Keyframes
            </span>
            <Badge tone={aiTools.enablePunchIn ? 'lime' : 'neutral'}>
              {aiTools.enablePunchIn ? 'ON' : 'OFF'}
            </Badge>
          </button>
        </div>

        <div className="space-y-2">
          <div className="text-xs font-bold">Motion Overlays (Templated Mode)</div>
          <div className="space-y-1.5">
            {remotionBlocks.map((b) => (
              <button
                key={b.id}
                type="button"
                onClick={() =>
                  toast.info(`Queued "${b.label}"`, 'Send a Producer prompt to attach to edit_decisions.json.')
                }
                className="flex w-full items-center gap-2.5 rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-2.5 text-left hover:border-[var(--accent-lime-border)] cursor-pointer"
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--bg-panel)] text-[var(--text-secondary)]">
                  <Layers className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-semibold">{b.label}</div>
                  <div className="truncate text-[11px] text-[var(--text-muted)]">{b.desc}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

const CANVAS_SWATCHES = ['#0b0d11', '#ffffff', '#14452f', '#1e1b4b', '#1c1917', '#0f172a'];

export function SettingsPanel() {
  const navigate = useNavigate();
  const { health } = useSystemStore();
  const { aspectRatio, setAspectRatio, canvasBg, setCanvasBg } = useEditorStore();

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-[var(--border-subtle)] px-4 py-3">
        <h2 className="text-base font-bold text-[var(--text-primary)]">Settings</h2>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5 text-xs">
        <div className="space-y-2">
          <label className="block font-bold text-[var(--text-primary)]">Canvas Size</label>
          <div className="grid grid-cols-2 gap-1.5">
            {(
              [
                ['9:16', 'Portrait 9:16'],
                ['16:9', 'Landscape 16:9'],
                ['1:1', 'Square 1:1'],
                ['4:5', 'Social 4:5'],
              ] as Array<[AspectRatioId, string]>
            ).map(([ratio, label]) => (
              <button
                key={ratio}
                type="button"
                onClick={() => setAspectRatio(ratio)}
                className={cn(
                  'rounded-[10px] border px-3 py-2 text-left font-medium cursor-pointer',
                  aspectRatio === ratio
                    ? 'border-[var(--accent-lime-border)] bg-[var(--accent-lime-soft)] font-semibold'
                    : 'border-[var(--border-subtle)] bg-[var(--bg-surface)]',
                )}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <label className="block font-bold text-[var(--text-primary)]">Background Color</label>
          <div className="flex flex-wrap gap-2">
            {CANVAS_SWATCHES.map((hex) => (
              <button
                key={hex}
                type="button"
                aria-label={`Canvas background ${hex}`}
                onClick={() => setCanvasBg(hex)}
                style={{ backgroundColor: hex }}
                className={cn(
                  'h-7 w-7 rounded-full border-2 cursor-pointer transition-transform hover:scale-110',
                  canvasBg === hex ? 'border-[var(--accent-lime-border)] ring-2 ring-[var(--accent-lime)]' : 'border-[var(--border-strong)]',
                )}
              />
            ))}
          </div>
        </div>

        <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-3 space-y-1.5">
          <div className="font-bold text-[var(--text-primary)]">Hardware Telemetry</div>
          <div className="flex justify-between font-mono text-[11px]">
            <span className="text-[var(--text-muted)]">Encoder</span>
            <span>{health?.nvenc_available ? 'h264_nvenc (GPU)' : 'libx264 (CPU)'}</span>
          </div>
          <div className="flex justify-between font-mono text-[11px]">
            <span className="text-[var(--text-muted)]">Face Tracker</span>
            <span>{health?.face_detector || 'yunet'}</span>
          </div>
          <div className="flex justify-between font-mono text-[11px]">
            <span className="text-[var(--text-muted)]">Top Supervisor</span>
            <span>{health?.fcc_online ? 'FCC Online' : 'FCC Standby'}</span>
          </div>
        </div>

        <Button
          variant="secondary"
          size="sm"
          className="w-full"
          onClick={() => navigate('/system')}
        >
          <Cpu className="h-3.5 w-3.5" />
          Open System &amp; 169-Tool Matrix
        </Button>
      </div>
    </div>
  );
}
