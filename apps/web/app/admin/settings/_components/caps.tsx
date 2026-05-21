// Shared capability icon definitions for the model picker and settings cards.
// No 'use client' — safe to import from server components.

import { Brain, Eye, FileText, ImageIcon, Wrench } from 'lucide-react';
import { cn } from '@/lib/utils';

export type CapKey = 'vision' | 'tools' | 'files' | 'reasoning' | 'imageGen';

export const CAPS = [
  {
    key: 'vision'    as CapKey,
    Icon: Eye,
    color: 'text-blue-500',
    label: 'Vision',
    desc: 'Accepts image input',
  },
  {
    key: 'tools'     as CapKey,
    Icon: Wrench,
    color: 'text-emerald-500',
    label: 'Tool use',
    desc: 'Supports function / tool calling',
  },
  {
    key: 'files'     as CapKey,
    Icon: FileText,
    color: 'text-orange-500',
    label: 'File input',
    desc: 'Accepts documents (PDF, DOCX…)',
  },
  {
    key: 'reasoning' as CapKey,
    Icon: Brain,
    color: 'text-purple-500',
    label: 'Reasoning',
    desc: 'Extended chain-of-thought / thinking',
  },
  {
    key: 'imageGen'  as CapKey,
    Icon: ImageIcon,
    color: 'text-pink-500',
    label: 'Image gen',
    desc: 'Generates image output',
  },
] as const;

/** Row of icons for a set of required capability keys. */
export function RequiredCapIcons({ keys }: { keys: CapKey[] }) {
  const caps = CAPS.filter((c) => keys.includes(c.key));
  if (caps.length === 0) return null;
  return (
    <div className="flex items-center gap-3 mt-3">
      {caps.map(({ key, Icon, color, label, desc }) => (
        <span
          key={key}
          title={desc}
          className="flex items-center gap-1 text-xs font-medium text-muted-foreground"
        >
          <Icon className={cn('size-3.5', color)} />
          {label}
        </span>
      ))}
    </div>
  );
}
