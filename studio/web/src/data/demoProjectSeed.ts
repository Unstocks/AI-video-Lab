import type { CaptionCue } from '@/types/editor';
import type { TranscriptWord } from '@/types/studio';

export const DEMO_PROJECT_ID = 'demo';
export const DEMO_PROJECT_TITLE = 'Book Reading Reflection — Hinglish Short';
export const DEMO_DURATION = 24.0;

export const DEMO_CAPTIONS: CaptionCue[] = [
  { id: 'cap_001', start: 0.2, end: 2.8, text: 'Kabhi-kabhi hum kisi book', originalText: 'Kabhi-kabhi hum kisi book', speaker: 'Speaker 1', styleName: 'Default' },
  { id: 'cap_002', start: 2.85, end: 5.4, text: 'ko padte, hum bas ek ya', originalText: 'ko padte, hum bas ek ya', speaker: 'Speaker 1', styleName: 'Default' },
  { id: 'cap_003', start: 5.45, end: 8.1, text: 'do page padke pura book', originalText: 'do page padke pura book', speaker: 'Speaker 1', styleName: 'Default' },
  { id: 'cap_004', start: 8.15, end: 10.2, text: 'kaisa hai, aye', originalText: 'kaisa hai, aye', speaker: 'Speaker 1', styleName: 'Default' },
  { id: 'cap_005', start: 10.25, end: 12.9, text: 'discuss kar lete hain.', originalText: 'discuss kar lete hain.', speaker: 'Speaker 1', styleName: 'Default' },
  { id: 'cap_006', start: 13.4, end: 16.0, text: 'But as we keep reading,', originalText: 'But as we keep reading,', speaker: 'Speaker 1', styleName: 'Seam' },
  { id: 'cap_007', start: 16.05, end: 18.8, text: 'the whole perspective shifts', originalText: 'the whole perspective shifts', speaker: 'Speaker 1', styleName: 'Seam' },
  { id: 'cap_008', start: 18.85, end: 21.4, text: 'chapter by chapter, until', originalText: 'chapter by chapter, until', speaker: 'Speaker 1', styleName: 'Default' },
  { id: 'cap_009', start: 21.45, end: 23.8, text: 'the real story unlocks.', originalText: 'the real story unlocks.', speaker: 'Speaker 1', styleName: 'Default' },
];

export const DEMO_TRANSCRIPT_WORDS: TranscriptWord[] = DEMO_CAPTIONS.flatMap((cap) => {
  const tokens = cap.text.split(/\s+/).filter(Boolean);
  const step = (cap.end - cap.start) / Math.max(1, tokens.length);
  return tokens.map((word, idx) => ({
    word,
    start: Number((cap.start + idx * step).toFixed(3)),
    end: Number((cap.start + (idx + 1) * step).toFixed(3)),
    speaker: cap.speaker,
  }));
});

export const DEMO_WAVEFORM_PEAKS: number[] = Array.from({ length: 180 }, (_, i) => {
  const wave = Math.abs(Math.sin(i * 0.27) * Math.cos(i * 0.11));
  const pauseDip = (i > 95 && i < 103) || (i > 142 && i < 148) ? 0.08 : 1;
  return Number(Math.max(0.06, Math.min(0.98, (0.22 + wave * 0.76) * pauseDip)).toFixed(3));
});
