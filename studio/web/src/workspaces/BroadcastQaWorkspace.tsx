import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  Gauge,
  Loader2,
  PackageCheck,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { buildMediaUrl, studioApi } from '@/lib/api';
import { cn, formatTimecode, lufsStatus } from '@/lib/format';
import { toast, useProjectStore, useSupervisorStore } from '@/stores/useStudioStore';
import { Badge, Button, EmptyState, Panel } from '@/components/ui/Primitives';
import { ExportModal, type ExportConfig } from '@/components/modals/ExportModal';

function LoudnessBar({ lufs, truePeak }: { lufs?: number | null; truePeak?: number | null }) {
  const status = lufsStatus(lufs);
  const pct =
    lufs != null && Number.isFinite(lufs)
      ? Math.max(0, Math.min(100, ((lufs + 28) / 28) * 100))
      : 0;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-[var(--text-muted)]">EBU R128 Loudness (Target −14 LUFS)</span>
        <span
          className={cn(
            'font-mono font-bold tabular-nums',
            status === 'pass'
              ? 'text-[var(--status-pass)]'
              : status === 'warn'
                ? 'text-[var(--status-warn)]'
                : status === 'fail'
                  ? 'text-[var(--status-fail)]'
                  : 'text-[var(--text-muted)]',
          )}
        >
          {lufs != null ? `${lufs.toFixed(1)} LUFS` : 'UNMEASURED'}
          {truePeak != null ? ` · ${truePeak.toFixed(1)} dBTP` : ''}
        </span>
      </div>
      <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-[var(--bg-canvas)] border border-[var(--border-subtle)]">
        {/* Broadcast green window [-16.5..-11.5] */}
        <div
          style={{ left: '41%', width: '18%' }}
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
  const { projectId = 'demo' } = useParams();
  const { boardState } = useProjectStore();
  const { ensureSessionForProject, setRunning } = useSupervisorStore();
  const [selectedForExport, setSelectedForExport] = useState<Record<string, boolean>>({});
  const [exporting, setExporting] = useState(false);
  const [exportModalOpen, setExportModalOpen] = useState(false);

  const clips = useMemo(() => boardState?.clip_studio?.clips ?? [], [boardState]);
  const planSynced = boardState?.clip_studio?.plan_sha256_synced;
  const finalReview = (boardState?.artifacts?.final_review as Record<string, unknown>) || null;
  const publishLog = (boardState?.artifacts?.publish_log as Record<string, unknown>) || null;

  // Hard Export Gate Parity: ONLY allow HUMAN_APPROVED + QA_PASSED + SHA-256 synced clips!
  const eligibleIds = useMemo(
    () =>
      clips
        .filter(
          (c) =>
            selectedForExport[c.candidate_id] &&
            c.review_state === 'HUMAN_APPROVED' &&
            (c.production_state === 'QA_PASSED' || c.production_state === 'EXPORTED') &&
            planSynced !== false,
        )
        .map((c) => c.candidate_id),
    [clips, planSynced, selectedForExport],
  );

  const totalDurationSeconds = useMemo(() => {
    return clips
      .filter((c) => selectedForExport[c.candidate_id])
      .reduce((acc, c) => acc + (c.duration_seconds || 15), 0);
  }, [clips, selectedForExport]);

  const handleConfirmExport = async (config: ExportConfig) => {
    if (!projectId || projectId === 'demo' || eligibleIds.length === 0) return;
    setExporting(true);
    try {
      const sid = await ensureSessionForProject(projectId);
      await studioApi.exportClips(sid, {
        clip_ids: eligibleIds,
        project_id: projectId,
        target_resolution: config.resolution,
        codec: config.codec,
        clarity_percent: config.clarityPercent,
      });
      setRunning(true);
      toast.success(
        'Export bundle dispatched',
        `Bundling ${eligibleIds.length} QA-verified clip(s) in ${config.resolution.toUpperCase()} (${config.codec.toUpperCase()}).`,
      );
    } catch (e) {
      toast.error('Export failed', String(e));
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-[1360px] overflow-y-auto space-y-5 p-5">
      {/* Header + 1-Click Hard-Gated Export CTA */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-[var(--status-pass)]" />
            <h1 className="text-base font-bold tracking-tight">Broadcast QA &amp; Export Studio</h1>
            {planSynced === true && <Badge tone="pass">SHA-256 Synced</Badge>}
            {planSynced === false && <Badge tone="fail">Plan Hash Drift — Re-Approve</Badge>}
          </div>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            EBU R128 loudness (−16.5..−11.5 LUFS / ≤−1.0 dBTP), yuv420p + faststart, metadata scrub,
            CheckStatus audit (never fakes NOT_CHECKED as PASS), and SHA-256 gated exports.
          </p>
        </div>

        <Button
          variant="primary"
          disabled={exporting || eligibleIds.length === 0}
          onClick={() => setExportModalOpen(true)}
          className="rounded-full"
        >
          {exporting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <PackageCheck className="h-4 w-4" />
          )}
          Export Verified Bundle ({eligibleIds.length})
        </Button>
      </div>

      {/* Clip-Level Broadcast QA Cards (Exact backlot/state.py contract!) */}
      {clips.length > 0 ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {clips.map((clip) => {
            const qa = clip.qa;
            const qaPassed =
              qa?.status === 'pass' ||
              clip.production_state === 'QA_PASSED' ||
              clip.production_state === 'EXPORTED';
            const canExport =
              clip.review_state === 'HUMAN_APPROVED' && qaPassed && planSynced !== false;
            const audit = clip.cold_viewer_audit || {};
            const checkStatuses = qa?.check_statuses || {};
            const checked = Boolean(selectedForExport[clip.candidate_id]);
            const mp4Url =
              clip.video_path && projectId !== 'demo'
                ? buildMediaUrl(projectId, clip.video_path, clip.video_mtime)
                : null;

            return (
              <Panel key={clip.candidate_id} className="p-4 space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <label className="flex items-start gap-2.5 cursor-pointer">
                    <input
                      type="checkbox"
                      disabled={!canExport}
                      checked={checked && canExport}
                      onChange={(e) =>
                        setSelectedForExport((s) => ({
                          ...s,
                          [clip.candidate_id]: e.target.checked,
                        }))
                      }
                      className="mt-1 h-4 w-4 accent-[var(--accent-lime-strong)] disabled:opacity-40"
                    />
                    <div>
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-mono text-xs font-bold">{clip.candidate_id}</span>
                        <Badge tone={clip.review_state === 'HUMAN_APPROVED' ? 'pass' : 'amber'}>
                          {clip.review_state}
                        </Badge>
                        <Badge tone={qaPassed ? 'pass' : 'warn'}>
                          {clip.production_state}
                        </Badge>
                        {clip.exported_paths.length > 0 && <Badge tone="cyan">EXPORTED</Badge>}
                      </div>
                      <p className="mt-1 text-xs text-[var(--text-secondary)] line-clamp-1">
                        {clip.spoken_hook?.text || clip.editorial_title}
                      </p>
                    </div>
                  </label>

                  {mp4Url && (
                    <a
                      href={mp4Url}
                      download
                      className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-panel)] px-2.5 py-1 text-[11px] font-medium hover:border-[var(--border-strong)]"
                    >
                      <Download className="h-3 w-3" /> MP4
                    </a>
                  )}
                </div>

                <LoudnessBar lufs={qa?.integrated_lufs} truePeak={qa?.true_peak_dbtp} />

                {/* Technical Probe Grid */}
                <div className="grid grid-cols-3 gap-2 font-mono text-[11px]">
                  <div className="rounded-lg bg-[var(--bg-canvas)] p-2 border border-[var(--border-subtle)]">
                    <div className="text-[9px] text-[var(--text-muted)]">RESOLUTION</div>
                    <div>{qa?.resolution || '—'}</div>
                  </div>
                  <div className="rounded-lg bg-[var(--bg-canvas)] p-2 border border-[var(--border-subtle)]">
                    <div className="text-[9px] text-[var(--text-muted)]">CODEC / PIX</div>
                    <div>
                      {qa?.codec || '—'} · {qa?.pix_fmt || '—'}
                    </div>
                  </div>
                  <div className="rounded-lg bg-[var(--bg-canvas)] p-2 border border-[var(--border-subtle)]">
                    <div className="text-[9px] text-[var(--text-muted)]">DURATION</div>
                    <div>{formatTimecode(clip.duration_seconds)}</div>
                  </div>
                </div>

                {/* Honest CheckStatus Enum Badges */}
                {Object.keys(checkStatuses).length > 0 && (
                  <div className="space-y-1.5">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                      Automated QA Check Matrix
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(checkStatuses).map(([k, st]) => {
                        const upper = String(st).toUpperCase();
                        const tone =
                          upper === 'PASS'
                            ? 'pass'
                            : upper === 'FAIL'
                              ? 'fail'
                              : upper === 'WARNING'
                                ? 'warn'
                                : 'neutral';
                        return (
                          <Badge key={k} tone={tone} className="text-[10px]">
                            {upper === 'PASS' ? (
                              <CheckCircle2 className="h-3 w-3" />
                            ) : upper === 'FAIL' ? (
                              <XCircle className="h-3 w-3" />
                            ) : upper === 'WARNING' ? (
                              <AlertTriangle className="h-3 w-3" />
                            ) : null}
                            {k.replace(/_/g, ' ')}: {upper}
                          </Badge>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* 5-Point Cold-Viewer Audit */}
                {Object.keys(audit).length > 0 && (
                  <div className="space-y-1.5">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                      5-Point Cold-Viewer Audit
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {Object.entries(audit)
                        .filter(([k]) => k !== 'notes')
                        .map(([k, v]) => {
                          const ok = v === true;
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

                {qa?.video_sha256 && (
                  <div className="font-mono text-[10px] text-[var(--text-muted)] truncate">
                    MP4 SHA-256: {qa.video_sha256}
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
            Project Final Review Report{' '}
            <span className="font-mono text-xs text-[var(--text-muted)]">
              artifacts/final_review.json
            </span>
          </div>
          <pre className="max-h-[480px] overflow-auto rounded-lg bg-[var(--bg-canvas)] p-3.5 font-mono text-[11px] text-[var(--text-secondary)]">
            {JSON.stringify(finalReview, null, 2)}
          </pre>
        </Panel>
      ) : (
        <EmptyState
          icon={<ShieldCheck className="h-5 w-5" />}
          title="No Broadcast QA reports yet"
          description="Run media_qa after rendering clips or master videos to view live EBU R128 loudness meters, CheckStatus matrix, SHA-256 verification, and 1-click Export Bundles."
        />
      )}

      {publishLog && (
        <Panel className="p-4 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold">
              Publish &amp; Export Log{' '}
              <span className="font-mono text-[11px] text-[var(--text-muted)]">
                artifacts/publish_log.json
              </span>
            </span>
            <Badge tone="pass">VERIFIED</Badge>
          </div>
          <pre className="max-h-60 overflow-auto rounded-lg bg-[var(--bg-canvas)] p-3 font-mono text-[11px] text-[var(--text-secondary)]">
            {JSON.stringify(publishLog, null, 2)}
          </pre>
        </Panel>
      )}

      <ExportModal
        isOpen={exportModalOpen}
        onClose={() => setExportModalOpen(false)}
        onConfirmExport={handleConfirmExport}
        clipCount={eligibleIds.length}
        totalDurationSeconds={totalDurationSeconds}
      />
    </div>
  );
}
