import { test,expect } from '@playwright/test';
import { readFileSync,writeFileSync } from 'node:fs';
import { createHash,randomBytes } from 'node:crypto';
import { gzipSync } from 'node:zlib';
test('invented authenticated map traverses real current worker SDK and ledger',async({page})=>{
  const url=process.env.ORACLE2_PREVIEW_URL!;
  const anonymous=await page.request.get(`${url}/api/consultant/source`);expect(anonymous.status()).toBe(401);
  await page.goto(`${url}/consultant/operating-model`);
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByLabel('Access token').fill(process.env.ORACLE2_PILOT_TOKEN!);
  await page.getByRole('button',{name:'Connect',exact:true}).click();
  await expect(page.getByRole('img',{name:'Reported workflow Invented intake'})).toBeVisible({timeout:30000});
  await expect(page.getByText('Approval owner is missing.',{exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Download corresponding source (AGPL)'})).toHaveAttribute('href','/api/consultant/source');
  const download=await page.request.get(`${url}/api/consultant/source`);expect(download.ok()).toBeTruthy();
  const archive=await download.body();const manifest=JSON.parse(readFileSync('.source-offer/manifest.json','utf8'));
  expect(createHash('sha256').update(archive).digest('hex')).toBe(manifest.archive_sha256);
  expect(download.headers()['x-oracle-source-revision']).toBe(manifest.revision);expect(archive.subarray(0,2).toString('hex')).toBe('1f8b');
  const metadata=await page.request.get(`${url}/api/consultant/source?metadata=1`);expect(metadata.ok()).toBeTruthy();
  const descriptor=await metadata.json();expect(descriptor.bytes).toBe(archive.length);expect(descriptor.sha256).toBe(manifest.archive_sha256);
  expect((await page.request.get(`${url}/api/consultant/source`,{headers:{Range:'bytes=0-10','If-Match':'"'+'0'.repeat(64)+'"'}})).status()).toBe(412);
  expect((await page.request.get(`${url}/api/consultant/source`,{headers:{Range:'bytes=0-1048576','If-Match':`"${descriptor.sha256}"`}})).status()).toBe(416);
  const [delivered]=await Promise.all([page.waitForEvent('download'),page.getByRole('link',{name:'Download corresponding source (AGPL)'}).click()]);
  expect(createHash('sha256').update(readFileSync((await delivered.path())!)).digest('hex')).toBe(manifest.archive_sha256);
  // Oversized invented transfer fixture proves native deployed route/chunk client,
  // never a licensed-source or company-evidence acceptance claim. Restore before exit.
  const manifestBytes=readFileSync('.source-offer/manifest.json');
  const oversized=gzipSync(randomBytes(5*1024*1024));
  const oversizedHash=createHash('sha256').update(oversized).digest('hex');
  try{
    writeFileSync('.source-offer/oracle-source.tar.gz',oversized);
    writeFileSync('.source-offer/manifest.json',JSON.stringify({...manifest,archive_sha256:oversizedHash}));
    expect((await page.request.get(`${url}/api/consultant/source`)).status()).toBe(413);
    const [largeDownload]=await Promise.all([page.waitForEvent('download'),page.getByRole('link',{name:'Download corresponding source (AGPL)'}).click()]);
    expect(createHash('sha256').update(readFileSync((await largeDownload.path())!)).digest('hex')).toBe(oversizedHash);
  }finally{writeFileSync('.source-offer/oracle-source.tar.gz',archive);writeFileSync('.source-offer/manifest.json',manifestBytes);}
  await page.getByText('Source support',{exact:true}).click();
  await expect(page.getByText('Intake sends packet to Review.',{exact:true})).toBeVisible();
  await page.getByLabel('Process',{exact:true}).selectOption('intake');
  await expect(page.getByRole('img',{name:'Reported workflow Invented intake'})).toBeVisible({timeout:30000});
  if(process.env.ORACLE2_WORKFLOW_SCREENSHOT)await page.screenshot({path:process.env.ORACLE2_WORKFLOW_SCREENSHOT,fullPage:true});
  const logout=await page.request.delete(`${url}/api/consultant/session`);expect(logout.ok()).toBeTruthy();
  await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByRole('img',{name:'Reported workflow Invented intake'})).toHaveCount(0);
  expect((await page.request.get(`${url}/api/consultant/source`)).status()).toBe(401);
});
