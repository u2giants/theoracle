import { test,expect } from '@playwright/test';
test('invented authenticated map traverses real current worker SDK and ledger',async({page})=>{
  const url=process.env.ORACLE2_PREVIEW_URL!;
  await page.goto(`${url}/consultant/operating-model`);
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByLabel('Access token').fill(process.env.ORACLE2_PILOT_TOKEN!);
  await page.getByRole('button',{name:'Connect',exact:true}).click();
  await expect(page.getByRole('img',{name:'Reported workflow Invented intake'})).toBeVisible({timeout:30000});
  await expect(page.getByText('Approval owner is missing.',{exact:true})).toBeVisible();
  await page.getByText('Source support',{exact:true}).click();
  await expect(page.getByText('Intake sends packet to Review.',{exact:true})).toBeVisible();
  await page.getByLabel('Process',{exact:true}).selectOption('intake');
  await expect(page.getByRole('img',{name:'Reported workflow Invented intake'})).toBeVisible({timeout:30000});
  if(process.env.ORACLE2_WORKFLOW_SCREENSHOT)await page.screenshot({path:process.env.ORACLE2_WORKFLOW_SCREENSHOT,fullPage:true});
  const logout=await page.request.delete(`${url}/api/consultant/session`);expect(logout.ok()).toBeTruthy();
  await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByRole('img',{name:'Reported workflow Invented intake'})).toHaveCount(0);
});
