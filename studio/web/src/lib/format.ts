import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatTimecode(seconds: number | null | undefined, showMs = true): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) {
    return showMs ? '00:00.00' : '00:00';
  }
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  const cs = Math.floor((seconds % 1) * 100);
  const pad = (n: number) => String(n).padStart(2, '0');
  const base = hrs > 0 ? `${pad(hrs)}:${pad(mins)}:${pad(secs)}` : `${pad(mins)}:${pad(secs)}`;
  return showMs ? `${base}.${pad(cs)}` : base;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let idx = 0;
  let val = bytes;
  while (val >= 1024 && idx < units.length - 1) {
    val /= 1024;
    idx += 1;
  }
  return `${val < 10 && idx > 0 ? val.toFixed(1) : Math.round(val)} ${units[idx]}`;
}

export function formatUsd(amount: number | null | undefined): string {
  if (amount == null || !Number.isFinite(amount)) return '$0.00';
  return `$${amount.toFixed(2)}`;
}

export function formatRelativeTime(epochSecOrIso: number | string | null | undefined): string {
  if (!epochSecOrIso) return '—';
  const ms =
    typeof epochSecOrIso === 'number'
      ? epochSecOrIso > 1e12
        ? epochSecOrIso
        : epochSecOrIso * 1000
      : Date.parse(epochSecOrIso);
  if (!Number.isFinite(ms)) return '—';
  const diffSec = Math.max(0, Math.floor((Date.now() - ms) / 1000));
  if (diffSec < 10) return 'just now';
  if (diffSec < 60) return `${diffSec}s ago`;
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

export function lufsStatus(lufs: number | null | undefined): 'pass' | 'warn' | 'fail' | 'unknown' {
  if (lufs == null || !Number.isFinite(lufs)) return 'unknown';
  if (lufs >= -16.0 && lufs <= -12.0) return 'pass';
  if (lufs >= -18.0 && lufs <= -10.0) return 'warn';
  return 'fail';
}

export function stripMediaPrefix(urlOrPath: string | null | undefined, projectId: string): string | null {
  if (!urlOrPath) return null;
  const clean = urlOrPath.replace(/^\/+/, '');
  const prefix = `media/${projectId}/`;
  if (clean.startsWith(prefix)) return clean.slice(prefix.length);
  return clean;
}

export function estimateExportSizeBytes(
  durationSeconds: number,
  resolution: '1080p' | '1440p' | '2160p' | '4k',
  codec: 'hevc' | 'h264' | 'auto',
  qualityTier: 'draft' | 'balanced' | 'master' = 'balanced',
  audioBitrateKbps: number = 256,
): number {
  const normRes = resolution === '4k' ? '2160p' : resolution;
  const normCodec = codec === 'auto' || codec === 'hevc' ? 'hevc' : 'h264';
  const bitrateTable: Record<string, Record<string, Record<string, number>>> = {
    '1080p': {
      hevc: { draft: 5_000_000, balanced: 8_500_000, master: 14_000_000 },
      h264: { draft: 7_500_000, balanced: 12_000_000, master: 18_000_000 },
    },
    '1440p': {
      hevc: { draft: 10_000_000, balanced: 18_000_000, master: 26_000_000 },
      h264: { draft: 14_000_000, balanced: 24_000_000, master: 35_000_000 },
    },
    '2160p': {
      hevc: { draft: 22_000_000, balanced: 36_000_000, master: 55_000_000 },
      h264: { draft: 32_000_000, balanced: 48_000_000, master: 75_000_000 },
    },
  };

  const videoBps = bitrateTable[normRes]?.[normCodec]?.[qualityTier] ?? 18_000_000;
  const audioBps = audioBitrateKbps * 1000;
  const totalBps = videoBps + audioBps;

  return Math.round((totalBps * Math.max(1, durationSeconds)) / 8);
}
