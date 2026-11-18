import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  CheckCircle2,
  Download,
  Gauge,
  Loader2,
  PackageCheck,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { studioApi } from '@/lib/api';
import { cn, formatTimecode, lufsStatus } from '@/lib/format';
import { toast, useProjectStore, useSupervisorStore } from '@/stores/useStudioStore';
import { Badge, Button, EmptyState, Panel } from '@/components/ui/Primitives';

function LoudnessBar({ lufs, truePeak }: { lufs?: number; truePeak?: number }) {
  const status = lufsStatus(lufs);
  // Map -28 .. 0 LUFS onto 0..100%
  const pct =
    lufs != null && Number.isFinite(lufs)
      ? Math.max(0, Math.min(100, ((lufs + 28) / 28) * 100))
      : 0;
  // Target window [-16, -12] -> [42.8%, 57.1%]
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-[var(--text-muted)]">EBU R128 Loudness (Target −14 LUFS)</span>
        <span
          className={cn(
            'font-mono font-bold',
            status === 'pass'
              ? 'text-[var(--status-pass)]'
              : status === 'warn'
                ? 'text-[var(--status-warn)]'
                : status === 'fail'
                  ? 'text-[var(--status-fail)]'
                  : 'text-[var(--text-muted)]',
          )}
        >
          {lufs != null ? `${lufs.toFixed(1)} LUFS` : 'Not measured'}
          {truePeak != null ? ` · ${truePeak.toFixed(1)} dBTP` : ''}
        </span>
      </div>
      <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-[var(--bg-canvas)] border border-[var(--border-subtle)]">
        {/* Target broadcast green zone [-16..-12] */}
        <div
          style={{ left: '42.8%', width: '14.3%' }}
          className="absolute inset-y-0 bg-[var(--status-pass)]/25 border-x border-[var(--status-pass)]/60"
        />
        {lufs != null && (
          <div
            style={{ width: `${pct}%` }}
            className={cn(
              'h-full rounded-full transition-all',
              status === 'pass'
                ? 'bg-[var(--status-pass)]'
                : status === 'warn'
                  ? 'bg-[var(--status-warn)]'
                  : 'bg-[var(--status-fail)]',
            )}
          />
        )}
      </div>
    </div>
  );
}

export function BroadcastQaWorkspace() {
  const { projectId } = useParams();
  const { boardState } = useProjectStore();
  const { ensureSessionForProject, setRunning } = useSupervisorStore();
  const [selectedForExport, setSelectedForExport] = useState<Record<string, boolean>>({});
  const [exporting, setExporting] = useState(false);

  const clips = useMemo(() => boardState?.clip_studio?.clips ?? [], [boardState]);
  const finalReview = (boardState?.artifacts?.final_review as Record<string, unknown>) || null;
  const exportManifest = boardState?.clip_studio?.export_manifest ?? null;

  const eligibleIds = useMemo(
    () =>
      clips
        .filter((c) => selectedForExport[c.candidate_id])
        .map((c) => c.clip_id || c.candidate_id),
    [clips, selectedForExport],
  );

  const handleExport = async () => {
    if (!projectId || eligibleIds.length === 0) return;
    setExporting(true);
    try {
      const sid = await ensureSessionForProject(projectId);
      await studioApi.exportClips(sid, { clip_ids: eligibleIds, project_id: projectId });
      setRunning(true);
      toast.success('Export bundle dispatched', `Bundling ${eligibleIds.length} QA-verified clip(s).`);
    } catch (e) {
      toast.error('Export failed', String(e));
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1360px] space-y-5 p-5">
      {/* Header + 1-Click Export CTA */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-[var(--status-pass)]" />
            <h1 className="text-base font-bold tracking-tight">Broadcast QA &amp; Export Studio</h1>
          </div>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            EBU R128 loudness (−14 LUFS / −2.0 dBTP), yuv420p + faststart, metadata scrub, 5-point cold-viewer audit, and hard-gated bundle exports.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="primary"
            disabled={exporting || eligibleIds.length === 0}
            onClick={handleExport}
          >
            {exporting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <PackageCheck className="h-4 w-4" />
            )}
            Export Verified Bundle ({eligibleIds.length})
          </Button>
        </div>
      </div>

      {/* Clip-Level Broadcast QA Cards */}
      {clips.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {clips.map((clip) => {
            const qa = clip.qa_report;
            const probe = qa?.technical_probe;
            const audio = qa?.audio_spotcheck;
            const passed = Boolean(qa?.passed || clip.production_state === 'QA_PASSED');
            const audit = clip.cold_viewer_audit || {};
            const checked = Boolean(selectedForExport[clip.candidate_id]);

            return (
              <Panel key={clip.candidate_id} className="p-4 space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <label className="flex items-start gap-2.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) =>
                        setSelectedForExport((s) => ({
                          ...s,
                          [clip.candidate_id]: e.target.checked,
                        }))
                      }
                      className="mt-1 h-4 w-4 accent-[var(--accent-amber)]"
                    />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold">{clip.candidate_id}</span>
                        <Badge tone={passed ? 'pass' : 'warn'}>
                          {passed ? 'QA PASSED' : clip.production_state || 'PENDING QA'}
                        </Badge>
                        {clip.exported && <Badge tone="cyan">EXPORTED</Badge>}
                      </div>
                      <p className="mt-0.5 text-xs text-[var(--text-secondary)] line-clamp-1">
                        {clip.spoken_hook || clip.hook_text || clip.title || 'Clip render'}
                      </p>
                    </div>
                  </label>

                  {clip.render_url && (
                    <a
                      href={clip.render_url}
                      download
                      className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1 text-[11px] font-medium hover:border-[var(--border-strong)]"
                    >
                      <Download className="h-3 w-3" /> MP4
                    </a>
                  )}
                </div>

                {/* Loudness Meter */}
                <LoudnessBar lufs={audio?.integrated_lufs} truePeak={audio?.true_peak_dbtp} />

                {/* Technical Probe Grid */}
                <div className="grid grid-cols-3 gap-2 font-mono text-[11px]">
                  <div className="rounded-lg bg-[var(--bg-canvas)] p-2 border border-[var(--border-subtle)]">
                    <div className="text-[9px] text-[var(--text-muted)]">RES / FPS</div>
                    <div>
                      {probe?.width || '—'}×{probe?.height || '—'} · {probe?.fps ? Math.round(probe.fps) : '—'}
                    </div>
                  </div>
                  <div className="rounded-lg bg-[var(--bg-canvas)] p-2 border border-[var(--border-subtle)]">
                    <div className="text-[9px] text-[var(--text-muted)]">CODEC / PIX</div>
                    <div>
                      {probe?.video_codec || '—'} · {probe?.pix_fmt || '—'}
                    </div>
                  </div>
                  <div className="rounded-lg bg-[var(--bg-canvas)] p-2 border border-[var(--border-subtle)]">
                    <div className="text-[9px] text-[var(--text-muted)]">DURATION</div>
                    <div>
                      {formatTimecode(probe?.duration ?? clip.duration_seconds ?? 0)}
                    </div>
                  </div>
                </div>

                {/* 5-Point Cold-Viewer Audit */}
                {Object.keys(audit).length > 0 && (
                  <div className="space-y-1.5">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                      Cold-Viewer Audit
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(audit).map(([k, v]) => {
                        const ok = v === true || String(v).toLowerCase() === 'pass';
                        return (
                          <Badge key={k} tone={ok ? 'pass' : 'fail'}>
                            {ok ? (
                              <CheckCircle2 className="h-3 w-3" />
                            ) : (
                              <XCircle className="h-3 w-3" />
                            )}
                            {k.replace(/_/g, ' ')}
                          </Badge>
                        );
                      })}
                    </div>
                  </div>
                )}
              </Panel>
            );
          })}
        </div>
      ) : finalReview ? (
        <Panel className="p-4 space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Gauge className="h-4 w-4 text-[var(--accent-cyan)]" />
            Project Final Review Report <span className="font-mono text-xs text-[var(--text-muted)]">artifacts/final_review.json</span>
          </div>
          <pre className="max-h-[480px] overflow-auto rounded-lg bg-[var(--bg-canvas)] p-3.5 font-mono text-[11px] text-[var(--text-secondary)]">
            {JSON.stringify(finalReview, null, 2)}
          </pre>
        </Panel>
      ) : (
        <EmptyState
          icon={<ShieldCheck className="h-5 w-5" />}
          title="No Broadcast QA reports yet"
          description="Run media_qa after rendering clips or master videos to view live EBU R128 loudness meters, technical probe checks, and 1-click Export Bundles."
        />
      )}

      {/* Export Manifest Preview */}
      {exportManifest && (
        <Panel className="p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold">Export Bundle Manifest <span className="font-mono text-[11px] text-[var(--text-muted)]">exports/manifest.json</span></span>
            <Badge tone="pass">VERIFIED</Badge>
          </div>
          <pre className="max-h-60 overflow-auto rounded-lg bg-[var(--bg-canvas)] p-3 font-mono text-[11px] text-[var(--text-secondary)]">
            {JSON.stringify(exportManifest, null, 2)}
          </pre>
        </Panel>
      )}
    </div>
  );
}
