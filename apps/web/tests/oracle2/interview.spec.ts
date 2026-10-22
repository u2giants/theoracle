// Real installed acceptance journeys. No page-ready flags, URL-only assertions,
// synthetic SourceRefs or fixture self-appointment. The authenticated configured
// browser must have its separately installed own conversation admission.
import {test,expect} from '@playwright/test';
test('pause, refresh and resume retain the saved question and original wording',async({page})=>{
 await page.goto('/consultant/interviews');await page.getByLabel('Topic',{exact:true}).fill('Acceptance interview');
 await page.getByRole('button',{name:'Start an interview (up to 8 questions)',exact:true}).click();
 await expect(page.getByTestId('interview-question')).toBeVisible();
 await page.getByLabel('Your response or direct question',{exact:true}).fill('Only samples require this second check.');
 await page.getByRole('button',{name:'Send response',exact:true}).click();
 await expect(page.locator('ol').getByText('Only samples require this second check.',{exact:true})).toBeVisible();
 const question=await page.getByTestId('interview-question').textContent();
 await page.getByRole('button',{name:'Pause',exact:true}).click();await expect(page.getByRole('button',{name:'Resume',exact:true})).toBeVisible();
 await page.reload();await page.getByRole('button',{name:'Resume',exact:true}).click();
 await expect(page.getByTestId('interview-question')).toHaveText(question!);
 await expect(page.locator('ol').getByText('Only samples require this second check.',{exact:true})).toHaveCount(1);
});
test('correction preserves both originals and exact account review excludes company approval',async({page})=>{
 await page.goto('/consultant/interviews');await page.getByLabel('Topic',{exact:true}).fill('Acceptance correction');
 await page.getByRole('button',{name:'Start ordinary chat',exact:true}).click();
 await page.getByLabel('Your response or direct question',{exact:true}).fill('不允许未经复核就发货。仅限样品。');
 await page.getByRole('button',{name:'Send response',exact:true}).click();await expect(page.locator('ol').getByText('不允许未经复核就发货。仅限样品。',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Correct this response',exact:true}).click();await page.getByRole('textbox',{name:/Your corrected original response/}).fill('样品也必须复核。');
 await page.getByRole('button',{name:'Save correction',exact:true}).click();await expect(page.locator('ol').getByText('样品也必须复核。',{exact:true})).toBeVisible();
 await expect(page.locator('ol').getByText('不允许未经复核就发货。仅限样品。',{exact:true})).toHaveCount(1);
 await page.getByRole('button',{name:'Review recap',exact:true}).click();await page.getByRole('button',{name:'I reviewed this exact account',exact:true}).click();
 await expect(page.getByText('Your earlier account review is retained. It does not approve company policy.',{exact:true})).toBeVisible();
});
