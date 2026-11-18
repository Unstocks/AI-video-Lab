import type { TextOverlayItem } from '@/types/editor';

export type TextTemplateCategory = 'Simple' | 'Title' | 'Lower Third' | 'Other';

export interface TextTemplateDef {
  id: string;
  label: string;
  sublabel?: string;
  section: 'Quick' | 'Title' | 'Lower Third' | 'Other';
  category: TextTemplateCategory;
  sampleText: string;
  sampleSubtext?: string;
  fontFamily: string;
  fontSize: number;
  fontWeight: number;
  italic?: boolean;
  uppercase?: boolean;
  color: string;
  backgroundColor?: string;
  letterSpacing?: string;
}

export const TEXT_TEMPLATES: TextTemplateDef[] = [
  // Quick top 2-column grid (6 featured tiles)
  {
    id: 'tpl_title',
    label: 'Title',
    section: 'Quick',
    category: 'Title',
    sampleText: 'Title',
    fontFamily: '"Montserrat", "Inter", sans-serif',
    fontSize: 32,
    fontWeight: 800,
    color: '#ffffff',
  },
  {
    id: 'tpl_simple',
    label: 'Simple',
    section: 'Quick',
    category: 'Simple',
    sampleText: 'Simple',
    fontFamily: '"Inter", sans-serif',
    fontSize: 22,
    fontWeight: 500,
    color: '#ffffff',
  },
  {
    id: 'tpl_cursive',
    label: 'Cursive',
    section: 'Quick',
    category: 'Simple',
    sampleText: 'Cursive',
    fontFamily: '"Playfair Display", Georgia, serif',
    fontSize: 28,
    fontWeight: 600,
    italic: true,
    color: '#fef08a',
  },
  {
    id: 'tpl_serif',
    label: 'Serif',
    section: 'Quick',
    category: 'Simple',
    sampleText: 'Serif',
    fontFamily: '"Noto Serif", "Playfair Display", Georgia, serif',
    fontSize: 28,
    fontWeight: 700,
    color: '#ffffff',
  },
  {
    id: 'tpl_typewriter',
    label: 'Typewriter',
    section: 'Quick',
    category: 'Other',
    sampleText: 'Typewriter',
    fontFamily: '"JetBrains Mono", monospace',
    fontSize: 22,
    fontWeight: 600,
    color: '#4ade80',
    backgroundColor: 'rgba(15,23,42,0.72)',
  },
  {
    id: 'tpl_bold',
    label: 'bold',
    section: 'Quick',
    category: 'Title',
    sampleText: 'bold',
    fontFamily: '"Anton", "Montserrat", sans-serif',
    fontSize: 34,
    fontWeight: 800,
    color: '#c6f64d',
    letterSpacing: '0.02em',
  },

  // Title section (exact 6 signature pairs)
  {
    id: 'tpl_bold_traditional',
    label: 'bold',
    sublabel: 'Traditional',
    section: 'Title',
    category: 'Title',
    sampleText: 'bold',
    sampleSubtext: 'Traditional',
    fontFamily: '"Montserrat", sans-serif',
    fontSize: 30,
    fontWeight: 800,
    color: '#ffffff',
  },
  {
    id: 'tpl_editorial_classic',
    label: 'Editorial',
    sublabel: 'Classic',
    section: 'Title',
    category: 'Title',
    sampleText: 'Editorial',
    sampleSubtext: 'Classic',
    fontFamily: '"Playfair Display", Georgia, serif',
    fontSize: 28,
    fontWeight: 700,
    italic: true,
    color: '#faf7f2',
  },
  {
    id: 'tpl_modern_bauhaus',
    label: 'Modern',
    sublabel: 'Bauhaus',
    section: 'Title',
    category: 'Title',
    sampleText: 'Modern',
    sampleSubtext: 'Bauhaus',
    fontFamily: '"Outfit", "Inter", sans-serif',
    fontSize: 28,
    fontWeight: 700,
    color: '#38bdf8',
    letterSpacing: '0.04em',
  },
  {
    id: 'tpl_elegant_light',
    label: 'Elegant',
    sublabel: 'Light',
    section: 'Title',
    category: 'Title',
    sampleText: 'Elegant',
    sampleSubtext: 'Light',
    fontFamily: '"Playfair Display", Georgia, serif',
    fontSize: 26,
    fontWeight: 400,
    color: '#ffffff',
    letterSpacing: '0.08em',
  },
  {
    id: 'tpl_signature_industrial',
    label: 'Signature',
    sublabel: 'INDUSTRIAL',
    section: 'Title',
    category: 'Title',
    sampleText: 'Signature',
    sampleSubtext: 'INDUSTRIAL',
    fontFamily: '"Anton", sans-serif',
    fontSize: 28,
    fontWeight: 700,
    uppercase: true,
    color: '#facc15',
    letterSpacing: '0.06em',
  },
  {
    id: 'tpl_reliable_typewriter',
    label: 'RELIABLE',
    sublabel: 'Typewriter',
    section: 'Title',
    category: 'Title',
    sampleText: 'RELIABLE',
    sampleSubtext: 'Typewriter',
    fontFamily: '"JetBrains Mono", monospace',
    fontSize: 22,
    fontWeight: 700,
    uppercase: true,
    color: '#ffffff',
    backgroundColor: 'rgba(17,24,39,0.75)',
  },

  // Lower Thirds
  {
    id: 'tpl_lt_speaker',
    label: 'Speaker Tag',
    sublabel: 'Host · Podcast',
    section: 'Lower Third',
    category: 'Lower Third',
    sampleText: 'Vicky Sharma',
    sampleSubtext: 'Host · AI Video Lab',
    fontFamily: '"Poppins", "Inter", sans-serif',
    fontSize: 20,
    fontWeight: 700,
    color: '#111827',
    backgroundColor: '#c6f64d',
  },
  {
    id: 'tpl_lt_chapter',
    label: 'Chapter Pill',
    sublabel: '01 · Hook',
    section: 'Lower Third',
    category: 'Lower Third',
    sampleText: '01 · THE KEY INSIGHT',
    fontFamily: '"Inter", sans-serif',
    fontSize: 16,
    fontWeight: 700,
    uppercase: true,
    color: '#ffffff',
    backgroundColor: 'rgba(17,24,39,0.82)',
    letterSpacing: '0.08em',
  },

  // Other
  {
    id: 'tpl_comic_callout',
    label: 'Comic Pop',
    sublabel: 'Viral Callout',
    section: 'Other',
    category: 'Other',
    sampleText: 'WAIT FOR IT!',
    fontFamily: '"Bangers", sans-serif',
    fontSize: 30,
    fontWeight: 400,
    uppercase: true,
    color: '#39ff14',
    letterSpacing: '0.06em',
  },
  {
    id: 'tpl_hinglish_quote',
    label: 'Hinglish Note',
    sublabel: 'Devanagari Safe',
    section: 'Other',
    category: 'Other',
    sampleText: 'असली कहानी यहाँ शुरू होती है',
    fontFamily: '"Noto Sans Devanagari", "Inter", sans-serif',
    fontSize: 22,
    fontWeight: 700,
    color: '#ffb800',
    backgroundColor: 'rgba(0,0,0,0.68)',
  },
];

export function createOverlayFromTemplate(
  tpl: TextTemplateDef,
  startSeconds: number,
  maxDuration: number,
): TextOverlayItem {
  const start = Math.max(0, Number(startSeconds.toFixed(2)));
  const end = Math.min(Math.max(maxDuration, start + 3), Number((start + 3.5).toFixed(2)));
  return {
    id: `txt_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 5)}`,
    templateId: tpl.id,
    category: tpl.category,
    text: tpl.sampleText,
    subtext: tpl.sampleSubtext,
    start,
    end,
    x: 0.5,
    y: tpl.category === 'Lower Third' ? 0.78 : 0.28,
    width: tpl.category === 'Lower Third' ? 0.72 : 0.62,
    height: tpl.sampleSubtext ? 0.14 : 0.1,
    rotation: 0,
    fontFamily: tpl.fontFamily,
    fontSize: tpl.fontSize,
    fontWeight: tpl.fontWeight,
    italic: tpl.italic,
    uppercase: tpl.uppercase,
    color: tpl.color,
    backgroundColor: tpl.backgroundColor,
    letterSpacing: tpl.letterSpacing,
  };
}
