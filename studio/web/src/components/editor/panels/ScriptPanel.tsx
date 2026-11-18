import { useDeferredValue, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  AlertTriangle,
  MoreHorizontal,
  Play,
  RotateCcw,
  Scissors,
  Share2,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { studioApi } from '@/lib/api';
import { DEMO_TRANSCRIPT_WORDS } from '@/data/demoProjectSeed';
import { cn, formatTimecode } from '@/lib/format';
import {
  playbackHub,
  toast,
  useProjectStore,
  useSupervisorStore,
  useSystemStore,
} from '@/stores/useStudioStore';
import { useEditorStore } from '@/stores/useEditorStore';
import { Badge, Button } from '@/components/ui/Primitives';
import type { TranscriptWord } from '@/types/studio';

export function ScriptPanel({ duration }: { duration: number }) {
  const { projectId = 'demo' } = useParams();
  const { setDockOpen } = useSystemStore();
  const { transcript, boardState, activeClipId } = useProjectStore();
  const { ensureSessionForProject, setRunning } = useSupervisorStore();
  const {
    setActiveTool,
    cutRanges,
    addCutRange,
    removeCutRange,
    scriptTipDismissed,
    dismissScriptTip,
    undo,
    past,
    activeSubtitlePreset,
    aiTools,
  } = useEditorStore();

  const [selStartIdx, setSelStartIdx] = useState<number | null>(null);
  const [selEndIdx, setSelEndIdx] = useState<number | null>(null);
  const [committing, setCommitting] = useState(false);

  const rawWords: TranscriptWord[] = useMemo(() => {
    if (projectId === 'demo') return DEMO_TRANSCRIPT_WORDS;
    if (transcript?.words && transcript.words.length > 0) return transcript.words;
    return DEMO_TRANSCRIPT_WORDS;
  }, [projectId, transcript]);

  const words = useDeferredValue(rawWords);

  const activeClip = useMemo(() => {
    const clips = boardState?.clip_studio?.clips ?? [];
    return clips.find((c) => c.candidate_id === activeClipId) ?? clips[0] ?? null;
  }, [activeClipId, boardState]);

  const hookText = activeClip?.spoken_hook?.text?.toLowerCase().trim() || '';

  const selLo =
    selStartIdx != null && selEndIdx != null ? Math.min(selStartIdx, selEndIdx) : selStartIdx;
  const selHi =
    selStartIdx != null && selEndIdx != null ? Math.max(selStartIdx, selEndIdx) : selStartIdx;

  const cutDuration = useMemo(
    () => cutRanges.reduce((acc, r) => acc + Math.max(0, r.end - r.start), 0),
    [cutRanges],
  );
  const effectiveDuration = Math.max(0.5, (duration || 24) - cutDuration);

  const isWordCut = (w: TranscriptWord) =>
    cutRanges.some((r) => w.start >= r.start - 0.02 && w.end <= r.end + 0.02);

  const handleWordClick = (idx: number, shiftKey: boolean) => {
    const w = words[idx];
    if (!w) return;
    if (shiftKey && selStartIdx != null) {
      setSelEndIdx(idx);
    } else {
      setSelStartIdx(idx);
      setSelEndIdx(idx);
    }
    playbackHub.requestSeek(w.start);
  };

  const handleDeleteSelection = () => {
    if (selLo == null || selHi == null) return;
    const slice = words.slice(selLo, selHi + 1);
    if (slice.length === 0) return;
    const start = slice[0].start;
    const end = slice[slice.length - 1].end;
    const label = slice.map((w) => w.word).join(' ');
    const intersectsHook = Boolean(hookText && hookText.includes(label.toLowerCase()));

    addCutRange({ start, end, label, intersectsHook });
    setSelStartIdx(null);
    setSelEndIdx(null);
    if (intersectsHook) {
      toast.warn(
        'Cut intersects verbatim Spoken Hook',
        'Hook provenance will be re-validated by ClipSelector before final render.',
      );
    } else {
      toast.success('Cut marker created', `Removed ${(end - start).toFixed(2)}s from playback`);
    }
  };

  const handleCommitRecut = async () => {
    if (projectId === 'demo') {
      toast.info('Demo sandbox cut preview active', 'Open a real project to render cuts via Producer.');
      return;
    }
    const kept = words.filter((w) => !isWordCut(w));
    if (kept.length === 0) return;
    const newStart = kept[0].start;
    const newEnd = kept[kept.length - 1].end;
    const cid = activeClip?.candidate_id || 'clip_01';

    setCommitting(true);
    try {
      const sid = await ensureSessionForProject(projectId);
      await studioApi.recutClip(sid, {
        candidate_id: cid,
        start_seconds: newStart,
        end_seconds: newEnd,
        project_id: projectId,
        style_preset: activeSubtitlePreset,
        layout_mode: aiTools.layoutMode,
      });
      setRunning(true);
      setDockOpen(true);
      toast.success('Recut sent to Executive Producer', `${formatTimecode(newStart)} → ${formatTimecode(newEnd)}`);
    } catch (e) {
      toast.error('Recut dispatch failed', String(e));
    } finally {
      setCommitting(false);
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header: Edit script + AI Tools, Export/Share, Overflow */}
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-5 py-3">
        <div className="flex items-center gap-2.5">
          <h2 className="text-base font-bold text-[var(--text-primary)]">Edit script</h2>
          <Badge tone="neutral" className="font-mono text-[10px]">
            {transcript?.evidence_quality || 'medium_word'}
          </Badge>
        </div>

        <div className="flex items-center gap-1.5">
          <Button size="xs" variant="secondary" onClick={() => setActiveTool('ai-tools')}>
            <Sparkles className="h-3.5 w-3.5 text-[var(--accent-lime-strong)]" />
            AI Tools
          </Button>
          <button
            type="button"
            aria-label="Commit recut"
            title="Commit script cuts to Producer"
            onClick={() => void handleCommitRecut()}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)] cursor-pointer"
          >
            <Share2 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            aria-label="Undo last script edit"
            title="Undo (Ctrl+Z)"
            disabled={past.length === 0}
            onClick={undo}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-panel)] disabled:opacity-35 cursor-pointer"
          >
            <MoreHorizontal className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Dismissible Instructional Card: "Edit videos just like a doc" */}
      {!scriptTipDismissed && (
        <div className="mx-5 mt-4 flex items-center gap-3.5 rounded-[12px] border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-3">
          <div className="relative flex h-12 w-16 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-slate-800 to-slate-950 text-white">
            <Play className="h-4 w-4 fill-current" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-xs font-bold text-[var(--text-primary)]">
              Edit videos just like a doc
            </div>
            <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
              Remove spoken words to make cuts in the video. Shift+Click to select a phrase.
            </p>
          </div>
          <Button size="xs" variant="secondary" onClick={dismissScriptTip}>
            Got it
          </Button>
        </div>
      )}

      {/* Selection Action Bar */}
      {(selLo != null || cutRanges.length > 0) && (
        <div className="mx-5 mt-3 flex flex-wrap items-center justify-between gap-2 rounded-[10px] border border-[var(--accent-lime-border)]/60 bg-[var(--accent-lime-soft)]/70 px-3 py-2 text-xs">
          <div className="flex items-center gap-2 font-mono text-[11px]">
            {selLo != null && selHi != null ? (
              <span>
                Selected {selHi - selLo + 1} word(s) · {formatTimecode(words[selLo]?.start ?? 0)}–
                {formatTimecode(words[selHi]?.end ?? 0)}
              </span>
            ) : (
              <span>
                {cutRanges.length} cut(s) · Effective duration: {formatTimecode(effectiveDuration)}
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            {selLo != null && (
              <Button size="xs" variant="danger" onClick={handleDeleteSelection}>
                <Trash2 className="h-3 w-3" />
                Delete to Cut
              </Button>
            )}
            {cutRanges.length > 0 && (
              <Button
                size="xs"
                variant="primary"
                disabled={committing}
                onClick={() => void handleCommitRecut()}
              >
                <Scissors className="h-3 w-3" />
                Commit Recut
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Scrollable Doc-Style Transcript (15-16px text, 29px line-height, pause/cut markers) */}
      <div
        className="flex-1 overflow-y-auto px-5 py-4"
        onKeyDown={(e) => {
          if ((e.key === 'Delete' || e.key === 'Backspace') && selLo != null) {
            e.preventDefault();
            handleDeleteSelection();
          }
        }}
        tabIndex={0}
      >
        <div className="text-[15.5px] leading-[29px] text-[var(--text-primary)]">
          {words.map((w, idx) => {
            const prev = idx > 0 ? words[idx - 1] : null;
            const gap = prev ? w.start - prev.end : 0;
            const inSel = selLo != null && selHi != null && idx >= selLo && idx <= selHi;
            const cut = isWordCut(w);
            const inHook = Boolean(hookText && w.word.length > 3 && hookText.includes(w.word.toLowerCase()));
            return (
              <span key={`${w.start}-${idx}`}>
                {/* Light-gray rounded pause marker */}
                {gap > 0.35 && (
                  <span
                    title={`Pause ${gap.toFixed(1)}s`}
                    className="mx-1 inline-flex h-5 items-center rounded-full bg-[var(--bg-elevated)] px-2 align-middle font-mono text-[10px] text-[var(--text-muted)]"
                  >
                    ··· {gap.toFixed(1)}s
                  </span>
                )}
                <button
                  type="button"
                  onClick={(e) => handleWordClick(idx, e.shiftKey)}
                  title={`${formatTimecode(w.start)} – ${formatTimecode(w.end)}`}
                  className={cn(
                    'mr-1 inline rounded px-0.5 transition-colors cursor-pointer',
                    cut && 'line-through opacity-40 bg-red-500/15 text-[var(--status-fail)]',
                    !cut && inSel && 'bg-[var(--accent-lime)] text-zinc-950 font-semibold',
                    !cut && !inSel && 'hover:bg-[var(--bg-panel)]',
                    inHook && !cut && 'underline decoration-[var(--accent-amber)] decoration-2 underline-offset-4',
                  )}
                >
                  {w.word}
                </button>
              </span>
            );
          })}
        </div>

        {/* Active Cut Markers List */}
        {cutRanges.length > 0 && (
          <div className="mt-6 border-t border-[var(--border-subtle)] pt-3 space-y-2">
            <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
              Cut Markers ({cutRanges.length})
            </div>
            {cutRanges.map((c) => (
              <div
                key={c.id}
                className="flex items-center justify-between gap-2 rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-panel)] px-3 py-1.5 text-xs"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    {c.intersectsHook && (
                      <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-[var(--accent-amber)]" />
                    )}
                    <span className="truncate line-through text-[var(--text-secondary)]">
                      “{c.label}”
                    </span>
                  </div>
                  <div className="font-mono text-[10px] text-[var(--text-muted)]">
                    {formatTimecode(c.start)} – {formatTimecode(c.end)}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => removeCutRange(c.id)}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-surface)] hover:text-[var(--text-primary)] cursor-pointer"
                >
                  <RotateCcw className="h-3 w-3" /> Restore
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer Duration Summary */}
      <div className="flex items-center justify-between border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] px-5 py-2.5 text-xs">
        <span className="text-[var(--text-muted)]">
          Immutable master <code className="font-mono">source/transcript.json</code> protected
        </span>
        <span className="font-mono font-semibold text-[var(--text-primary)] tabular-nums">
          {formatTimecode(effectiveDuration, false)}
        </span>
      </div>
    </div>
  );
}
