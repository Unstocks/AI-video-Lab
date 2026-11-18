export interface HomeTemplateCard {
  id: string;
  title: string;
  subtitle: string;
  category:
    | 'Promo'
    | 'Tips & How-To'
    | 'Thought Leadership'
    | 'Founder-led'
    | 'Testimonial';
  pipeline_type: string;
  style_playbook: string;
  style_preset: string;
  media_profile: string;
  sampleCaption: string;
  sampleCaptionHighlight: string;
  fontFamily: string;
  gradient: string;
  accentColor: string;
  badge: string;
}

export const HOME_TEMPLATE_CATEGORIES = [
  'All',
  'Promo',
  'Tips & How-To',
  'Thought Leadership',
  'Founder-led',
  'Testimonial',
] as const;

export const HOME_TEMPLATES: HomeTemplateCard[] = [
  {
    id: 'tpl_podcast_split',
    title: '2-Speaker Podcast Viral Split',
    subtitle: 'YuNet Reframe v2 · Style: Seam',
    category: 'Thought Leadership',
    pipeline_type: 'clip-factory',
    style_playbook: 'flat-motion-graphics',
    style_preset: 'hinglish_impact',
    media_profile: 'youtube_shorts',
    sampleCaption: 'BUT AS WE KEEP',
    sampleCaptionHighlight: 'READING',
    fontFamily: '"Noto Sans Devanagari", "Montserrat", sans-serif',
    gradient: 'linear-gradient(160deg, #1b2432 0%, #2c3e50 48%, #111827 100%)',
    accentColor: '#ffb800',
    badge: 'Clip Factory',
  },
  {
    id: 'tpl_founder_hook',
    title: 'Founder Story Hook',
    subtitle: 'Hormozi Pop · 9:16 Punch-In',
    category: 'Founder-led',
    pipeline_type: 'talking-head',
    style_playbook: 'premium-minimalist',
    style_preset: 'hormozi_pop',
    media_profile: 'instagram_reels',
    sampleCaption: 'WHY 90% OF',
    sampleCaptionHighlight: 'FOUNDERS FAIL',
    fontFamily: '"Montserrat", sans-serif',
    gradient: 'linear-gradient(155deg, #1a2e22 0%, #14452f 52%, #0c1712 100%)',
    accentColor: '#ffe600',
    badge: 'Talking Head',
  },
  {
    id: 'tpl_explainer_launch',
    title: 'Product Launch Promo',
    subtitle: 'HyperFrames Kinetic Motion',
    category: 'Promo',
    pipeline_type: 'animated-explainer',
    style_playbook: 'clean-professional',
    style_preset: 'neon_glow',
    media_profile: 'instagram_reels',
    sampleCaption: 'SHIP 10X',
    sampleCaptionHighlight: 'FASTER',
    fontFamily: '"Outfit", sans-serif',
    gradient: 'linear-gradient(150deg, #1e1b4b 0%, #3b0764 55%, #0f172a 100%)',
    accentColor: '#00ffff',
    badge: 'Explainer',
  },
  {
    id: 'tpl_howto_demo',
    title: '60s CLI & App Walkthrough',
    subtitle: 'Screen Demo · Minimal Mono',
    category: 'Tips & How-To',
    pipeline_type: 'screen-demo',
    style_playbook: 'minimalist-diagram',
    style_preset: 'minimal_mono',
    media_profile: 'youtube_shorts',
    sampleCaption: 'STEP 01:',
    sampleCaptionHighlight: 'AUTOMATE IT',
    fontFamily: '"JetBrains Mono", monospace',
    gradient: 'linear-gradient(155deg, #0f172a 0%, #1e293b 52%, #020617 100%)',
    accentColor: '#4ade80',
    badge: 'Screen Demo',
  },
  {
    id: 'tpl_testimonial_doc',
    title: 'Editorial Customer Story',
    subtitle: 'Editorial Serif · EBU R128',
    category: 'Testimonial',
    pipeline_type: 'hybrid',
    style_playbook: 'premium-minimalist',
    style_preset: 'editorial_serif',
    media_profile: 'tiktok_vertical',
    sampleCaption: 'It doubled our',
    sampleCaptionHighlight: 'watch time.',
    fontFamily: '"Playfair Display", Georgia, serif',
    gradient: 'linear-gradient(155deg, #3b2618 0%, #573620 50%, #1c130d 100%)',
    accentColor: '#f0b860',
    badge: 'Hybrid',
  },
  {
    id: 'tpl_avatar_brief',
    title: 'AI Spokesperson Briefing',
    subtitle: 'Avatar · Pill Highlight',
    category: 'Promo',
    pipeline_type: 'avatar-spokesperson',
    style_playbook: 'clean-professional',
    style_preset: 'pill_highlight',
    media_profile: 'instagram_reels',
    sampleCaption: 'MEET YOUR NEW',
    sampleCaptionHighlight: 'AI PRODUCER',
    fontFamily: '"Poppins", sans-serif',
    gradient: 'linear-gradient(155deg, #11343d 0%, #164e63 52%, #0b1920 100%)',
    accentColor: '#ffd700',
    badge: 'Avatar',
  },
  {
    id: 'tpl_cinematic_teaser',
    title: 'Cinematic Mood Teaser',
    subtitle: 'Documentary Clean · NVENC',
    category: 'Thought Leadership',
    pipeline_type: 'cinematic',
    style_playbook: 'anime-ghibli',
    style_preset: 'documentary_clean',
    media_profile: 'youtube_landscape',
    sampleCaption: 'THE FUTURE OF',
    sampleCaptionHighlight: 'STORYTELLING',
    fontFamily: '"Inter", sans-serif',
    gradient: 'linear-gradient(155deg, #271a38 0%, #432357 48%, #130f1e 100%)',
    accentColor: '#7dd3fc',
    badge: 'Cinematic',
  },
  {
    id: 'tpl_viral_bounce',
    title: 'High-Energy Viral Mythbuster',
    subtitle: 'Viral Bounce · Bangers',
    category: 'Tips & How-To',
    pipeline_type: 'podcast-repurpose',
    style_playbook: 'flat-motion-graphics',
    style_preset: 'viral_bounce',
    media_profile: 'tiktok_vertical',
    sampleCaption: 'STOP DOING',
    sampleCaptionHighlight: 'THIS NOW!',
    fontFamily: '"Bangers", sans-serif',
    gradient: 'linear-gradient(155deg, #2e1065 0%, #4c1d95 52%, #090d16 100%)',
    accentColor: '#39ff14',
    badge: 'Podcast',
  },
];
