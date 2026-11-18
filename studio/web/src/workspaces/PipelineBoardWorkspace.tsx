import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FileCode2,
  FileText,
  FolderTree,
  GitCommitHorizontal,
  History,
  Layers,
  Loader2,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { studioApi } from '@/lib/api';
import { cn, formatBytes, formatRelativeTime, formatUsd } from '@/lib/format';
import { toast, useProjectStore, useSupervisorStore } from '@/stores/useStudioStore';
import { Badge, Button, EmptyState, Panel } from '@/components/ui/Primitives';
import type { ProjectFileItem, StageRailItem } from '@/types/studio';

export function PipelineBoardWorkspace() {
  const { projectId } = useParams();
  const { boardState, boardLoading } = useProjectStore();
  const { ensureSessionForProject, setRunning } = useSupervisorStore();

  const [tab, setTab] = useState<'storyboard' | 'decisions' | 'artifacts' | 'files'>('storyboard');
  const [selectedStage, setSelectedStage] = useState<StageRailItem | null>(null);
  const [historyData, setHistoryData] = useState<Record<string, Array<Record<string, unknown>>>>({});
  const [files, setFiles] = useState<ProjectFileItem[]>([]);
  const [selectedArtifact, setSelectedArtifact] = useState<string | null>(null);
  const [artifactPayload, setArtifactPayload] = useState<unknown>(null);
  const [gateNotes, setGateNotes] = useState('');
  const [gateSubmitting, setGateSubmitting] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    studioApi.getHistory(projectId).then((r) => setHistoryData(r.stages || {})).catch(() => {});
    studioApi.getProjectFiles(projectId).then((r) => setFiles(r.files || [])).catch(() => {});
  }, [projectId, boardState?.stages?.length]);

  const awaitingStage = useMemo(
    () => boardState?.stages?.find((s) => s.status === 'awaiting_human') ?? null,
    [boardState],
  );

  const artifactNames = useMemo(
    () => Object.keys(boardState?.artifacts || {}).sort(),
    [boardState],
  );

  useEffect(() => {
    if (!selectedArtifact && artifactNames.length > 0) {
      setSelectedArtifact(artifactNames[0]);
      setArtifactPayload(boardState?.artifacts?.[artifactNames[0]] ?? null);
    }
  }, [artifactNames, boardState, selectedArtifact]);

  const handleSelectArtifact = async (name: string) => {
    setSelectedArtifact(name);
    if (boardState?.artifacts?.[name]) {
      setArtifactPayload(boardState.artifacts[name]);
    }
    if (projectId) {
      try {
        const res = await studioApi.getArtifact(projectId, name);
        setArtifactPayload(res.data);
      } catch {
        // fallback already displayed
      }
    }
  };

  const handleGateDecision = async (decision: 'approve' | 'revise' | 'reject') => {
    if (!projectId || !awaitingStage) return;
    setGateSubmitting(true);
    try {
      const sid = await ensureSessionForProject(projectId);
      await studioApi.sendGateDecision(sid, {
        stage: awaitingStage.name,
        decision,
        notes: gateNotes,
        project_id: projectId,
      });
      setRunning(true);
      setGateNotes('');
      toast.success(
        `Gate "${awaitingStage.name}" → ${decision.toUpperCase()}`,
        'Top Supervisor is executing the next step.',
      );
    } catch (e) {
      toast.error('Gate action failed', String(e));
    } finally {
      setGateSubmitting(false);
    }
  };

  if (boardLoading && !boardState) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-[var(--text-muted)]">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading pipeline production board…
      </div>
    );
  }

  if (!boardState) {
    return (
      <div className="p-6">
        <EmptyState
          icon={<Layers className="h-5 w-5" />}
          title="Project state unavailable"
          description="Select an existing project from the Command Hub or launch a new production."
        />
      </div>
    );
  }

  const pipelineType =
    boardState.pipeline?.pipeline_type || boardState.pipeline_type || 'unknown';
  const scenes = Array.isArray(boardState.storyboard?.scenes)
    ? boardState.storyboard.scenes
    : Array.isArray(boardState.scenes)
      ? boardState.scenes
      : [];
  const decisionLogArt = boardState.artifacts?.decision_log as
    | { decisions?: Array<Record<string, unknown>> }
    | undefined;
  const decisions = Array.isArray(boardState.decisions)
    ? boardState.decisions
    : Array.isArray(decisionLogArt?.decisions)
      ? decisionLogArt.decisions
      : [];
  const costTotal = boardState.cost?.total_usd ?? 0;
  const costBudget = boardState.cost?.budget_usd ?? 0;

  return (
    <div className="mx-auto max-w-[1360px] space-y-5 p-5">
      {/* Project Header + Cost Meter */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-base font-bold tracking-tight">
              {boardState.title || boardState.project_id}
            </h1>
            <Badge tone="cyan">{pipelineType}</Badge>
            {boardState.live && <Badge tone="pass">LIVE</Badge>}
            {boardState.stalled && <Badge tone="fail">STALLED</Badge>}
          </div>
          <div className="mt-0.5 font-mono text-[11px] text-[var(--text-muted)]">
            projects/{boardState.project_id}/ · {boardState.stages.length} stages ·{' '}
            {artifactNames.length} artifacts
          </div>
        </div>

        <Panel className="flex items-center gap-4 px-4 py-2 text-xs">
          <div>
            <div className="text-[10px] uppercase text-[var(--text-muted)]">Spend</div>
            <div className="font-mono font-bold text-[var(--text-primary)]">{formatUsd(costTotal)}</div>
          </div>
          {costBudget > 0 && (
            <div>
              <div className="text-[10px] uppercase text-[var(--text-muted)]">Budget Cap</div>
              <div className="font-mono text-[var(--text-secondary)]">{formatUsd(costBudget)}</div>
            </div>
          )}
        </Panel>
      </div>

      {/* Universal Human Gate Review Bar */}
      {awaitingStage && (
        <Panel className="border-[var(--accent-amber)]/50 bg-[var(--accent-amber-soft)]/70 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-[var(--accent-amber)]" />
                <span className="text-sm font-bold text-[var(--text-primary)]">
                  Human Approval Gate — Stage “{awaitingStage.name}”
                </span>
              </div>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                Review the artifacts produced by this stage ({awaitingStage.produces.join(', ') || 'checkpoint'}) before approving spend or downstream rendering.
              </p>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              value={gateNotes}
              onChange={(e) => setGateNotes(e.target.value)}
              placeholder="Optional director notes or revision feedback…"
              className="min-w-[240px] flex-1 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs"
            />
            <Button
              variant="primary"
              disabled={gateSubmitting}
              onClick={() => handleGateDecision('approve')}
            >
              <CheckCircle2 className="h-3.5 w-3.5" /> Approve &amp; Continue
            </Button>
            <Button
              variant="secondary"
              disabled={gateSubmitting}
              onClick={() => handleGateDecision('revise')}
            >
              Request Revisions
            </Button>
            <Button
              variant="danger"
              disabled={gateSubmitting}
              onClick={() => handleGateDecision('reject')}
            >
              <XCircle className="h-3.5 w-3.5" /> Reject
            </Button>
          </div>
        </Panel>
      )}

      {/* Interactive Pipeline Stage Rail */}
      <Panel className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <span className="text-xs font-semibold text-[var(--text-secondary)]">
            Interactive Pipeline Stage Rail (click any stage to inspect checkpoint history)
          </span>
          {selectedStage && (
            <Button size="xs" variant="ghost" onClick={() => setSelectedStage(null)}>
              Close Drawer
            </Button>
          )}
        </div>
        <div className="flex gap-2 overflow-x-auto pb-1">
          {boardState.stages.map((st, idx) => {
            const active = selectedStage?.name === st.name;
            const tone =
              st.status === 'completed'
                ? 'border-[var(--status-pass)]/50 bg-[var(--status-pass-soft)]/50'
                : st.status === 'awaiting_human'
                  ? 'border-[var(--accent-amber)] bg-[var(--accent-amber-soft)]'
                  : st.status === 'in_progress'
                    ? 'border-[var(--accent-cyan)] bg-[var(--accent-cyan-soft)]'
                    : st.status === 'failed'
                      ? 'border-[var(--status-fail)] bg-[var(--status-fail-soft)]'
                      : 'border-[var(--border-subtle)] bg-[var(--bg-canvas)]/50';
            return (
              <button
                key={`${st.name}-${idx}`}
                type="button"
                onClick={() => setSelectedStage(active ? null : st)}
                className={cn(
                  'min-w-[136px] shrink-0 rounded-xl border p-3 text-left transition-all cursor-pointer',
                  tone,
                  active && 'ring-2 ring-[var(--accent-cyan)]',
                )}
              >
                <div className="flex items-center justify-between gap-1">
                  <span className="font-mono text-[10px] text-[var(--text-muted)]">
                    {String(idx + 1).padStart(2, '0')}
                  </span>
                  {st.gated && (
                    <Badge tone="amber" className="px-1.5 py-0 text-[9px]">
                      GATE
                    </Badge>
                  )}
                </div>
                <div className="mt-1 text-xs font-bold text-[var(--text-primary)] truncate">
                  {st.name}
                </div>
                <div className="mt-1 flex items-center justify-between text-[10px] text-[var(--text-muted)]">
                  <span>{st.status}</span>
                  {st.versions > 0 && <span className="font-mono">v{st.versions}</span>}
                </div>
                {st.gate_skipped && (
                  <div className="mt-1 flex items-center gap-1 text-[10px] text-[var(--status-warn)]">
                    <AlertTriangle className="h-3 w-3" /> gate skipped
                  </div>
                )}
              </button>
            );
          })}
        </div>

        {/* Versioned Checkpoint History Drawer */}
        {selectedStage && (
          <div className="mt-4 rounded-xl border border-[var(--border-strong)] bg-[var(--bg-canvas)] p-3.5 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-xs font-semibold">
                <History className="h-4 w-4 text-[var(--accent-cyan)]" />
                Stage “{selectedStage.name}” Checkpoint &amp; Version History
              </div>
              <span className="font-mono text-[10px] text-[var(--text-muted)]">
                {selectedStage.timestamp ? formatRelativeTime(selectedStage.timestamp) : 'No checkpoint yet'}
              </span>
            </div>
            {selectedStage.error && (
              <div className="rounded-lg border border-[var(--status-fail)]/40 bg-[var(--status-fail-soft)] p-2 text-xs text-[var(--status-fail)]">
                {selectedStage.error}
              </div>
            )}
            <div className="grid gap-3 md:grid-cols-2 text-xs">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1">
                  Produces Artifacts
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {selectedStage.produces.length > 0 ? (
                    selectedStage.produces.map((a) => (
                      <Badge key={a} tone="neutral" className="font-mono">
                        {a}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-[var(--text-muted)]">—</span>
                  )}
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1">
                  Archived History Versions ({(historyData[selectedStage.name] || []).length})
                </div>
                <div className="space-y-1 max-h-28 overflow-y-auto font-mono text-[10px]">
                  {(historyData[selectedStage.name] || []).length === 0 ? (
                    <span className="text-[var(--text-muted)]">No prior archived checkpoints.</span>
                  ) : (
                    (historyData[selectedStage.name] || []).map((v, i) => (
                      <div key={i} className="flex justify-between rounded bg-[var(--bg-surface)] px-2 py-1">
                        <span>
                          v{i + 1} · {String(v.status || 'unknown')}
                        </span>
                        <span className="text-[var(--text-muted)]">
                          {formatRelativeTime(String(v.timestamp || ''))}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </Panel>

      {/* Workspace Sub-Tabs */}
      <div className="flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-0.5 w-fit">
        {(
          [
            ['storyboard', `Storyboard (${scenes.length})`, Layers],
            ['decisions', `Decisions Log (${decisions.length})`, GitCommitHorizontal],
            ['artifacts', `Artifacts (${artifactNames.length})`, FileCode2],
            ['files', `Project Files (${files.length})`, FolderTree],
          ] as const
        ).map(([id, label, Icon]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all cursor-pointer',
              tab === id
                ? 'bg-[var(--bg-elevated)] text-[var(--text-primary)]'
                : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>

      {/* Tab: Storyboard Scenes */}
      {tab === 'storyboard' &&
        (scenes.length === 0 ? (
          <EmptyState
            icon={<Layers className="h-5 w-5" />}
            title="No storyboard scenes yet"
            description="Once the pipeline completes scene_plan or assets, every scene card with generated visuals, takes, and narration audio appears here."
          />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {scenes.map((sc, idx) => {
              const mediaUrl = String(sc.image_url || sc.thumb_url || sc.video_url || '');
              const audioUrl = String(sc.audio_url || '');
              return (
                <Panel key={idx} className="overflow-hidden flex flex-col">
                  <div className="relative h-40 bg-[var(--bg-canvas)] border-b border-[var(--border-subtle)]">
                    {mediaUrl ? (
                      <img src={mediaUrl} alt={`Scene ${idx + 1}`} className="h-full w-full object-cover" />
                    ) : (
                      <div className="flex h-full items-center justify-center font-mono text-xs text-[var(--text-muted)]">
                        Scene {idx + 1} · Awaiting Visual
                      </div>
                    )}
                    <div className="absolute left-2 top-2">
                      <Badge tone="neutral" className="bg-black/70 text-zinc-100 border-white/15">
                        SCENE {String(sc.scene_id || idx + 1)}
                      </Badge>
                    </div>
                  </div>
                  <div className="p-3.5 flex-1 flex flex-col space-y-2 text-xs">
                    <div className="font-semibold text-[var(--text-primary)]">
                      {String(sc.title || sc.heading || `Scene ${idx + 1}`)}
                    </div>
                    <p className="text-[11px] text-[var(--text-secondary)] line-clamp-3 leading-relaxed">
                      {String(sc.narration || sc.script || sc.visual_description || '—')}
                    </p>
                    {audioUrl && (
                      <audio controls preload="none" src={audioUrl} className="mt-auto h-8 w-full" />
                    )}
                  </div>
                </Panel>
              );
            })}
          </div>
        ))}

      {/* Tab: Decisions Audit Rail */}
      {tab === 'decisions' &&
        (decisions.length === 0 ? (
          <EmptyState
            icon={<GitCommitHorizontal className="h-5 w-5" />}
            title="No logged production decisions yet"
            description="Every provider, voice, model, playbook, and runtime choice logged by the Top Supervisor to decision_log.json is audited here."
          />
        ) : (
          <div className="space-y-2.5">
            {decisions.map((d, idx) => (
              <Panel key={idx} className="p-3.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge tone="cyan">{String(d.category || 'decision')}</Badge>
                    <span className="text-xs font-semibold text-[var(--text-primary)]">
                      {String(d.subject || d.title || `Decision #${idx + 1}`)}
                    </span>
                  </div>
                  <span className="inline-flex items-center gap-1 font-mono text-[10px] text-[var(--text-muted)]">
                    <Clock className="h-3 w-3" />
                    {formatRelativeTime(String(d.timestamp || ''))}
                  </span>
                </div>
                <div className="mt-2 text-xs text-[var(--accent-amber)] font-medium">
                  Chosen: {String(d.chosen || d.choice || '—')}
                </div>
                {Boolean(d.reason || d.rationale) && (
                  <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
                    {String(d.reason || d.rationale)}
                  </p>
                )}
              </Panel>
            ))}
          </div>
        ))}

      {/* Tab: Structured JSON Artifacts Explorer */}
      {tab === 'artifacts' && (
        <div className="grid gap-4 lg:grid-cols-12">
          <Panel className="lg:col-span-4 p-2.5 space-y-1 max-h-[520px] overflow-y-auto">
            {artifactNames.length === 0 ? (
              <div className="p-6 text-center text-xs text-[var(--text-muted)]">No artifacts written yet.</div>
            ) : (
              artifactNames.map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => handleSelectArtifact(name)}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left font-mono text-xs transition-colors cursor-pointer',
                    selectedArtifact === name
                      ? 'bg-[var(--accent-amber-soft)] text-[var(--accent-amber)] font-semibold'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]',
                  )}
                >
                  <FileText className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{name}.json</span>
                </button>
              ))
            )}
          </Panel>

          <Panel className="lg:col-span-8 p-4 overflow-hidden">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-mono text-xs font-semibold text-[var(--text-primary)]">
                {selectedArtifact ? `artifacts/${selectedArtifact}.json` : 'Select an artifact'}
              </span>
            </div>
            <pre className="max-h-[460px] overflow-auto rounded-lg bg-[var(--bg-canvas)] p-3.5 font-mono text-[11px] text-[var(--text-secondary)]">
              {artifactPayload ? JSON.stringify(artifactPayload, null, 2) : '{}'}
            </pre>
          </Panel>
        </div>
      )}

      {/* Tab: Project Files */}
      {tab === 'files' && (
        <Panel className="overflow-hidden">
          <div className="max-h-[520px] overflow-auto">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 border-b border-[var(--border-subtle)] bg-[var(--bg-panel)] text-[10px] uppercase tracking-wider text-[var(--text-muted)]">
                <tr>
                  <th className="px-3.5 py-2.5">Relative Path</th>
                  <th className="px-3.5 py-2.5">Type</th>
                  <th className="px-3.5 py-2.5">Size</th>
                  <th className="px-3.5 py-2.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]/60">
                {files.map((f) => (
                  <tr key={f.rel_path} className="hover:bg-[var(--bg-elevated)]/40">
                    <td className="px-3.5 py-2 font-mono text-[11px] text-[var(--text-primary)]">
                      {f.rel_path}
                    </td>
                    <td className="px-3.5 py-2">
                      <Badge tone="neutral">{f.extension || 'file'}</Badge>
                    </td>
                    <td className="px-3.5 py-2 font-mono text-[11px] text-[var(--text-muted)]">
                      {formatBytes(f.size_bytes)}
                    </td>
                    <td className="px-3.5 py-2 text-right">
                      <a
                        href={f.media_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-[11px] text-[var(--accent-cyan)] hover:underline"
                      >
                        Open
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  );
}
