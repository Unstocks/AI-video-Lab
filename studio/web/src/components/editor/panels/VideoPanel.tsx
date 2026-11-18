import { useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  CheckCircle2,
  Film,
  Link2,
  Loader2,
  Scissors,
  Upload,
  X,
} from 'lucide-react';
import { studioApi } from '@/lib/api';
import { cn, formatTimecode } from '@/lib/format';
import {
  toast,
  useProjectStore,
  useSupervisorStore,
  useSystemStore,
} from '@/stores/useStudioStore';
import { useEditorStore } from '@/stores/useEditorStore';
import { useBrandKitStore } from '@/stores/useBrandKitStore';
import { Badge, Button } from '@/components/ui/Primitives';

export function VideoPanel() {
  const { projectId = 'demo' } = useParams();
  const { setDockOpen } = useSystemStore();
  const { boardState, activeClipId, setActiveClipId } = useProjectStore();
  const { ensureSessionForProject, setRunning, loadSessions, selectSession } = useSupervisorStore();
  const { activeSubtitlePreset, aiTools } = useEditorStore();
  const { saveItem } = useBrandKitStore();

  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [urlModalOpen, setUrlModalOpen] = useState(false);
  const [urlInput, setUrlInput] = useState('');
  const [selectedBatch, setSelectedBatch] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);

  const clips = boardState?.clip_studio?.clips ?? [];
  const renders = boardState?.media?.renders ?? [];
  const selectedIds = clips
    .filter((c) => selectedBatch[c.candidate_id])
    .map((c) => c.candidate_id);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const res = await studioApi.uploadMediaFile(file);
      await saveItem('video', res.filename, { path: res.path, size_bytes: res.size_bytes });
      toast.success('Video uploaded', `${res.filename} added to Workspace`);
    } catch (e) {
      toast.error('Upload failed', String(e));
    } finally {
      setUploading(false);
    }
  };

  const handleUrlIntake = async () => {
    const cleaned = urlInput.trim();
    if (!cleaned) return;
    setBusy(true);
    try {
      const s = await studioApi.startJob({
        source_input: cleaned,
        project_id: projectId !== 'demo' ? projectId : undefined,
        style_preset: activeSubtitlePreset,
        layout_mode: aiTools.layoutMode,
        enable_punch_in: aiTools.enablePunchIn,
      });
      await loadSessions();
      await selectSession(s.session_id);
      setRunning(true);
      setDockOpen(true);
      setUrlModalOpen(false);
      setUrlInput('');
      toast.success('URL intake launched', 'Executive Producer is ingesting source video.');
    } catch (e) {
      toast.error('URL intake failed', String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleApproveBatch = async () => {
    if (projectId === 'demo' || selectedIds.length === 0) return;
    setBusy(true);
    try {
      const sid = await ensureSessionForProject(projectId);
      await studioApi.approveClips(sid, {
        approved_ids: selectedIds,
        rejected_ids: clips
          .filter((c) => !selectedBatch[c.candidate_id])
          .map((c) => c.candidate_id),
        style_preset: activeSubtitlePreset,
        layout_mode: aiTools.layoutMode,
        enable_punch_in: aiTools.enablePunchIn,
        project_id: projectId,
      });
      setRunning(true);
      setDockOpen(true);
      toast.success('Approval sent', `Rendering ${selectedIds.length} approved clip(s) on GPU.`);
    } catch (e) {
      toast.error('Approval failed', String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <input
        ref={fileRef}
        type="file"
        accept="video/*"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void handleUpload(f);
          e.target.value = '';
        }}
      />

      {/* Header + Upload / URL Buttons */}
      <div className="space-y-3 border-b border-[var(--border-subtle)] px-4 py-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-[var(--text-primary)]">Video</h2>
          <Badge tone="neutral" className="font-mono text-[10px]">
            {clips.length} clips
          </Badge>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <Button
            variant="primary"
            size="xs"
            className="rounded-[10px]"
            disabled={uploading}
            onClick={() => fileRef.current?.click()}
          >
            {uploading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Upload className="h-3.5 w-3.5" />
            )}
            Upload Video
          </Button>
          <Button
            variant="secondary"
            size="xs"
            className="rounded-[10px]"
            onClick={() => setUrlModalOpen(true)}
          >
            <Link2 className="h-3.5 w-3.5" />
            YouTube URL
          </Button>
        </div>
      </div>

      {/* Inline URL Intake Popover */}
      {urlModalOpen && (
        <div className="mx-4 mt-3 rounded-[10px] border border-[var(--accent-lime-border)] bg-[var(--bg-panel)] p-3 space-y-2">
          <div className="flex items-center justify-between text-xs font-bold">
            <span>Ingest Public Video URL</span>
            <button
              type="button"
              aria-label="Close URL dialog"
              onClick={() => setUrlModalOpen(false)}
              className="text-[var(--text-muted)] hover:text-[var(--text-primary)] cursor-pointer"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <input
            autoFocus
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setUrlModalOpen(false);
              if (e.key === 'Enter') void handleUrlIntake();
            }}
            placeholder="https://www.youtube.com/watch?v=…"
            className="h-8 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 text-xs"
          />
          <Button
            variant="primary"
            size="xs"
            className="w-full"
            disabled={busy || !urlInput.trim()}
            onClick={() => void handleUrlIntake()}
          >
            Ingest &amp; Extract Clips
          </Button>
        </div>
      )}

      {/* Clip Factory Candidates & Project Videos */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {clips.length > 0 ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
              <span className="inline-flex items-center gap-1">
                <Scissors className="h-3 w-3" /> Clip Candidates
              </span>
              {boardState?.clip_studio?.plan_sha256_synced === true && (
                <Badge tone="pass" className="text-[9px]">
                  SHA-256 Synced
                </Badge>
              )}
            </div>

            {clips.map((c) => {
              const selected = activeClipId === c.candidate_id;
              const checked = Boolean(selectedBatch[c.candidate_id]);
              const coldPass = c.cold_viewer_audit?.passed;
              return (
                <div
                  key={c.candidate_id}
                  onClick={() => setActiveClipId(c.candidate_id)}
                  className={cn(
                    'rounded-[10px] border p-3 transition-all cursor-pointer space-y-1.5',
                    selected
                      ? 'border-[var(--accent-lime-border)] bg-[var(--accent-lime-soft)]/65'
                      : 'border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--border-strong)]',
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <label
                      className="flex items-center gap-1.5 cursor-pointer"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) =>
                          setSelectedBatch((s) => ({ ...s, [c.candidate_id]: e.target.checked }))
                        }
                        className="h-3.5 w-3.5 accent-[var(--accent-lime-strong)]"
                      />
                      <span className="font-mono text-xs font-bold text-[var(--text-primary)]">
                        {c.candidate_id}
                      </span>
                    </label>
                    <span className="font-mono text-[10px] text-[var(--text-muted)]">
                      {formatTimecode(c.start_seconds, false)}–{formatTimecode(c.end_seconds, false)}
                    </span>
                  </div>

                  <p className="line-clamp-2 text-xs text-[var(--text-secondary)] leading-snug">
                    {c.spoken_hook?.text || c.editorial_title}
                  </p>

                  {/* Strictly orthogonal Core Brain states */}
                  <div className="flex flex-wrap items-center gap-1 pt-0.5">
                    <Badge
                      tone={c.review_state === 'HUMAN_APPROVED' ? 'pass' : 'amber'}
                      className="text-[9px]"
                    >
                      {c.review_state}
                    </Badge>
                    <Badge
                      tone={
                        c.production_state === 'QA_PASSED' || c.production_state === 'EXPORTED'
                          ? 'pass'
                          : c.production_state === 'QA_FAILED'
                            ? 'fail'
                            : 'neutral'
                      }
                      className="text-[9px]"
                    >
                      {c.production_state}
                    </Badge>
                    {coldPass != null && (
                      <Badge tone={coldPass ? 'lime' : 'fail'} className="text-[9px]">
                        {coldPass ? '5/5 Cold' : 'Cold Fail'}
                      </Badge>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="rounded-[10px] border border-dashed border-[var(--border-strong)] p-5 text-center space-y-1.5">
            <Film className="mx-auto h-5 w-5 text-[var(--text-muted)]" />
            <div className="text-xs font-bold text-[var(--text-primary)]">
              {projectId === 'demo' ? 'Interactive Demo Media Loaded' : 'Source Video Ready'}
            </div>
            <p className="text-[11px] text-[var(--text-muted)]">
              Upload local footage, paste a YouTube URL, or run Viral Clip Discovery in AI Tools.
            </p>
          </div>
        )}

        {/* Project Renders List (using exact backlot/state.py media.renders[].path) */}
        {renders.length > 0 && (
          <div className="space-y-1.5 pt-2">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
              Project Renders ({renders.length})
            </div>
            {renders.map((r) => (
              <div
                key={r.path}
                className="flex items-center justify-between rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-panel)] px-2.5 py-2 text-xs"
              >
                <span className="truncate font-mono text-[11px]">{r.path}</span>
                <Badge tone="neutral" className="text-[9px]">
                  MP4
                </Badge>
              </div>
            ))}
          </div>
        )}
      </div>

      {clips.length > 0 && (
        <div className="border-t border-[var(--border-subtle)] p-3.5">
          <Button
            variant="primary"
            size="xs"
            className="w-full rounded-full"
            disabled={busy || selectedIds.length === 0}
            onClick={() => void handleApproveBatch()}
          >
            <CheckCircle2 className="h-3.5 w-3.5" />
            Approve &amp; Render Selected ({selectedIds.length})
          </Button>
        </div>
      )}
    </div>
  );
}
