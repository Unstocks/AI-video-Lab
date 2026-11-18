import { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { HeroFeatureBanner } from '@/components/home/HeroFeatureBanner';
import {
  TalkingVideoComposer,
  type ComposerSeed,
} from '@/components/home/TalkingVideoComposer';
import { TemplateGallery } from '@/components/home/TemplateGallery';
import { toast } from '@/stores/useStudioStore';
import type { HomeTemplateCard } from '@/data/homeTemplates';

export function HomePage() {
  const navigate = useNavigate();
  const composerInputRef = useRef<HTMLInputElement>(null);
  const [composerSeed, setComposerSeed] = useState<ComposerSeed | null>(null);

  const handleSelectTemplate = (tpl: HomeTemplateCard) => {
    setComposerSeed({
      pipeline_type: tpl.pipeline_type,
      style_playbook: tpl.style_playbook,
      style_preset: tpl.style_preset,
      media_profile: tpl.media_profile,
    });
    toast.info(`Template loaded: ${tpl.title}`, `${tpl.pipeline_type} · ${tpl.style_preset}`);
    composerInputRef.current?.focus();
    composerInputRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  return (
    <div className="mx-auto w-full max-w-[1280px] space-y-9 px-6 py-7 lg:px-10">
      {/* Wide Pale-Lime Hero Feature Banner */}
      <HeroFeatureBanner
        onPrimaryAction={() => {
          setComposerSeed({
            pipeline_type: 'clip-factory',
            style_preset: 'hinglish_impact',
            media_profile: 'youtube_shorts',
          });
          composerInputRef.current?.focus();
        }}
        onTryDemo={() => navigate('/editor/demo')}
      />

      {/* Centered "Create a talking video" Rounded Prompt/URL Composer */}
      <TalkingVideoComposer seed={composerSeed} inputRef={composerInputRef} />

      {/* Left-Aligned "Start with a template" 5-Column Portrait Gallery */}
      <TemplateGallery onSelectTemplate={handleSelectTemplate} />
    </div>
  );
}
