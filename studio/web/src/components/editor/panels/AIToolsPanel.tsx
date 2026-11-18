import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Crop, Sparkles, Wand2 } from 'lucide-react';
import { studioApi } from '@/lib/api';
import { cn } from '@/lib/format';
import {
  toast,
  useProjectStore,
  useSupervisorStore,
  useSystemStore,
} from '@/stores/useStudioStore';
import { useEditorStore } from '@/stores/useEditorStore';
import { Badge, Button } from '@/components/ui/Primitives';

interface ToggleRowProps {
  title: string;
  description: string;
  checked: boolean;
  badge?: string;
  onToggle: (next: boolean) => void;
}

function AiToggleRow({ title, description, checked, badge, onToggle }: ToggleRowProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onToggle(!checked)}
      className={cn(
        'flex w-full items-start justify-between gap-3 rounded-[10px] border p-3 text-left transition-all cursor-pointer',
        checked
          ? 'border-[var(--accent-lime-border)] bg-[var(--accent-lime-soft)]/70'
          : 'border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-strong)]',
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-bold text-[var(--text-primary)]">{title}</span>
          {badge && (
            <Badge tone={checked ? 'lime' : 'neutral'} className="text-[9px] px-1.5 py-0">
              {badge}
            </Badge>
          )}
        </div>
        <p className="mt-0.5 text-[11px] text-[var(--text-secondary)] leading-snug">
          {description}
        </p>
      </div>
      <span
        className={cn(
          'mt-0.5 inline-flex h-5 w-9 shrink-0 items-center rounded-full p-0.5 transition-colors',
          checked ? 'bg-[var(--accent-lime-strong)]' : 'bg-[var(--border-strong)]',
        )}
      >
        <span
          className={cn(
            'h-4 w-4 rounded-full bg-white shadow-xs transition-transform',
            checked ? 'translate-x-4' : 'translate-x-0',
          )}
        />
      </span>
    </button>
  );
}

export function AIToolsPanel() {
  const { projectId = 'demo' } = useParams();
  const { setDockOpen } = useSystemStore();
  const { activeClipId } = useProjectStore();
  const { ensureSessionForProject, setRunning } = useSupervisorStore();
  const { aiTools, updateAiTools, setStageViewMode, stageViewMode } = useEditorStore();
  const [dispatching, setDispatching] = useState(false);

  const runToolDirective = async (action: string, params: Record<string, unknown>) => {
    if (projectId === 'demo') {
      toast.info(`AI Tool preview: ${action}`, 'Open a real project to execute via Executive Producer.');
      return;
    }
    setDispatching(true);
    try {
      const sid = await ensureSessionForProject(projectId);
      await studioApi.sendToolAction(sid, { action, params, project_id: projectId });
      setRunning(true);
      setDockOpen(true);
      toast.success('AI Tool directive dispatched', action);
    } catch (e) {
      toast.error('AI Tool action failed', String(e));
    } finally {
      setDispatching(false);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b border-[var(--border-subtle)] px-4 py-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-[var(--text-primary)]">AI Tools</h2>
          <Badge tone="lime" className="font-mono text-[10px]">
            Reframe v2
          </Badge>
        </div>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          Toggle local GPU &amp; OpenMontage enhancements, then apply via Executive Producer.
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3.5 space-y-2.5">
        {/* Reframe v2 Layout Mode */}
        <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-3 space-y-2">
          <div className="flex items-center justify-between text-xs font-bold">
            <span>Smart Reframe v2 Mode</span>
            <button
              type="button"
              onClick={() =>
                setStageViewMode(stageViewMode === 'reframe_crop' ? 'preview' : 'reframe_crop')
              }
              className="inline-flex items-center gap-1 text-[11px] font-semibold text-[var(--accent-lime-strong)] hover:underline cursor-pointer"
            >
              <Crop className="h-3 w-3" />
              {stageViewMode === 'reframe_crop' ? 'Exit Crop' : 'Edit 16:9 Crop'}
            </button>
          </div>
          <select
            aria-label="Smart Reframe v2 layout mode"
            value={aiTools.layoutMode}
            onChange={(e) =>
              updateAiTools({ layoutMode: e.target.value as typeof aiTools.layoutMode })
            }
            className="h-8 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 text-xs font-medium"
          >
            <option value="auto">Auto (YuNet + 2-Speaker Split)</option>
            <option value="stacked_split">Stacked 2-Speaker Split</option>
            <option value="single_crop">Single Active-Speaker Track</option>
            <option value="speaker_cut">Fast Active-Speaker Cut</option>
            <option value="blurred_pillarbox">Blurred Pillarbox (General)</option>
          </select>
        </div>

        <AiToggleRow
          title="Emphasis Punch-In (1.15×)"
          description="Automatic subtle zoom beats on high-energy spoken hooks."
          badge="punch_in"
          checked={aiTools.enablePunchIn}
          onToggle={(v) => updateAiTools({ enablePunchIn: v })}
        />

        <AiToggleRow
          title="Magic Cut · Silence Removal"
          description="Trim dead air and long pauses using FFmpeg silencedetect."
          badge="silence_cutter"
          checked={aiTools.magicSilenceCut}
          onToggle={(v) => updateAiTools({ magicSilenceCut: v })}
        />

        <AiToggleRow
          title="Broadcast Audio (−14 LUFS)"
          description="Single-pass EBU R128 loudness normalization & −2.0 dBTP limiter."
          badge="loudnorm"
          checked={aiTools.broadcastLoudnorm}
          onToggle={(v) => updateAiTools({ broadcastLoudnorm: v })}
        />

        <AiToggleRow
          title="Clean Audio · Voice Enhance"
          description="Remove room noise & hiss via local FFmpeg audio_enhance."
          badge="audio_enhance"
          checked={aiTools.voiceDenoise}
          onToggle={(v) => updateAiTools({ voiceDenoise: v })}
        />

        <AiToggleRow
          title="Auto Style: Seam Split Captions"
          description="Centers subtitles on the 2-speaker seam automatically during split ranges."
          badge="Seam"
          checked={aiTools.seamSubtitles}
          onToggle={(v) => updateAiTools({ seamSubtitles: v })}
        />
      </div>

      <div className="border-t border-[var(--border-subtle)] p-4 space-y-2">
        <Button
          variant="primary"
          size="sm"
          className="w-full rounded-full"
          disabled={dispatching}
          onClick={() =>
            void runToolDirective('apply_ai_enhancements', {
              candidate_id: activeClipId,
              ...aiTools,
            })
          }
        >
          <Wand2 className="h-3.5 w-3.5" />
          Apply Enabled AI Tools via Producer
        </Button>
        <Button
          variant="secondary"
          size="xs"
          className="w-full"
          disabled={dispatching}
          onClick={() => void runToolDirective('clip_selector', { target_clips: 3 })}
        >
          <Sparkles className="h-3.5 w-3.5 text-[var(--accent-lime-strong)]" />
          Discover Viral Clips (5-Pt Cold Viewer)
        </Button>
      </div>
    </div>
  );
}
