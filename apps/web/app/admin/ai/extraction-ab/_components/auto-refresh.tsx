'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export function ExtractionAbAutoRefresh({ active }: { active: boolean }) {
  const router = useRouter();

  useEffect(() => {
    if (!active) return;
    const interval = window.setInterval(() => {
      router.refresh();
    }, 5_000);
    return () => window.clearInterval(interval);
  }, [active, router]);

  return null;
}
