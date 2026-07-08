export interface TranscriptCue {
  speaker: string | null;
  text: string;
  offsetMs: number;
  endOffsetMs: number;
}

function vttTimeToMs(t: string): number {
  const p = t.trim().split(':').map((x) => Number.parseFloat(x) || 0);
  if (p.length === 3) {
    return Math.round(((p[0] ?? 0) * 3600 + (p[1] ?? 0) * 60 + (p[2] ?? 0)) * 1000);
  }
  if (p.length === 2) {
    return Math.round(((p[0] ?? 0) * 60 + (p[1] ?? 0)) * 1000);
  }
  return 0;
}

/** Parse Teams WebVTT into cues. Handles `<v Speaker Name>text</v>` voice tags. */
export function parseVtt(vtt: string): TranscriptCue[] {
  const cues: TranscriptCue[] = [];
  const blocks = vtt.replace(/\r/g, '').split(/\n\n+/);
  for (const block of blocks) {
    const lines = block.split('\n').filter((l) => l.trim() !== '');
    const timingIdx = lines.findIndex((l) => l.includes('-->'));
    if (timingIdx === -1) continue;
    const timingLine = lines[timingIdx];
    if (!timingLine) continue;
    const [startText, endText] = timingLine.split('-->');
    const offsetMs = vttTimeToMs(startText ?? '');
    const endOffsetMs = vttTimeToMs(endText?.split(/\s+/)[0] ?? '');

    let text = lines.slice(timingIdx + 1).join(' ').trim();
    let speaker: string | null = null;
    const voice = text.match(/<v\s+([^>]+)>([\s\S]*?)<\/v>/i);
    if (voice) {
      speaker = (voice[1] ?? '').trim();
      text = (voice[2] ?? '').trim();
    } else {
      text = text.replace(/<[^>]+>/g, '').trim();
    }
    if (text) cues.push({ speaker, text, offsetMs, endOffsetMs });
  }
  return cues;
}

/** Merge consecutive cues from the same speaker into one fuller utterance. */
export function mergeBySpeaker(cues: TranscriptCue[]): TranscriptCue[] {
  const out: TranscriptCue[] = [];
  for (const c of cues) {
    const last = out[out.length - 1];
    if (last && last.speaker === c.speaker) {
      last.text = `${last.text} ${c.text}`.trim();
      last.endOffsetMs = Math.max(last.endOffsetMs, c.endOffsetMs);
    } else {
      out.push({ ...c });
    }
  }
  return out;
}

export function cuesToPlainText(cues: TranscriptCue[]): string {
  return cues
    .map((c) => (c.speaker ? `${c.speaker}: ${c.text}` : c.text))
    .join('\n')
    .trim();
}
