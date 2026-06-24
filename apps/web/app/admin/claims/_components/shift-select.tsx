'use client';

import { useEffect } from 'react';

// Shift-click range selection for the claims checkboxes.
//
// The checkboxes stay server-rendered and form-associated (submission is
// unchanged); this is a pure DOM enhancer. When a checkbox carrying
// data-claim-select is shift-clicked, every checkbox sharing the same
// data-select-form between the previously-clicked index and this one is set to
// the just-clicked box's checked state. Ranges are keyed by FORM, so a range
// never crosses the pending ("bulk-evaluate") / approved ("translate-claims")
// boundary even when both appear inside one meeting/document group.
export function ShiftSelect() {
  useEffect(() => {
    const lastIndexByForm: Record<string, number> = {};

    function onClick(event: MouseEvent) {
      const target = event.target as HTMLElement | null;
      const box = target?.closest<HTMLInputElement>(
        'input[type="checkbox"][data-claim-select]',
      );
      if (!box) return;

      const form = box.dataset.selectForm ?? '';
      const index = Number(box.dataset.selectIndex ?? '-1');
      if (!Number.isInteger(index) || index < 0) return;

      const last = lastIndexByForm[form];
      if (event.shiftKey && last !== undefined && last !== index) {
        const start = Math.min(last, index);
        const end = Math.max(last, index);
        const checked = box.checked; // click already toggled it
        const boxes = document.querySelectorAll<HTMLInputElement>(
          `input[type="checkbox"][data-claim-select][data-select-form="${form}"]`,
        );
        boxes.forEach((b) => {
          const i = Number(b.dataset.selectIndex ?? '-1');
          if (i >= start && i <= end) b.checked = checked;
        });
      }

      lastIndexByForm[form] = index;
    }

    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
  }, []);

  return null;
}
