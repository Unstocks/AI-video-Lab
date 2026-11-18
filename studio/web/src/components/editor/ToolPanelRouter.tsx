import { useEditorStore } from '@/stores/useEditorStore';
import { AIToolsPanel } from '@/components/editor/panels/AIToolsPanel';
import { VideoPanel } from '@/components/editor/panels/VideoPanel';
import {
  AudioPanel,
  ElementsPanel,
  ImagePanel,
  SettingsPanel,
} from '@/components/editor/panels/MediaToolPanels';
import { SubtitlePanel } from '@/components/editor/panels/SubtitlePanel';
import { TextPanel } from '@/components/editor/panels/TextPanel';
import { ScriptPanel } from '@/components/editor/panels/ScriptPanel';
import { BrandKitPanel } from '@/components/editor/panels/BrandKitPanel';

export function ToolPanelRouter({ duration }: { duration: number }) {
  const { activeTool } = useEditorStore();
  // Section G spec: widen contextual panel to 512px for Script doc-editor while rail stays 68px
  const panelWidth = activeTool === 'script' ? 512 : 364;

  return (
    <aside
      aria-label="Contextual Tool Panel"
      style={{ width: panelWidth }}
      className="flex h-full shrink-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-surface)] transition-[width] duration-200 overflow-hidden min-w-0 max-w-[46vw]"
    >
      {activeTool === 'ai-tools' && <AIToolsPanel />}
      {activeTool === 'video' && <VideoPanel />}
      {activeTool === 'audio' && <AudioPanel />}
      {activeTool === 'image' && <ImagePanel />}
      {activeTool === 'subtitles' && <SubtitlePanel duration={duration} />}
      {activeTool === 'text' && <TextPanel duration={duration} />}
      {activeTool === 'elements' && <ElementsPanel />}
      {activeTool === 'script' && <ScriptPanel duration={duration} />}
      {activeTool === 'brand-kit' && <BrandKitPanel />}
      {activeTool === 'settings' && <SettingsPanel />}
    </aside>
  );
}
