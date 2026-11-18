import { useState } from 'react';
import { ArrowRight, Sparkles, X } from 'lucide-react';
import { Button } from '@/components/ui/Primitives';

export function HeroFeatureBanner({
  onPrimaryAction,
  onTryDemo,
}: {
  onPrimaryAction: () => void;
  onTryDemo: () => void;
}) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  return (
    <section
      aria-label="Featured Studio Workflow"
      className="relative overflow-hidden rounded-[22px] border border-[var(--accent-lime-border)]/40 bg-[var(--accent-lime-soft)] px-7 py-6 shadow-[var(--shadow-panel)]"
    >
      <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
        {/* Left Copy + Dark-Green CTA Pill */}
        <div className="max-w-lg space-y-3">
          <div className="inline-flex items-center gap-1.5 rounded-full bg-white/75 dark:bg-black/30 px-2.5 py-0.5 text-[11px] font-semibold text-[#14452f] dark:text-[var(--accent-lime)]">
            <Sparkles className="h-3 w-3" />
            RTX 3050 NVENC · YuNet Reframe v2 · 8 Bundled Fonts
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-[#102a1d] dark:text-[var(--text-primary)] leading-tight">
            Clone your studio workflow
          </h2>
          <p className="text-sm text-[#284b38] dark:text-[var(--text-secondary)] leading-relaxed">
            Turn any 16:9 podcast or talking video into viral 9:16 Shorts with automatic 2-speaker
            split framing, <span className="font-semibold">Style: Seam</span> Hinglish/English
            subtitles, and Broadcast −14 LUFS QA.
          </p>
          <div className="flex flex-wrap items-center gap-2.5 pt-1">
            <Button
              variant="forest"
              size="md"
              onClick={onPrimaryAction}
              className="rounded-full px-5"
            >
              Start AI Clip Studio
              <ArrowRight className="h-4 w-4" />
            </Button>
            <button
              type="button"
              onClick={onTryDemo}
              className="rounded-full border border-[#14452f]/25 dark:border-[var(--border-strong)] bg-white/70 dark:bg-black/25 px-4 py-2 text-xs font-semibold text-[#14452f] dark:text-[var(--text-primary)] hover:bg-white dark:hover:bg-black/40 transition-colors cursor-pointer"
            >
              Open Interactive Demo Editor
            </button>
          </div>
        </div>

        {/* Right Side-by-Side Portrait Comparison Cards: Original vs AI Reframe */}
        <div className="relative flex items-center gap-3 self-start lg:self-center shrink-0">
          <button
            type="button"
            onClick={() => setDismissed(true)}
            aria-label="Dismiss banner"
            title="Dismiss banner"
            className="absolute -right-2 -top-2 z-10 flex h-7 w-7 items-center justify-center rounded-full border border-black/10 bg-white/90 text-zinc-700 shadow-sm hover:bg-white cursor-pointer"
          >
            <X className="h-3.5 w-3.5" />
          </button>

          {/* Card 1: Original */}
          <div className="relative h-[156px] w-[124px] overflow-hidden rounded-[14px] border border-black/10 bg-gradient-to-b from-slate-700 via-slate-800 to-slate-950 p-2.5 shadow-sm">
            <span className="inline-block rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-semibold text-white">
              Original
            </span>
            <div className="mt-5 flex items-center justify-center gap-1.5">
              <div className="h-12 w-11 rounded-md border border-white/20 bg-gradient-to-br from-sky-400/35 to-indigo-600/35 flex items-end justify-center pb-1">
                <div className="h-6 w-6 rounded-full bg-amber-200/80" />
              </div>
              <div className="h-12 w-11 rounded-md border border-white/20 bg-gradient-to-br from-emerald-400/35 to-teal-600/35 flex items-end justify-center pb-1">
                <div className="h-6 w-6 rounded-full bg-orange-200/80" />
              </div>
            </div>
            <div className="mt-3 text-center font-mono text-[9px] text-slate-300">
              16:9 Raw Source
            </div>
          </div>

          {/* Card 2: AI Clone / AI Reframe */}
          <div className="relative h-[156px] w-[124px] overflow-hidden rounded-[14px] border-2 border-[#14452f]/60 bg-gradient-to-b from-zinc-900 to-black shadow-md flex flex-col">
            <div className="relative flex-1 bg-gradient-to-br from-sky-500/30 to-indigo-900/50 flex items-center justify-center">
              <span className="absolute left-2 top-2 rounded-full bg-[#c6f64d] px-2 py-0.5 text-[10px] font-bold text-zinc-950">
                AI Clone
              </span>
              <div className="h-8 w-8 rounded-full bg-amber-200/90 mt-3" />
            </div>
            {/* Style: Seam center subtitle badge */}
            <div className="z-10 -my-2.5 mx-1.5 rounded bg-black/85 px-1.5 py-0.5 text-center text-[9px] font-extrabold tracking-tight text-white shadow">
              PURE <span className="text-[#c6f64d]">SEAM</span> 9:16
            </div>
            <div className="flex-1 bg-gradient-to-br from-emerald-500/25 to-teal-950/60 flex items-center justify-center">
              <div className="h-8 w-8 rounded-full bg-orange-200/90" />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
