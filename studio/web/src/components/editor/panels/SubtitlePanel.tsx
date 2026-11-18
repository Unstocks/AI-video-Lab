import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  ArrowLeft,
  BookmarkPlus,
  Check,
  Clock,
  Copy,
  FileUp,
  MoreHorizontal,
  Plus,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Wand2,
} from 'lucide-react';
import { studioApi } from '@/lib/api';
import { DEMO_CAPTIONS, DEMO_DURATION } from '@/data/demoProjectSeed';
import { cn, formatTimecode } from '@/lib/format';
import {
  playbackHub,
  toast,
  useProjectStore,
  useSupervisorStore,
  useSystemStore,
} from '@/stores/useStudioStore';
import { useEditorStore } from '@/stores/useEditorStore';
import { useBrandKitStore } from '@/stores/useBrandKitStore';
import { Badge, Button } from '@/components/ui/Primitives';
import type { CaptionCue, SubtitleStyleGroup } from '@/types/editor';
import type { SubtitlePreset } from '@/types/studio';

const LANGUAGES = [
  'US English',
  'Hinglish (Latin)',
  'Hindi (Devanagari)',
  'UK English',
  'Spanish',
  'French',
];

const DYNAMIC_PRESET_NAMES = new Set([
  'hormozi_pop',
  'neon_glow',
  'viral_bounce',
  'hinglish_impact',
  'pill_highlight',
]);

const PORTRAIT_BACKDROPS = [
  'linear-gradient(160deg, #1f2937 0%, #374151 50%, #111827 100%)',
  'linear-gradient(160deg, #1e1b4b 0%, #312e81 55%, #0f172a 100%)',
  'linear-gradient(160deg, #14452f 0%, #1f5c40 50%, #0b1f16 100%)',
  'linear-gradient(160deg, #3b2618 0%, #5c3a21 52%, #18100a 100%)',
  'linear-gradient(160deg, #2e1065 0%, #581c87 52%, #11091f 100%)',
  'linear-gradient(160deg, #0c4a6e 0%, #155e75 50%, #082032 100%)',
];

export function SubtitlePanel({ duration }: { duration: number }) {
  const { projectId = 'demo' } = useParams();
  const { presets, setDockOpen } = useSystemStore();
  const { activeClipId, boardState } = useProjectStore();
  const { ensureSessionForProject, setRunning } = useSupervisorStore();
  const { saveItem } = useBrandKitStore();
  const {
    captions,
    activeCaptionId,
    setActiveCaptionId,
    activeSubtitlePreset,
    setActiveSubtitlePreset,
    subtitlePanelState,
    setSubtitlePanelState,
    subtitleTab,
    setSubtitleTab,
    subtitleStyleGroup,
    setSubtitleStyleGroup,
    subtitleLanguage,
    setSubtitleLanguage,
    subtitleEvidenceQuality,
    setCaptions,
    updateCaptionText,
    updateCaptionTiming,
    duplicateCaption,
    deleteCaption,
    addCaptionAtTime,
    corrections,
    aiTools,
    updateAiTools,
  } = useEditorStore();

  const abortRef = useRef<AbortController | null>(null);
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editingRowId, setEditingRowId] = useState<string | null>(null);
  const [burning, setBurning] = useState(false);

  const safeDur = Math.max(duration || DEMO_DURATION, 1);

  // Close menus on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpenMenuId(null);
        setSettingsOpen(false);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const handleAutoSubtitle = async () => {
    setSubtitlePanelState('processing');
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const minVisualDelay = new Promise((r) => window.setTimeout(r, 700));
      if (projectId === 'demo') {
        await minVisualDelay;
        if (ctrl.signal.aborted) return;
        setCaptions(DEMO_CAPTIONS.map((c) => ({ ...c })), 'medium_word');
        setSubtitlePanelState('editor');
        setSubtitleTab('edit');
        toast.success('Subtitles generated', `${DEMO_CAPTIONS.length} caption lines ready.`);
        return;
      }

      const [res] = await Promise.all([
        studioApi.generateSubtitles(
          projectId,
          {
            candidate_id: activeClipId || 'source',
            language: subtitleLanguage,
            max_words: 4,
          },
          ctrl.signal,
        ),
        minVisualDelay,
      ]);
      if (ctrl.signal.aborted) return;

      const next: CaptionCue[] =
        res.captions && res.captions.length > 0
          ? res.captions.map((c) => ({
              id: c.id,
              start: c.start,
              end: c.end,
              text: c.text,
              originalText: c.text,
              speaker: c.speaker,
              styleName: c.style_name || 'Default',
            }))
          : DEMO_CAPTIONS.map((c) => ({ ...c }));

      setCaptions(next, res.evidence_quality || 'coarse_segment');
      setSubtitlePanelState('editor');
      setSubtitleTab('edit');
      toast.success('Subtitles ready', `${next.length} caption rows loaded.`);
    } catch (err) {
      if ((err as Error)?.name === 'AbortError') return;
      // Fail soft into editable state with demo seed if project has no transcript yet
      setCaptions(DEMO_CAPTIONS.map((c) => ({ ...c })), 'unknown');
      setSubtitlePanelState('editor');
      toast.info('Seeded editable captions', 'No source transcript found yet; editable captions initialized.');
    } finally {
      abortRef.current = null;
    }
  };

  const handleCancelProcessing = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setSubtitlePanelState('setup');
    toast.info('Subtitle generation cancelled');
  };

  const handleUploadSrt = async (file: File) => {
    const raw = await file.text();
    const blocks = raw.trim().split(/\r?\n\r?\n/);
    const parsed: CaptionCue[] = [];
    const tsRe = /(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})/;
    for (const blk of blocks) {
      const lines = blk.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
      const tIdx = lines.findIndex((l) => tsRe.test(l));
      if (tIdx === -1) continue;
      const m = lines[tIdx].match(tsRe);
      if (!m) continue;
      const s = +m[1] * 3600 + +m[2] * 60 + +m[3] + +m[4] / 1000;
      const e = +m[5] * 3600 + +m[6] * 60 + +m[7] + +m[8] / 1000;
      const text = lines.slice(tIdx + 1).join(' ');
      if (text) {
        parsed.push({
          id: `cap_${parsed.length + 1}`,
          start: Number(s.toFixed(3)),
          end: Number(Math.max(e, s + 0.2).toFixed(3)),
          text,
          originalText: text,
          styleName: 'Default',
        });
      }
    }
    if (parsed.length > 0) {
      setCaptions(parsed, 'medium_word');
      setSubtitlePanelState('editor');
      toast.success('Subtitle file imported', `${parsed.length} cues from ${file.name}`);
    } else {
      toast.warn('No cues parsed', 'Please select a valid .srt or .vtt subtitle file.');
    }
  };

  const handleBurnWithProducer = async () => {
    if (projectId === 'demo') {
      toast.info('Demo sandbox preview updated', 'Open a real project to NVENC-burn subtitles via Producer.');
      return;
    }
    const cid = activeClipId || boardState?.clip_studio?.clips?.[0]?.candidate_id || 'clip_01';
    setBurning(true);
    try {
      const sid = await ensureSessionForProject(projectId);
      await studioApi.changeStylePreset(sid, {
        candidate_id: cid,
        style_preset: activeSubtitlePreset,
        project_id: projectId,
        layout_mode: aiTools.layoutMode,
        corrections: Object.keys(corrections).length > 0 ? corrections : undefined,
      });
      setRunning(true);
      setDockOpen(true);
      toast.success('Burn directive sent', `Re-rendering ${cid} with ${activeSubtitlePreset}.`);
    } catch (e) {
      toast.error('Burn request failed', String(e));
    } finally {
      setBurning(false);
    }
  };

  const styleGroups = useMemo(() => {
    const dyn: SubtitlePreset[] = [];
    const contentAware: SubtitlePreset[] = [];
    for (const p of presets) {
      if (DYNAMIC_PRESET_NAMES.has(p.name)) dyn.push(p);
      else contentAware.push(p);
    }
    return {
      dynamic: dyn.length ? dyn : presets,
      'content-aware': contentAware.length ? contentAware : presets,
    };
  }, [presets]);

  // ── STATE 1: Setup Screen ─────────────────────────────────────────────
  if (subtitlePanelState === 'setup') {
    return (
      <div className="flex h-full flex-col p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-[var(--text-primary)]">Subtitles</h2>
          {captions.length > 0 && (
            <button
              type="button"
              onClick={() => setSubtitlePanelState('editor')}
              className="text-xs font-semibold text-[var(--accent-lime-strong)] hover:underline cursor-pointer"
            >
              View {captions.length} lines
            </button>
          )}
        </div>

        <div className="space-y-2.5">
          <div>
            <label className="mb-1 block text-xs font-medium text-[var(--text-secondary)]">
              Spoken language
            </label>
            <select
              aria-label="Subtitle language"
              value={subtitleLanguage}
              onChange={(e) => setSubtitleLanguage(e.target.value)}
              className="h-9 w-full rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-input)] px-3 text-xs font-medium text-[var(--text-primary)]"
            >
              {LANGUAGES.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>
          </div>

          <button
            type="button"
            onClick={() => void handleAutoSubtitle()}
            className="flex w-full items-center gap-3 rounded-[12px] border border-[var(--accent-lime-border)] bg-[var(--accent-lime-soft)] p-4 text-left transition-all hover:brightness-95 cursor-pointer"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] bg-[var(--accent-lime)] text-zinc-950">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <div className="text-sm font-bold text-[var(--text-primary)]">Auto-subtitle</div>
              <div className="text-xs text-[var(--text-secondary)]">
                Sync captions from project transcript with Hinglish &amp; Seam support
              </div>
            </div>
          </button>

          <input
            ref={uploadInputRef}
            type="file"
            accept=".srt,.vtt,.ass"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void handleUploadSrt(f);
              e.target.value = '';
            }}
          />
          <button
            type="button"
            onClick={() => uploadInputRef.current?.click()}
            className="flex w-full items-center gap-3 rounded-[12px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3.5 text-left hover:border-[var(--border-strong)] hover:bg-[var(--bg-panel)] transition-colors cursor-pointer"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--bg-panel)] text-[var(--text-secondary)]">
              <FileUp className="h-4 w-4" />
            </div>
            <div>
              <div className="text-xs font-semibold text-[var(--text-primary)]">Upload Subtitle File</div>
              <div className="text-[11px] text-[var(--text-muted)]">Import .SRT, .VTT, or .ASS</div>
            </div>
          </button>

          <button
            type="button"
            onClick={() => addCaptionAtTime(playbackHub.currentTime, safeDur)}
            className="flex w-full items-center gap-3 rounded-[12px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3.5 text-left hover:border-[var(--border-strong)] hover:bg-[var(--bg-panel)] transition-colors cursor-pointer"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--bg-panel)] text-[var(--text-secondary)]">
              <Plus className="h-4 w-4" />
            </div>
            <div>
              <div className="text-xs font-semibold text-[var(--text-primary)]">Manual Subtitles</div>
              <div className="text-[11px] text-[var(--text-muted)]">Type timed captions from scratch</div>
            </div>
          </button>
        </div>
      </div>
    );
  }

  // ── STATE 2: Non-Blocking Pale-Lime Processing Screen ─────────────────
  if (subtitlePanelState === 'processing') {
    return (
      <div className="flex h-full flex-col p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-[var(--text-primary)]">Subtitles</h2>
          <button
            type="button"
            onClick={handleCancelProcessing}
            className="rounded-md px-2.5 py-1 text-xs font-semibold text-[var(--text-secondary)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)] cursor-pointer"
          >
            Cancel
          </button>
        </div>

        <div className="flex flex-1 flex-col items-center justify-center text-center px-6">
          {/* Pale-lime square progress illustration with moving short lime bar */}
          <div className="flex h-24 w-24 flex-col items-center justify-center rounded-[18px] border border-[var(--accent-lime-border)]/40 bg-[var(--accent-lime-soft)] shadow-xs">
            <div className="space-y-1.5 w-14">
              <div className="h-1.5 w-10 rounded-full bg-[var(--accent-lime-border)]/35 mx-auto" />
              <div className="h-2 w-14 overflow-hidden rounded-full bg-[var(--accent-lime-border)]/25">
                <div className="h-full w-6 rounded-full bg-[var(--accent-lime-strong)] animate-lime-slide" />
              </div>
              <div className="h-1.5 w-8 rounded-full bg-[var(--accent-lime-border)]/35 mx-auto" />
            </div>
          </div>

          <h3 className="mt-5 text-sm font-bold text-[var(--text-primary)]">
            Generating Subtitles…
          </h3>
          <p className="mt-1.5 text-xs text-[var(--text-muted)] leading-relaxed">
            Aligning {subtitleLanguage} word timestamps and checking mobile safe zones. You can keep
            scrubbing the preview.
          </p>
        </div>
      </div>
    );
  }

  // ── STATE 3B: Portrait Style Gallery (Section E) ──────────────────────
  if (subtitleTab === 'style') {
    const activeGroup: SubtitleStyleGroup = subtitleStyleGroup || 'dynamic';
    const cards = styleGroups[activeGroup];
    const groupTitle = activeGroup === 'content-aware' ? 'Content Aware' : 'Dynamic';

    return (
      <div className="flex h-full flex-col overflow-hidden">
        {/* Top Back Header + Duration */}
        <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-4 py-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label="Back to Subtitle Editor"
              onClick={() => {
                if (subtitleStyleGroup) setSubtitleStyleGroup(null);
                else setSubtitleTab('edit');
              }}
              className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--text-secondary)] hover:bg-[var(--bg-panel)] hover:text-[var(--text-primary)] cursor-pointer"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <h2 className="text-sm font-bold text-[var(--text-primary)]">{groupTitle}</h2>
          </div>
          <span className="font-mono text-xs text-[var(--text-muted)] tabular-nums">
            {formatTimecode(safeDur, false)}
          </span>
        </div>

        {/* Group Switcher Pills: Dynamic vs Content Aware */}
        <div className="flex items-center gap-1.5 px-4 pt-3 pb-2">
          {(
            [
              ['dynamic', 'Dynamic'],
              ['content-aware', 'Content Aware'],
            ] as const
          ).map(([gid, label]) => (
            <button
              key={gid}
              type="button"
              onClick={() => setSubtitleStyleGroup(gid)}
              className={cn(
                'rounded-full px-3 py-1 text-xs font-semibold border transition-colors cursor-pointer',
                activeGroup === gid
                  ? 'border-[var(--accent-lime-border)] bg-[var(--accent-lime)] text-zinc-950'
                  : 'border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]',
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {/* 3-Column Portrait Gallery (106×133px, 10px radius, 10px gaps) */}
        <div className="flex-1 overflow-y-auto px-4 pb-4 pt-1">
          <div className="grid grid-cols-3 gap-[10px]">
            {cards.map((p, idx) => {
              const selected = activeSubtitlePreset === p.name;
              const isSeamDemo = activeGroup === 'content-aware';
              return (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => {
                    setActiveSubtitlePreset(p.name);
                    toast.info(`Style: ${p.display_name}`, `${p.font_name} applied live`);
                  }}
                  style={{ background: PORTRAIT_BACKDROPS[idx % PORTRAIT_BACKDROPS.length] }}
                  className={cn(
                    'group relative flex h-[133px] w-full flex-col justify-between overflow-hidden rounded-[10px] p-2 text-center transition-all cursor-pointer border-2',
                    selected
                      ? 'border-[var(--accent-lime-border)] ring-2 ring-[var(--accent-lime)]/50'
                      : 'border-transparent hover:border-[var(--border-strong)]',
                  )}
                >
                  {/* Subtle speaker portrait framing */}
                  <div className="mx-auto mt-1 h-8 w-8 rounded-full bg-white/15 border border-white/20 flex items-center justify-center">
                    <div className="h-4 w-4 rounded-full bg-amber-200/75" />
                  </div>

                  {/* Live Real-Font Typography Sample */}
                  <div
                    className={cn(
                      'my-auto leading-tight',
                      isSeamDemo ? 'translate-y-0' : 'translate-y-1',
                    )}
                    style={{
                      fontFamily: `"${p.font_name}", "Noto Sans Devanagari", "Inter", sans-serif`,
                      fontWeight: p.bold ? 800 : 600,
                      fontStyle: p.italic ? 'italic' : 'normal',
                      textTransform: p.uppercase ? 'uppercase' : 'none',
                      backgroundColor:
                        p.border_style === 3 ? p.back_hex || 'rgba(0,0,0,0.75)' : 'transparent',
                      textShadow: '0 1px 4px rgba(0,0,0,0.9)',
                    }}
                  >
                    <span className="text-[11px]" style={{ color: p.primary_hex }}>
                      THE{' '}
                    </span>
                    <span className="text-[12px]" style={{ color: p.active_hex }}>
                      QUICK
                    </span>
                    <div className="text-[10px]" style={{ color: p.primary_hex }}>
                      STORY
                    </div>
                  </div>

                  <div className="truncate rounded bg-black/55 px-1 py-0.5 text-[9px] font-medium text-white">
                    {p.display_name}
                  </div>

                  {selected && (
                    <span className="absolute right-1.5 top-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-[var(--accent-lime)] text-zinc-950">
                      <Check className="h-2.5 w-2.5 stroke-[3]" />
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          <div className="mt-4 rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-3 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-[var(--text-primary)]">Active Font Engine</span>
              <Badge tone="lime" className="font-mono text-[10px]">
                DirectWrite Verified
              </Badge>
            </div>
            <p className="text-[11px] text-[var(--text-muted)]">
              All 8 bundled OFL fonts render offline with zero Arial fallback and auto-switch to{' '}
              <span className="font-mono text-[var(--text-primary)]">Style: Seam</span> on 2-speaker
              split ranges.
            </p>
            <Button
              variant="primary"
              size="xs"
              className="w-full"
              disabled={burning}
              onClick={() => void handleBurnWithProducer()}
            >
              <Wand2 className="h-3.5 w-3.5" />
              Burn “{activeSubtitlePreset}” via Producer
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // ── STATE 3A: Subtitle Editing List (Section D) ───────────────────────
  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header: Title, Language Selector, Settings Icon, Style/Edit Segmented Switch */}
      <div className="space-y-3 border-b border-[var(--border-subtle)] px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-base font-bold text-[var(--text-primary)]">Subtitles</h2>
          <div className="flex items-center gap-1.5">
            <select
              aria-label="Subtitle language"
              value={subtitleLanguage}
              onChange={(e) => setSubtitleLanguage(e.target.value)}
              className="h-7 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2 text-[11px] font-medium text-[var(--text-primary)]"
            >
              {LANGUAGES.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </select>

            <button
              type="button"
              aria-label="Subtitle settings"
              onClick={() => setSettingsOpen((v) => !v)}
              className={cn(
                'flex h-7 w-7 items-center justify-center rounded-md border transition-colors cursor-pointer',
                settingsOpen
                  ? 'border-[var(--accent-lime-border)] bg-[var(--accent-lime-soft)] text-[var(--text-primary)]'
                  : 'border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
              )}
            >
              <SlidersHorizontal className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Segmented Style / Edit Switch */}
        <div className="grid grid-cols-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-0.5 text-xs font-semibold">
          <button
            type="button"
            onClick={() => {
              setSubtitleTab('style');
              setSubtitleStyleGroup('dynamic');
            }}
            className="rounded-md py-1.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors cursor-pointer"
          >
            Style
          </button>
          <button
            type="button"
            onClick={() => setSubtitleTab('edit')}
            className="rounded-md bg-[var(--bg-surface)] py-1.5 text-[var(--text-primary)] shadow-2xs cursor-pointer"
          >
            Edit
          </button>
        </div>

        {/* Optional Settings Popover */}
        {settingsOpen && (
          <div className="rounded-[10px] border border-[var(--border-strong)] bg-[var(--bg-panel)] p-2.5 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-[var(--text-secondary)]">Timing Provenance</span>
              <Badge tone="neutral" className="font-mono text-[10px]">
                {subtitleEvidenceQuality}
              </Badge>
            </div>
            <label className="flex items-center justify-between cursor-pointer">
              <span className="text-[var(--text-secondary)]">Auto Style: Seam on 2-Speaker Split</span>
              <input
                type="checkbox"
                checked={aiTools.seamSubtitles}
                onChange={(e) => updateAiTools({ seamSubtitles: e.target.checked })}
                className="h-3.5 w-3.5 accent-[var(--accent-lime-strong)]"
              />
            </label>
            <div className="flex justify-between pt-1">
              <button
                type="button"
                onClick={() => setSubtitlePanelState('setup')}
                className="text-[11px] font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] cursor-pointer"
              >
                Re-run Auto-subtitle…
              </button>
              <button
                type="button"
                onClick={() => setSettingsOpen(false)}
                className="text-[11px] font-semibold text-[var(--accent-lime-strong)] cursor-pointer"
              >
                Done
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Caption Rows List (Generous vertical spacing, 15px text, thin lime left bar + lime active highlight) */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2.5">
        {captions.length === 0 ? (
          <div className="rounded-[10px] border border-dashed border-[var(--border-strong)] p-6 text-center space-y-2">
            <div className="text-xs font-semibold text-[var(--text-primary)]">No subtitles yet</div>
            <p className="text-[11px] text-[var(--text-muted)]">
              Run Auto-subtitle or click Add Subtitle on the timeline.
            </p>
            <Button size="xs" variant="lime" onClick={() => void handleAutoSubtitle()}>
              Auto-subtitle
            </Button>
          </div>
        ) : (
          captions.map((cap) => {
            const active = activeCaptionId === cap.id;
            const isEditing = editingRowId === cap.id;
            return (
              <div
                key={cap.id}
                onClick={() => {
                  setActiveCaptionId(cap.id);
                  playbackHub.requestSeek(cap.start + 0.05);
                }}
                className={cn(
                  'cv-auto group relative flex items-start justify-between gap-2 rounded-[10px] px-3 py-2.5 transition-all cursor-pointer border',
                  active
                    ? 'border-[var(--accent-lime-border)]/70 bg-[var(--accent-lime-soft)]/70'
                    : 'border-transparent hover:border-[var(--border-subtle)] hover:bg-[var(--bg-panel)]/70',
                )}
              >
                {/* Thin Lime Bar at Left for Current Row */}
                {active && (
                  <span className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r-full bg-[var(--accent-lime-border)]" />
                )}

                <div className="min-w-0 flex-1 pl-1">
                  {isEditing ? (
                    <input
                      autoFocus
                      value={cap.text}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => updateCaptionText(cap.id, e.target.value)}
                      onBlur={() => setEditingRowId(null)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === 'Escape') setEditingRowId(null);
                      }}
                      className="w-full rounded border border-[var(--accent-lime-border)] bg-[var(--bg-surface)] px-1.5 py-0.5 text-[15px] text-[var(--text-primary)] focus:outline-none"
                    />
                  ) : (
                    <div
                      onDoubleClick={(e) => {
                        e.stopPropagation();
                        setEditingRowId(cap.id);
                      }}
                      className="text-[15px] leading-snug text-[var(--text-primary)]"
                    >
                      <span
                        className={cn(
                          'rounded px-0.5 transition-colors',
                          active && 'bg-[var(--accent-lime)]/65 text-zinc-950 font-medium',
                        )}
                      >
                        {cap.text}
                      </span>
                    </div>
                  )}

                  <div className="mt-1 flex items-center gap-2 font-mono text-[10px] text-[var(--text-muted)] tabular-nums">
                    <span>
                      {formatTimecode(cap.start)} – {formatTimecode(cap.end)}
                    </span>
                    {cap.styleName === 'Seam' && (
                      <span className="rounded bg-[var(--track-sub-bg)] px-1 text-[9px] text-[var(--track-sub-text)]">
                        Seam
                      </span>
                    )}
                  </div>
                </div>

                {/* Overflow Menu Trigger */}
                <div className="relative shrink-0">
                  <button
                    type="button"
                    aria-label="Caption actions"
                    onClick={(e) => {
                      e.stopPropagation();
                      setOpenMenuId(openMenuId === cap.id ? null : cap.id);
                    }}
                    className="flex h-7 w-7 items-center justify-center rounded-md text-[var(--text-muted)] opacity-70 hover:bg-[var(--bg-surface)] hover:text-[var(--text-primary)] hover:opacity-100 cursor-pointer"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </button>

                  {openMenuId === cap.id && (
                    <div
                      onClick={(e) => e.stopPropagation()}
                      className="absolute right-0 top-8 z-30 w-44 rounded-[10px] border border-[var(--border-strong)] bg-[var(--bg-surface)] p-1 shadow-[var(--shadow-float)] text-xs"
                    >
                      <button
                        type="button"
                        onClick={() => {
                          setEditingRowId(cap.id);
                          setOpenMenuId(null);
                        }}
                        className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left hover:bg-[var(--bg-panel)] cursor-pointer"
                      >
                        Edit text
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          duplicateCaption(cap.id);
                          setOpenMenuId(null);
                        }}
                        className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left hover:bg-[var(--bg-panel)] cursor-pointer"
                      >
                        <Copy className="h-3.5 w-3.5 text-[var(--text-muted)]" /> Duplicate
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          updateCaptionTiming(cap.id, cap.start, cap.end + 0.5);
                          setOpenMenuId(null);
                        }}
                        className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left hover:bg-[var(--bg-panel)] cursor-pointer"
                      >
                        <Clock className="h-3.5 w-3.5 text-[var(--text-muted)]" /> Extend +0.5s
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setSubtitleTab('style');
                          setSubtitleStyleGroup('dynamic');
                          setOpenMenuId(null);
                        }}
                        className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left hover:bg-[var(--bg-panel)] cursor-pointer"
                      >
                        <Sparkles className="h-3.5 w-3.5 text-[var(--text-muted)]" /> Change Style
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          void saveItem('saved', `Subtitle · ${activeSubtitlePreset}`, {
                            kind: 'subtitle_style',
                            preset: activeSubtitlePreset,
                            sample: cap.text,
                          });
                          setOpenMenuId(null);
                        }}
                        className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left hover:bg-[var(--bg-panel)] cursor-pointer"
                      >
                        <BookmarkPlus className="h-3.5 w-3.5 text-[var(--text-muted)]" /> Save to Brand Kit
                      </button>
                      <div className="my-1 border-t border-[var(--border-subtle)]" />
                      <button
                        type="button"
                        onClick={() => {
                          deleteCaption(cap.id);
                          setOpenMenuId(null);
                        }}
                        className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[var(--status-fail)] hover:bg-[var(--status-fail-soft)] cursor-pointer"
                      >
                        <Trash2 className="h-3.5 w-3.5" /> Delete
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Bottom Burn / Corrections Footer */}
      <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-2.5 space-y-2">
        {Object.keys(corrections).length > 0 && (
          <div className="flex items-center justify-between text-[11px] text-[var(--text-secondary)]">
            <span>{Object.keys(corrections).length} non-destructive typo fix(es) staged</span>
            <Badge tone="lime" className="text-[9px]">
              Raw Transcript Safe
            </Badge>
          </div>
        )}
        <Button
          variant="primary"
          size="xs"
          className="w-full rounded-full"
          disabled={burning}
          onClick={() => void handleBurnWithProducer()}
        >
          <Wand2 className="h-3.5 w-3.5" />
          Apply &amp; Burn ({activeSubtitlePreset})
        </Button>
      </div>
    </div>
  );
}
