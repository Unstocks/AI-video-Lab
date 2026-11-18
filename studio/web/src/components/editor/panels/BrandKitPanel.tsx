import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Lock,
  Plus,
  Search,
  Trash2,
  Upload,
} from 'lucide-react';
import { studioApi } from '@/lib/api';
import { cn } from '@/lib/format';
import { toast, useSystemStore } from '@/stores/useStudioStore';
import { useBrandKitStore } from '@/stores/useBrandKitStore';
import { useEditorStore } from '@/stores/useEditorStore';
import type { BrandKitRecord } from '@/types/studio';

const FILTER_CHIPS = [
  { id: 'all', label: 'All' },
  { id: 'saved', label: 'Saved Items' },
  { id: 'video', label: 'Videos' },
  { id: 'audio', label: 'Audio' },
  { id: 'image', label: 'Images' },
  { id: 'subtitle', label: 'Subtitles' },
  { id: 'font_color', label: 'Fonts & Colors' },
] as const;

export function BrandKitPanel() {
  const { playbooks, presets, musicLibrary, loadMusicLibrary } = useSystemStore();
  const { items, loadBrandKit, saveItem, removeItem } = useBrandKitStore();
  const { setActiveSubtitlePreset } = useEditorStore();

  const fileRef = useRef<HTMLInputElement>(null);
  const [uploadTargetCat, setUploadTargetCat] = useState<BrandKitRecord['category']>('video');
  const [query, setQuery] = useState('');
  const [chip, setChip] = useState<(typeof FILTER_CHIPS)[number]['id']>('all');
  const [workspaceName] = useState('My Workspace');

  useEffect(() => {
    void loadBrandKit();
    void loadMusicLibrary();
  }, [loadBrandKit, loadMusicLibrary]);

  const q = query.trim().toLowerCase();

  const savedItems = useMemo(
    () =>
      items.filter(
        (i) => i.category === 'saved' && (!q || i.name.toLowerCase().includes(q)),
      ),
    [items, q],
  );
  const videoItems = useMemo(
    () =>
      items.filter(
        (i) => i.category === 'video' && (!q || i.name.toLowerCase().includes(q)),
      ),
    [items, q],
  );
  const audioItems = useMemo(() => {
    const uploaded = items.filter(
      (i) => i.category === 'audio' && (!q || i.name.toLowerCase().includes(q)),
    );
    const localTracks = (musicLibrary?.tracks ?? [])
      .filter((t) => !q || t.name.toLowerCase().includes(q))
      .map((t) => ({
        item_id: `lib_${t.rel_path}`,
        category: 'audio' as const,
        name: t.name,
        payload: { stream_url: t.stream_url, rel_path: t.rel_path },
        created_at: '',
      }));
    return [...uploaded, ...localTracks];
  }, [items, musicLibrary, q]);

  const filteredPlaybooks = useMemo(
    () =>
      playbooks.filter(
        (pb) =>
          !q ||
          pb.name.toLowerCase().includes(q) ||
          pb.typography.heading_font.toLowerCase().includes(q),
      ),
    [playbooks, q],
  );

  const handleUpload = async (file: File) => {
    try {
      const res = await studioApi.uploadMediaFile(file);
      await saveItem(uploadTargetCat, res.filename, {
        path: res.path,
        size_bytes: res.size_bytes,
      });
    } catch (e) {
      toast.error('Upload failed', String(e));
    }
  };

  const triggerUpload = (cat: BrandKitRecord['category']) => {
    setUploadTargetCat(cat);
    fileRef.current?.click();
  };

  const showSection = (id: (typeof FILTER_CHIPS)[number]['id']) => chip === 'all' || chip === id;

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <input
        ref={fileRef}
        type="file"
        accept="video/*,audio/*,image/*,.srt,.ass"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void handleUpload(f);
          e.target.value = '';
        }}
      />

      {/* Heading "My Workspace" + Search + Upload + 2-Row Filter Chips */}
      <div className="space-y-3 border-b border-[var(--border-subtle)] px-4 py-3">
        <button
          type="button"
          className="inline-flex items-center gap-1.5 text-base font-bold text-[var(--text-primary)] cursor-pointer"
        >
          <span>{workspaceName}</span>
          <ChevronDown className="h-4 w-4 text-[var(--text-muted)]" />
        </button>

        {/* Search Field + Upload Icon Button */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-[var(--text-muted)]" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search your assets…"
              className="h-9 w-full rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-input)] pl-8 pr-3 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:border-[var(--accent-lime-border)] focus:outline-none"
            />
          </div>
          <button
            type="button"
            onClick={() => triggerUpload('video')}
            aria-label="Upload brand asset"
            title="Upload asset to Brand Kit"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:border-[var(--border-strong)] hover:text-[var(--text-primary)] cursor-pointer"
          >
            <Upload className="h-4 w-4" />
          </button>
        </div>

        {/* 2-Line Wrapping Filter Chips */}
        <div className="flex flex-wrap gap-1.5">
          {FILTER_CHIPS.map((c) => {
            const active = chip === c.id;
            return (
              <button
                key={c.id}
                type="button"
                onClick={() => setChip(c.id)}
                className={cn(
                  'rounded-full px-3 py-1 text-[11px] font-semibold border transition-colors cursor-pointer',
                  active
                    ? 'border-[var(--accent-lime-border)] bg-[var(--accent-lime)] text-zinc-950'
                    : 'border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:border-[var(--border-strong)]',
                )}
              >
                {c.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Grouped Collections (42–48px section spacing, 10px rounding, warm-gray outlines) */}
      <div className="flex-1 overflow-y-auto px-4 py-5 space-y-11">
        {/* Saved Items */}
        {showSection('saved') && (
          <section className="space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <h3 className="text-xs font-bold text-[var(--text-primary)]">Saved Items</h3>
                <span className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-amber-400/25 text-amber-600">
                  <Lock className="h-2.5 w-2.5" />
                </span>
              </div>
              <button
                type="button"
                onClick={() => setChip('saved')}
                className="inline-flex items-center gap-0.5 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-primary)] cursor-pointer"
              >
                View all <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {savedItems.length === 0 ? (
              <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-6 text-center">
                <div className="text-xs font-bold text-[var(--text-primary)]">No Saved Items</div>
                <p className="mt-1 text-[11px] text-[var(--text-muted)] leading-relaxed">
                  Select a subtitle style or text template and save it to Brand Kit for instant reuse.
                </p>
              </div>
            ) : (
              <div className="space-y-1.5">
                {savedItems.map((item) => (
                  <div
                    key={item.item_id}
                    className="flex items-center justify-between rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-xs"
                  >
                    <button
                      type="button"
                      onClick={() => {
                        if (typeof item.payload?.preset === 'string') {
                          setActiveSubtitlePreset(item.payload.preset);
                          toast.success('Applied saved preset', item.name);
                        }
                      }}
                      className="min-w-0 flex-1 truncate text-left font-medium text-[var(--text-primary)] hover:text-[var(--accent-lime-strong)] cursor-pointer"
                    >
                      {item.name}
                    </button>
                    <button
                      type="button"
                      aria-label="Delete saved item"
                      onClick={() => void removeItem(item.item_id)}
                      className="text-[var(--text-muted)] hover:text-[var(--status-fail)] cursor-pointer"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* Videos */}
        {showSection('video') && (
          <section className="space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <h3 className="text-xs font-bold text-[var(--text-primary)]">Videos</h3>
                <button
                  type="button"
                  aria-label="Upload brand video"
                  onClick={() => triggerUpload('video')}
                  className="flex h-5 w-5 items-center justify-center rounded-md border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-panel)] cursor-pointer"
                >
                  <Plus className="h-3 w-3" />
                </button>
              </div>
              <button
                type="button"
                onClick={() => setChip('video')}
                className="inline-flex items-center gap-0.5 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-primary)] cursor-pointer"
              >
                View all <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {videoItems.length === 0 ? (
              <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-6 text-center">
                <div className="text-xs font-bold text-[var(--text-primary)]">No Videos</div>
                <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                  Upload intro/outro clips here or select footage from the Video tab.
                </p>
              </div>
            ) : (
              <div className="space-y-1.5">
                {videoItems.map((item) => (
                  <div
                    key={item.item_id}
                    className="flex items-center justify-between rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-xs"
                  >
                    <span className="truncate font-medium">{item.name}</span>
                    <button
                      type="button"
                      onClick={() => void removeItem(item.item_id)}
                      className="text-[var(--text-muted)] hover:text-[var(--status-fail)] cursor-pointer"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* Audio */}
        {showSection('audio') && (
          <section className="space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <h3 className="text-xs font-bold text-[var(--text-primary)]">Audio</h3>
                <button
                  type="button"
                  aria-label="Upload brand audio"
                  onClick={() => triggerUpload('audio')}
                  className="flex h-5 w-5 items-center justify-center rounded-md border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-panel)] cursor-pointer"
                >
                  <Plus className="h-3 w-3" />
                </button>
              </div>
              <button
                type="button"
                onClick={() => setChip('audio')}
                className="inline-flex items-center gap-0.5 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-primary)] cursor-pointer"
              >
                View all <ChevronRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {audioItems.length === 0 ? (
              <div className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-4 py-6 text-center">
                <div className="text-xs font-bold text-[var(--text-primary)]">No Audio</div>
                <p className="mt-1 text-[11px] text-[var(--text-muted)]">
                  Upload music or SFX tracks, or drop files into <code className="font-mono">music_library/</code>.
                </p>
              </div>
            ) : (
              <div className="space-y-1.5">
                {audioItems.map((item) => (
                  <div
                    key={item.item_id}
                    className="flex items-center justify-between rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] px-3 py-2 text-xs"
                  >
                    <span className="truncate font-medium">{item.name}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        )}

        {/* Subtitles (8 Presets Quick Access) */}
        {chip === 'subtitle' && (
          <section className="space-y-2.5">
            <h3 className="text-xs font-bold text-[var(--text-primary)]">8 Bundled Subtitle Presets</h3>
            <div className="grid grid-cols-2 gap-2">
              {presets.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => {
                    setActiveSubtitlePreset(p.name);
                    toast.success(`Selected ${p.display_name}`);
                  }}
                  className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-panel)] p-2.5 text-left hover:border-[var(--accent-lime-border)] cursor-pointer"
                >
                  <div
                    className="truncate text-xs font-bold"
                    style={{ fontFamily: `"${p.font_name}", "Inter", sans-serif` }}
                  >
                    {p.display_name}
                  </div>
                  <div className="font-mono text-[10px] text-[var(--text-muted)]">{p.font_name}</div>
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Fonts & Colors (6 Real OpenMontage Style Playbooks) */}
        {showSection('font_color') && (
          <section className="space-y-2.5">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold text-[var(--text-primary)]">
                Fonts &amp; Colors (OpenMontage Playbooks)
              </h3>
            </div>
            <div className="space-y-2">
              {filteredPlaybooks.map((pb) => (
                <div
                  key={pb.slug}
                  className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-3"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-xs font-bold text-[var(--text-primary)]">
                      {pb.name}
                    </span>
                    <div className="flex items-center gap-1">
                      {[pb.palette.background, pb.palette.primary[0], pb.palette.accent[0]]
                        .filter(Boolean)
                        .map((hex, i) => (
                          <span
                            key={i}
                            title={hex}
                            className="h-4 w-4 rounded-full border border-black/15"
                            style={{ backgroundColor: hex }}
                          />
                        ))}
                    </div>
                  </div>
                  <div className="mt-1 font-mono text-[10px] text-[var(--text-muted)]">
                    {pb.typography.heading_font} · {pb.typography.body_font}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
