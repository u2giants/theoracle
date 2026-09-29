// S03 pilot journey browser test: upload → correct → confirm → answer after refresh.
import { test, expect } from '@playwright/test';

const PROCESS_DOC = [
  'Step 1: Designer submits the product concept to the licensing team.',
  '',
  'Step 2: Licensing reviews the concept against brand guidelines within 5 business days.',
  '',
  'Step 3: If approved, licensing hands off to production planning.',
  '',
  'Step 4: Production planning schedules the manufacturing run.',
  '',
  'Exception: If the concept uses a new material, licensing must also obtain an environmental compliance sign-off before the handoff to production.',
].join('\n');

test.describe('S03 pilot journey', () => {
  test('upload → correction → confirmation → answer after page refresh', async ({ page }) => {
    await page.goto('/consultant');

    // 1. Upload the process document.
    await page.getByTestId('document-text').fill(PROCESS_DOC);
    await page.getByTestId('upload-btn').click();
    await expect(page.getByTestId('source-id')).toBeVisible();
    await expect(page.getByTestId('block-0')).toBeVisible();
    await expect(page.getByTestId('draft-status')).toContainText('draft');

    // 2. Correct one connection (change the from/to step).
    await page.getByTestId('conn-from').selectOption('0');
    await page.getByTestId('conn-to').selectOption('3');
    await page.getByTestId('correct-btn').click();
    await expect(page.getByTestId('draft-status')).toContainText('corrected');

    // 3. Confirm the scoped draft.
    await page.getByTestId('confirm-btn').click();
    await expect(page.getByTestId('draft-status')).toContainText('confirmed');

    // 4. Ask a connected question.
    await page.getByTestId('question-input').fill(
      'Where can the handoff between licensing and production fail?',
    );
    await page.getByTestId('ask-btn').click();
    await expect(page.getByTestId('answer-section')).toBeVisible();
    await expect(page.getByTestId('answer-text')).not.toBeEmpty();
    await expect(page.getByTestId('citations')).toBeVisible();
    await expect(page.getByTestId('hypothetical')).toBeVisible();
    await expect(page.getByTestId('hypothetical')).toContainText('not established fact');

    // 5. Page refresh — the answer is still retrievable.
    await page.reload();
    await expect(page.getByTestId('answer-section')).toBeVisible();
    await expect(page.getByTestId('answer-text')).not.toBeEmpty();
    await expect(page.getByTestId('citations')).toBeVisible();
  });

  test('upload shows missing evidence for unrelated question', async ({ page }) => {
    await page.goto('/consultant');
    await page.getByTestId('document-text').fill('The weather is pleasant today.');
    await page.getByTestId('upload-btn').click();
    await expect(page.getByTestId('source-id')).toBeVisible();
    // Skip correction/confirm and ask directly
    // Confirm first since ask is gated on confirmed state
    await page.getByTestId('confirm-btn').click();
    await expect(page.getByTestId('draft-status')).toContainText('confirmed');
    await page.getByTestId('question-input').fill('What is the licensing approval threshold?');
    await page.getByTestId('ask-btn').click();
    await expect(page.getByTestId('answer-text')).toContainText('No source evidence');
    await expect(page.getByTestId('hypothetical')).not.toBeVisible();
  });
});
