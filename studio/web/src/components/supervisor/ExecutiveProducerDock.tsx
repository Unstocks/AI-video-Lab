import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Cpu,
  Loader2,
  Plus,
  Send,
  Sparkles,
  Square,
  Terminal,
  Trash2,
  User,
  XCircle,
} from 'lucide-react';
import { studioApi } from '@/lib/api';
import { cn, formatRelativeTime } from '@/lib/format';
import {
  toast,
  useProjectStore,
  useSupervisorStore,
  useSystemStore,
} from '@/stores/useStudioStore';
import { Badge, Button, StatusDot } from '@/components/ui/Primitives';
import type { SupervisorMessage } from '@/types/studio';

interface PairedToolCall {
  kind: 'tool';
  id: number;
  tool_id: string;
  name: string;
  input_summary: string;
  input: unknown;
  result_summary?: string;
  is_error?: boolean;
  finished: boolean;
  created_at: string;
}

type TimelineEntry =
  | { kind: 'message'; msg: SupervisorMessage }
  | PairedToolCall;

function groupMessages(messages: SupervisorMessage[]): TimelineEntry[] {
  const out: TimelineEntry[] = [];
  const toolById = new Map<string, PairedToolCall>();

  for (const m of messages) {
    if (m.role === 'tool_use') {
      const tid = String(m.content?.tool_id || `tool_${m.id}`);
      const card: PairedToolCall = {
        kind: 'tool',
        id: m.id,
        tool_id: tid,
        name: String(m.content?.name || 'tool'),
        input_summary: String(m.content?.input_summary || ''),
        input: m.content?.input,
        finished: false,
        created_at: m.created_at,
      };
      toolById.set(tid, card);
      out.push(card);
    } else if (m.role === 'tool_result') {
      const tid = String(m.content?.tool_id || '');
      const existing = tid ? toolById.get(tid) : undefined;
      if (existing) {
        existing.finished = true;
        existing.is_error = Boolean(m.content?.is_error);
        existing.result_summary = String(m.content?.summary || '');
      } else {
        out.push({ kind: 'message', msg: m });
      }
    } else {
      out.push({ kind: 'message', msg: m });
    }
  }
  return out;
}

function ToolCallCard({ item }: { item: PairedToolCall }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)]/70 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-2.5 py-2 text-left text-[11px] hover:bg-[var(--bg-elevated)]/50 transition-colors cursor-pointer"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" />
        )}
        {!item.finished ? (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-[var(--accent-cyan)]" />
        ) : item.is_error ? (
          <XCircle className="h-3.5 w-3.5 shrink-0 text-[var(--status-fail)]" />
        ) : (
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-[var(--status-pass)]" />
        )}
        <span className="font-mono font-semibold text-[var(--text-primary)] truncate">
          {item.name}
        </span>
        <span className="ml-auto truncate max-w-[140px] font-mono text-[10px] text-[var(--text-muted)]">
          {item.input_summary}
        </span>
      </button>
      {open && (
        <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-canvas)] px-2.5 py-2 space-y-2 text-[11px]">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1">
              Input
            </div>
            <pre className="max-h-36 overflow-auto rounded bg-[var(--bg-surface)] p-2 font-mono text-[10px] text-[var(--text-secondary)]">
              {JSON.stringify(item.input ?? item.input_summary, null, 2)}
            </pre>
          </div>
          {item.finished && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] mb-1">
                Output
              </div>
              <pre
                className={cn(
                  'max-h-36 overflow-auto rounded bg-[var(--bg-surface)] p-2 font-mono text-[10px] whitespace-pre-wrap',
                  item.is_error ? 'text-[var(--status-fail)]' : 'text-[var(--text-secondary)]',
                )}
              >
                {item.result_summary || '(empty)'}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const QUICK_DIRECTIVES = [
  'Summarize current project state & next gate',
  'Run preflight tool discovery for this pipeline',
  'Audit audio loudness & subtitle timing on rendered clips',
];

export function ExecutiveProducerDock() {
  const { health, refreshHealth, dockWidth, setDockWidth } = useSystemStore();
  const { activeProjectId, boardState, loadProject } = useProjectStore();
  const {
    sessions,
    activeSessionId,
    messages,
    running,
    sending,
    loadSessions,
    selectSession,
    ensureSessionForProject,
    appendMessage,
    setRunning,
    sendMessage,
    stopActiveRun,
    deleteSession,
  } = useSupervisorStore();

  const [input, setInput] = useState('');
  const [switchingModel, setSwitchingModel] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // Live SSE stream for active session
  useEffect(() => {
    if (!activeSessionId) return;
    const es = new EventSource(`/api/studio/sessions/${encodeURIComponent(activeSessionId)}/stream`);
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.message && typeof data.message === 'object') {
          appendMessage(data.message as SupervisorMessage);
        }
        if (data.type === 'run.start') {
          setRunning(true);
        } else if (data.type === 'run.done') {
          setRunning(false);
          loadSessions();
          if (activeProjectId) loadProject(activeProjectId, true);
        } else if (data.type === 'session.linked_project' && data.project_id) {
          loadSessions();
          loadProject(String(data.project_id), true);
        }
      } catch {
        // ignore malformed heartbeat
      }
    };
    return () => es.close();
  }, [activeSessionId, activeProjectId, appendMessage, loadProject, loadSessions, setRunning]);

  const timeline = useMemo(() => groupMessages(messages), [messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [timeline.length, running]);

  const awaitingStage = useMemo(
    () => boardState?.stages?.find((s) => s.status === 'awaiting_human') ?? null,
    [boardState],
  );

  const handleModelSwitch = async (model: string) => {
    if (!model) return;
    setSwitchingModel(true);
    try {
      const res = await studioApi.switchFccModel(model);
      if (res.ok) {
        toast.success('FCC model switched', `Active model: ${model}`);
      } else {
        toast.warn('Model switch note', String(res.detail || 'Check FCC proxy'));
      }
      await refreshHealth();
    } catch (e) {
      toast.error('Failed to switch model', String(e));
    } finally {
      setSwitchingModel(false);
    }
  };

  const handleResizeMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = dockWidth;
    const onMove = (me: MouseEvent) => {
      setDockWidth(startW + (startX - me.clientX));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const handleSend = async () => {
    if (!input.trim() || sending) return;
    const text = input;
    setInput('');
    await sendMessage(text, activeProjectId);
  };

  const handleQuickGate = async (decision: 'approve' | 'revise') => {
    if (!activeProjectId || !awaitingStage) return;
    try {
      const sid = await ensureSessionForProject(activeProjectId);
      await studioApi.sendGateDecision(sid, {
        stage: awaitingStage.name,
        decision,
        project_id: activeProjectId,
      });
      setRunning(true);
      toast.success(`Gate ${decision}d`, `Stage "${awaitingStage.name}" directive dispatched.`);
    } catch (e) {
      toast.error('Gate action failed', String(e));
    }
  };

  return (
    <aside
      style={{ width: dockWidth }}
      aria-label="Executive Producer Supervisor Dock"
      className="relative flex h-full shrink-0 flex-col border-l border-[var(--border-subtle)] bg-[var(--bg-surface)]"
    >
      {/* Drag resize handle */}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize Supervisor Dock"
        onMouseDown={handleResizeMouseDown}
        className="absolute inset-y-0 -left-1 z-20 w-2 cursor-col-resize hover:bg-[var(--accent-cyan)]/40 transition-colors"
      />

      {/* Dock Header */}
      <div className="flex items-center justify-between border-b border-[var(--border-subtle)] px-3.5 py-2.5">
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-amber-soft)] text-[var(--accent-amber)]">
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-[var(--text-primary)] truncate">
                Executive Producer
              </span>
              <StatusDot
                tone={running ? 'cyan' : health?.fcc_online ? 'pass' : 'warn'}
                pulse={running}
              />
            </div>
            <div className="text-[10px] font-mono text-[var(--text-muted)] truncate">
              {health?.fcc_online
                ? `fcc-claude · ${health.fcc_active_model || 'online'}`
                : 'fcc-claude offline (127.0.0.1:8082)'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1">
          {running && (
            <Button variant="danger" size="xs" onClick={stopActiveRun} title="Stop Supervisor">
              <Square className="h-3 w-3 fill-current" />
              Stop
            </Button>
          )}
          <Button
            variant="ghost"
            size="xs"
            title="New Supervisor Session"
            onClick={async () => {
              const s = await studioApi.createSession({
                project_id: activeProjectId,
                title: activeProjectId ? `Director · ${activeProjectId}` : 'New Session',
              });
              await loadSessions();
              await selectSession(s.session_id);
            }}
          >
            <Plus className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Session & Model Bar */}
      <div className="flex items-center gap-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-canvas)]/50 px-3 py-2">
        <select
          aria-label="Active Supervisor Session"
          value={activeSessionId || ''}
          onChange={(e) => e.target.value && selectSession(e.target.value)}
          className="min-w-0 flex-1 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2 py-1 text-[11px] text-[var(--text-primary)] focus:outline-none"
        >
          {sessions.length === 0 && <option value="">No sessions yet</option>}
          {sessions.map((s) => (
            <option key={s.session_id} value={s.session_id}>
              {s.title} {s.project_id ? `(${s.project_id})` : ''}
            </option>
          ))}
        </select>

        {activeSessionId && (
          <button
            type="button"
            title="Delete current session"
            aria-label="Delete current session"
            onClick={() => deleteSession(activeSessionId)}
            className="rounded-md p-1 text-[var(--text-muted)] hover:bg-[var(--status-fail-soft)] hover:text-[var(--status-fail)] transition-colors cursor-pointer"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Optional Live FCC Model Switcher */}
      {health?.fcc_online && health.fcc_models.length > 0 && (
        <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-1.5 text-[11px]">
          <Cpu className="h-3.5 w-3.5 text-[var(--accent-cyan)] shrink-0" />
          <span className="text-[var(--text-muted)] shrink-0">Model</span>
          <select
            aria-label="FCC Active Model"
            disabled={switchingModel}
            value={health.fcc_active_model || ''}
            onChange={(e) => handleModelSwitch(e.target.value)}
            className="min-w-0 flex-1 rounded border border-[var(--border-subtle)] bg-[var(--bg-input)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-primary)]"
          >
            {health.fcc_models.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Inline Human Gate Banner */}
      {awaitingStage && (
        <div className="mx-3 mt-2.5 rounded-xl border border-[var(--accent-amber)]/40 bg-[var(--accent-amber-soft)] p-2.5">
          <div className="flex items-center justify-between gap-2">
            <Badge tone="amber">AWAITING GATE · {awaitingStage.name}</Badge>
            <span className="font-mono text-[10px] text-[var(--text-secondary)]">
              {activeProjectId}
            </span>
          </div>
          <div className="mt-2 flex items-center gap-1.5">
            <Button variant="primary" size="xs" className="flex-1" onClick={() => handleQuickGate('approve')}>
              Approve &amp; Continue
            </Button>
            <Button variant="secondary" size="xs" onClick={() => handleQuickGate('revise')}>
              Revise
            </Button>
          </div>
        </div>
      )}

      {/* Streaming Timeline */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2.5">
        {timeline.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <Terminal className="h-7 w-7 text-[var(--text-muted)] mb-2" />
            <p className="text-xs font-medium text-[var(--text-secondary)]">
              Top Supervisor Ready
            </p>
            <p className="mt-1 text-[11px] text-[var(--text-muted)] max-w-[260px]">
              Direct any of the 13 pipelines, approve gates, recut clips, or inspect QA metrics in natural language.
            </p>
            <div className="mt-4 w-full space-y-1.5">
              {QUICK_DIRECTIVES.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => setInput(q)}
                  className="block w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)]/70 px-2.5 py-2 text-left text-[11px] text-[var(--text-secondary)] hover:border-[var(--accent-amber)]/50 hover:text-[var(--text-primary)] transition-colors cursor-pointer"
                >
                  “{q}”
                </button>
              ))}
            </div>
          </div>
        ) : (
          timeline.map((entry) => {
            if (entry.kind === 'tool') {
              return <ToolCallCard key={`tool-${entry.id}`} item={entry} />;
            }
            const m = entry.msg;
            const text = String(m.content?.text || m.content?.summary || '');
            const isUser = m.role === 'user';
            const isSystem = m.role === 'system';
            const isErr = Boolean(m.content?.is_error);

            if (isSystem) {
              return (
                <div
                  key={m.id}
                  className={cn(
                    'rounded-lg border px-2.5 py-1.5 text-[11px]',
                    isErr
                      ? 'border-[var(--status-fail)]/40 bg-[var(--status-fail-soft)] text-[var(--status-fail)]'
                      : 'border-[var(--border-subtle)] bg-[var(--bg-canvas)]/60 text-[var(--text-muted)]',
                  )}
                >
                  {text}
                </div>
              );
            }

            return (
              <div
                key={m.id}
                className={cn(
                  'rounded-xl border px-3 py-2.5 text-xs leading-relaxed',
                  isUser
                    ? 'ml-5 border-[var(--accent-amber)]/30 bg-[var(--accent-amber-soft)]/70 text-[var(--text-primary)]'
                    : 'mr-2 border-[var(--border-subtle)] bg-[var(--bg-panel)] text-[var(--text-primary)]',
                )}
              >
                <div className="mb-1 flex items-center justify-between text-[10px] text-[var(--text-muted)]">
                  <span className="inline-flex items-center gap-1 font-medium">
                    {isUser ? <User className="h-3 w-3" /> : <Bot className="h-3 w-3 text-[var(--accent-cyan)]" />}
                    {isUser ? 'Producer' : 'Supervisor'}
                  </span>
                  <span className="font-mono">{formatRelativeTime(m.created_at)}</span>
                </div>
                <div className="whitespace-pre-wrap break-words">{text}</div>
              </div>
            );
          })
        )}

        {running && (
          <div className="flex items-center gap-2 rounded-lg border border-[var(--accent-cyan)]/30 bg-[var(--accent-cyan-soft)] px-3 py-2 text-[11px] text-[var(--accent-cyan)]">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            <span>Top Supervisor executing pipeline turn…</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Composer */}
      <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-canvas)]/60 p-3">
        <div className="flex items-end gap-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-input)] px-2.5 py-2 focus-within:border-[var(--accent-cyan)]">
          <textarea
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder={
              activeProjectId
                ? `Direct ${activeProjectId}… (Enter to send)`
                : 'Message Executive Producer… (Enter to send)'
            }
            className="max-h-28 min-h-[36px] flex-1 resize-none bg-transparent text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none"
          />
          <Button
            variant="primary"
            size="xs"
            disabled={!input.trim() || sending || running}
            onClick={handleSend}
            aria-label="Send directive"
          >
            {sending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
          </Button>
        </div>
      </div>
    </aside>
  );
}
