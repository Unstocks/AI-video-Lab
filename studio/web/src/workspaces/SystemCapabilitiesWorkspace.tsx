import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  HardDrive,
  Loader2,
  Music,
  Palette,
  RefreshCw,
  Search,
  Wrench,
  XCircle,
} from 'lucide-react';
import { cn, formatBytes } from '@/lib/format';
import { useSystemStore } from '@/stores/useStudioStore';
import { Badge, Button, Panel, StatusDot } from '@/components/ui/Primitives';

export function SystemCapabilitiesWorkspace() {
  const {
    health,
    tools,
    toolsLoading,
    playbooks,
    musicLibrary,
    config,
    loadTools,
    loadMusicLibrary,
    refreshHealth,
  } = useSystemStore();

  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'available' | 'degraded' | 'unavailable'>('all');
  const [capFilter, setCapFilter] = useState<string>('all');
  const [activeTab, setActiveTab] = useState<'tools' | 'playbooks' | 'music'>('tools');

  useEffect(() => {
    loadTools(false);
    loadMusicLibrary();
  }, [loadTools, loadMusicLibrary]);

  const filteredTools = useMemo(() => {
    const list = tools?.tools ?? [];
    const q = query.trim().toLowerCase();
    return list.filter((t) => {
      if (statusFilter !== 'all' && t.status !== statusFilter) return false;
      if (capFilter !== 'all' && t.capability !== capFilter) return false;
      if (!q) return true;
      return (
        t.name.toLowerCase().includes(q) ||
        t.capability.toLowerCase().includes(q) ||
        t.provider.toLowerCase().includes(q) ||
        t.install_instructions.toLowerCase().includes(q)
      );
    });
  }, [capFilter, query, statusFilter, tools]);

  const budgetCfg = (config?.budget as Record<string, unknown>) || {};

  return (
    <div className="mx-auto max-w-[1360px] space-y-5 p-5">
      {/* Hardware & Runtime Telemetry Strip */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Panel className="p-4">
          <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
            <span>Top Supervisor (FCC)</span>
            <StatusDot tone={health?.fcc_online ? 'pass' : 'warn'} />
          </div>
          <div className="mt-1.5 text-sm font-semibold">
            {health?.fcc_online ? health.fcc_active_model || 'Online' : 'Offline'}
          </div>
          <div className="mt-1 font-mono text-[10px] text-[var(--text-muted)] truncate">
            {health?.fcc_base_url || 'http://127.0.0.1:8082'}
          </div>
        </Panel>

        <Panel className="p-4">
          <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
            <span>Video Hardware Encoder</span>
            <Cpu className="h-4 w-4 text-[var(--accent-cyan)]" />
          </div>
          <div className="mt-1.5 text-sm font-semibold">
            {health?.nvenc_available ? 'h264_nvenc (GPU)' : 'libx264 (CPU)'}
          </div>
          <div className="mt-1 font-mono text-[10px] text-[var(--text-muted)]">
            Face Tracker: {health?.face_detector || 'YuNet ONNX'}
          </div>
        </Panel>

        <Panel className="p-4">
          <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
            <span>Composition Runtimes</span>
            <HardDrive className="h-4 w-4 text-[var(--accent-amber)]" />
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {Object.entries(tools?.composition_runtimes || { ffmpeg: true }).map(([eng, ok]) => (
              <Badge key={eng} tone={ok ? 'pass' : 'neutral'}>
                {eng}: {ok ? 'ready' : 'off'}
              </Badge>
            ))}
          </div>
        </Panel>

        <Panel className="p-4">
          <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
            <span>Tool Registry Coverage</span>
            <Wrench className="h-4 w-4 text-[var(--accent-violet)]" />
          </div>
          <div className="mt-1.5 flex items-baseline gap-2">
            <span className="text-lg font-bold font-mono text-[var(--status-pass)]">
              {tools?.counts?.available ?? '—'}
            </span>
            <span className="text-xs text-[var(--text-muted)]">
              / {tools?.total ?? '—'} ready · {tools?.counts?.degraded ?? 0} degraded
            </span>
          </div>
          <div className="mt-1 font-mono text-[10px] text-[var(--text-muted)]">
            Global Budget Cap: ${String(budgetCfg.total_usd ?? 10)} ({String(budgetCfg.mode ?? 'warn')})
          </div>
        </Panel>
      </div>

      {/* Section Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] p-0.5">
          {(
            [
              ['tools', `169-Tool Matrix (${tools?.total ?? '…'})`, Wrench],
              ['playbooks', `Style Playbooks (${playbooks.length})`, Palette],
              ['music', `Local Music Library (${musicLibrary?.count ?? 0})`, Music],
            ] as const
          ).map(([id, label, Icon]) => (
            <button
              key={id}
              type="button"
              onClick={() => setActiveTab(id)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all cursor-pointer',
                activeTab === id
                  ? 'bg-[var(--bg-elevated)] text-[var(--text-primary)] shadow-xs'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              {label}
            </button>
          ))}
        </div>

        <Button
          variant="secondary"
          size="sm"
          disabled={toolsLoading}
          onClick={() => {
            refreshHealth();
            loadTools(true);
            loadMusicLibrary();
          }}
        >
          <RefreshCw className={cn('h-3.5 w-3.5', toolsLoading && 'animate-spin')} />
          Rescan Hardware &amp; Registry
        </Button>
      </div>

      {/* Tab 1: Tool Registry */}
      {activeTab === 'tools' && (
        <div className="space-y-4">
          {tools?.runtime_warnings && tools.runtime_warnings.length > 0 && (
            <div className="rounded-xl border border-[var(--status-warn)]/35 bg-[var(--status-warn-soft)] px-4 py-3 text-xs text-[var(--status-warn)] space-y-1">
              <div className="font-semibold flex items-center gap-1.5">
                <AlertTriangle className="h-4 w-4" /> Runtime Diagnostics
              </div>
              {tools.runtime_warnings.map((w, i) => (
                <div key={i} className="font-mono text-[11px] opacity-90">
                  • {w}
                </div>
              ))}
            </div>
          )}

          {/* Filters */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-[var(--text-muted)]" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search tools, providers, capabilities, or API keys…"
                className="h-8 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] pl-8 pr-3 text-xs focus:border-[var(--accent-cyan)] focus:outline-none"
              />
            </div>

            {(['all', 'available', 'degraded', 'unavailable'] as const).map((st) => (
              <Button
                key={st}
                size="sm"
                variant={statusFilter === st ? 'primary' : 'secondary'}
                onClick={() => setStatusFilter(st)}
              >
                {st === 'all' ? 'All' : st === 'unavailable' ? 'Setup Needed' : st}
              </Button>
            ))}

            <select
              aria-label="Filter by capability"
              value={capFilter}
              onChange={(e) => setCapFilter(e.target.value)}
              className="h-8 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 text-xs"
            >
              <option value="all">All 27 Capability Families</option>
              {(tools?.capabilities ?? []).map((c) => (
                <option key={c.capability} value={c.capability}>
                  {c.capability} ({c.configured}/{c.total})
                </option>
              ))}
            </select>
          </div>

          {toolsLoading && !tools ? (
            <div className="flex items-center justify-center py-16 text-xs text-[var(--text-muted)]">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Discovering 169 OpenMontage tools…
            </div>
          ) : (
            <Panel className="overflow-hidden">
              <div className="max-h-[560px] overflow-auto">
                <table className="w-full text-left text-xs">
                  <thead className="sticky top-0 z-10 border-b border-[var(--border-subtle)] bg-[var(--bg-panel)] text-[11px] uppercase tracking-wider text-[var(--text-muted)]">
                    <tr>
                      <th className="px-3.5 py-2.5">Tool</th>
                      <th className="px-3.5 py-2.5">Capability</th>
                      <th className="px-3.5 py-2.5">Provider</th>
                      <th className="px-3.5 py-2.5">Status</th>
                      <th className="px-3.5 py-2.5">Best For / Setup</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border-subtle)]/60">
                    {filteredTools.map((t) => (
                      <tr key={t.name} className="hover:bg-[var(--bg-elevated)]/40">
                        <td className="px-3.5 py-2.5 font-mono font-semibold text-[var(--text-primary)]">
                          {t.name}
                          <div className="text-[10px] font-normal text-[var(--text-muted)]">
                            {t.tier} · {t.runtime}
                          </div>
                        </td>
                        <td className="px-3.5 py-2.5 font-mono text-[11px] text-[var(--text-secondary)]">
                          {t.capability}
                        </td>
                        <td className="px-3.5 py-2.5 text-[var(--text-secondary)]">{t.provider}</td>
                        <td className="px-3.5 py-2.5">
                          <Badge
                            tone={
                              t.status === 'available'
                                ? 'pass'
                                : t.status === 'degraded'
                                  ? 'warn'
                                  : 'neutral'
                            }
                          >
                            {t.status === 'available' ? (
                              <CheckCircle2 className="h-3 w-3" />
                            ) : t.status === 'degraded' ? (
                              <AlertTriangle className="h-3 w-3" />
                            ) : (
                              <XCircle className="h-3 w-3" />
                            )}
                            {t.status}
                          </Badge>
                        </td>
                        <td className="px-3.5 py-2.5 max-w-md text-[11px] text-[var(--text-muted)]">
                          {t.status === 'available'
                            ? t.best_for.slice(0, 2).join(' · ') || 'Ready'
                            : t.install_instructions || 'Configure provider credentials in .env'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
        </div>
      )}

      {/* Tab 2: Style Playbooks */}
      {activeTab === 'playbooks' && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {playbooks.map((pb) => (
            <Panel key={pb.slug} className="overflow-hidden">
              <div
                className="flex h-20 items-end justify-between p-4 border-b border-[var(--border-subtle)]"
                style={{ backgroundColor: pb.palette.background, color: pb.palette.text }}
              >
                <div>
                  <div className="text-sm font-bold">{pb.name}</div>
                  <div className="text-[11px] opacity-75">{pb.category} · {pb.pace}</div>
                </div>
                <div className="flex gap-1.5">
                  {[...pb.palette.primary, ...pb.palette.accent].slice(0, 4).map((hex, idx) => (
                    <span
                      key={idx}
                      title={hex}
                      className="h-5 w-5 rounded-md border border-black/20 shadow-xs"
                      style={{ backgroundColor: hex }}
                    />
                  ))}
                </div>
              </div>
              <div className="p-4 space-y-2 text-xs">
                <p className="text-[var(--text-secondary)]">{pb.best_for || pb.mood}</p>
                <div className="flex flex-wrap gap-1.5 pt-1 font-mono text-[10px]">
                  <Badge tone="neutral">H: {pb.typography.heading_font}</Badge>
                  <Badge tone="neutral">B: {pb.typography.body_font}</Badge>
                  <Badge tone="neutral">C: {pb.typography.code_font}</Badge>
                </div>
                {pb.music_mood && (
                  <div className="text-[11px] text-[var(--text-muted)]">
                    Audio Mood: {pb.music_mood}
                  </div>
                )}
              </div>
            </Panel>
          ))}
        </div>
      )}

      {/* Tab 3: Local Music Library */}
      {activeTab === 'music' && (
        <Panel className="p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold">Local Royalty-Free Music Library</h3>
              <p className="font-mono text-[11px] text-[var(--text-muted)]">
                {musicLibrary?.library_dir || 'music_library/'}
              </p>
            </div>
            <Badge tone="neutral">{musicLibrary?.count ?? 0} tracks</Badge>
          </div>
          {!musicLibrary || musicLibrary.tracks.length === 0 ? (
            <div className="rounded-lg border border-dashed border-[var(--border-strong)] p-8 text-center text-xs text-[var(--text-muted)]">
              Drop <code className="font-mono text-[var(--text-primary)]">.mp3</code>, <code className="font-mono text-[var(--text-primary)]">.wav</code>, or <code className="font-mono text-[var(--text-primary)]">.m4a</code> tracks into <code className="font-mono text-[var(--text-primary)]">music_library/</code> to audition and select them free at proposal time.
            </div>
          ) : (
            <div className="divide-y divide-[var(--border-subtle)]">
              {musicLibrary.tracks.map((tr) => (
                <div key={tr.rel_path} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div>
                    <div className="text-xs font-semibold">{tr.name}</div>
                    <div className="font-mono text-[10px] text-[var(--text-muted)]">
                      {tr.rel_path} · {formatBytes(tr.size_bytes)}
                    </div>
                  </div>
                  <audio controls preload="none" src={tr.stream_url} className="h-8 w-72" />
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}
