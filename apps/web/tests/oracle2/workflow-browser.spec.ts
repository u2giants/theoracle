import { test,expect } from '@playwright/test';
import { readFileSync,writeFileSync } from 'node:fs';
import { createHash,randomBytes } from 'node:crypto';
import { gzipSync } from 'node:zlib';
// Authenticated fixture requests use the real browser cookie transport. The
// pinned Playwright API client omits Secure cookies on HTTP loopback.
async function browserRequest(page: import('@playwright/test').Page, url: string,
  options: { method?: string; data?: unknown; headers?: Record<string, string> } = {}) {
  const result = await page.evaluate(async ({ url, options }) => {
    const headers = { ...options.headers };
    let body: string | undefined;
    if (options.data !== undefined) {
      headers['Content-Type'] = 'application/json';
      body = typeof options.data === 'string' ? options.data : JSON.stringify(options.data);
    }
    const response = await fetch(url, { method: options.method ?? 'GET',
      credentials: 'same-origin', headers, body });
    return { status: response.status, headers: Object.fromEntries(response.headers),
      bytes: Array.from(new Uint8Array(await response.arrayBuffer())) };
  }, { url, options });
  const body = Buffer.from(result.bytes);
  return { status: () => result.status, ok: () => result.status >= 200 && result.status < 300,
    headers: () => result.headers, body: async () => body,
    json: async () => JSON.parse(body.toString('utf8')) };
}
test('invented authenticated map traverses real current worker SDK and ledger',async({page})=>{
  const url=process.env.ORACLE2_PREVIEW_URL!;
  const anonymous=await page.request.get(`${url}/api/consultant/source`);expect(anonymous.status()).toBe(401);
  await page.goto(`${url}/consultant/operating-model`);
  await expect(page.getByRole('alert')).toBeVisible();
  await page.getByLabel('Access token').fill(process.env.ORACLE2_PILOT_TOKEN!);
  await page.getByRole('button',{name:'Connect',exact:true}).click();
  await expect(page.getByRole('img',{name:'Reported workflow Invented intake'})).toBeVisible({timeout:30000});
  const oversizedEvent=await browserRequest(page,`${url}/api/consultant/processes/intake/events`,{method:'POST',data:JSON.stringify({format:'csv',window_start:'2026-01-01T00:00:00Z',window_end:'2026-01-02T00:00:00Z',mapping:{process_id:'intake',scope:'intake',timezone_name:'UTC'},raw_export_base64:'A'.repeat(4*1024*1024)})});
  expect(oversizedEvent.status()).toBe(413);
  await expect(page.getByText('Approval owner is missing.',{exact:true})).toBeVisible();
  const imported=await browserRequest(page,`${url}/api/consultant/processes/intake/events`,{method:'POST',data:JSON.parse(process.env.ORACLE2_EVENT_FIXTURE!)});
  expect(imported.status()).toBe(202);const importJob=await imported.json();
  await expect.poll(async()=>{const r=await browserRequest(page,`${url}/api/consultant/processes/intake/events?runId=${importJob.runId}`);return (await r.json()).state;},{timeout:30000}).toBe('completed');
  const importResult=await (await browserRequest(page,`${url}/api/consultant/processes/intake/events?runId=${importJob.runId}`)).json();
  expect(importResult.accepted_count).toBe(1);expect(importResult.actual_data_acceptance).toBe('unavailable');

  await expect(page.getByText('Unverified review material; it is not a fact.',{exact:true})).toBeVisible();
  await expect(page.getByText('Unverified legacy licensor concern',{exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'Download corresponding source (AGPL)'})).toHaveAttribute('href','/api/consultant/source');
  const download=await browserRequest(page,`${url}/api/consultant/source`);expect(download.ok()).toBeTruthy();
  const archive=await download.body();const manifest=JSON.parse(readFileSync('.source-offer/manifest.json','utf8'));
  expect(createHash('sha256').update(archive).digest('hex')).toBe(manifest.archive_sha256);
  expect(download.headers()['x-oracle-source-revision']).toBe(manifest.revision);expect(archive.subarray(0,2).toString('hex')).toBe('1f8b');
  const metadata=await browserRequest(page,`${url}/api/consultant/source?metadata=1`);expect(metadata.ok()).toBeTruthy();
  const descriptor=await metadata.json();expect(descriptor.bytes).toBe(archive.length);expect(descriptor.sha256).toBe(manifest.archive_sha256);
  expect((await browserRequest(page,`${url}/api/consultant/source`,{headers:{Range:'bytes=0-10','If-Match':'"'+'0'.repeat(64)+'"'}})).status()).toBe(412);
  expect((await browserRequest(page,`${url}/api/consultant/source`,{headers:{Range:'bytes=0-1048576','If-Match':`"${descriptor.sha256}"`}})).status()).toBe(416);
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
    expect((await browserRequest(page,`${url}/api/consultant/source`)).status()).toBe(413);
    const [largeDownload]=await Promise.all([page.waitForEvent('download'),page.getByRole('link',{name:'Download corresponding source (AGPL)'}).click()]);
    expect(createHash('sha256').update(readFileSync((await largeDownload.path())!)).digest('hex')).toBe(oversizedHash);
  }finally{writeFileSync('.source-offer/oracle-source.tar.gz',archive);writeFileSync('.source-offer/manifest.json',manifestBytes);}
  const sourceSupport=page.locator('details').filter({has:page.locator('blockquote').filter({hasText:/^Intake sends packet to Review\.$/})}).first();
  await sourceSupport.getByText('Source support',{exact:true}).click();
  await expect(sourceSupport.locator('blockquote')).toBeVisible();
  await page.getByLabel('Process',{exact:true}).selectOption('intake');
  await expect(page.getByRole('img',{name:'Reported workflow Invented intake'})).toBeVisible({timeout:30000});
  await page.getByRole('button',{name:'Show connected processes'}).click();
  await expect(page.getByText('Two connected invented processes',{exact:false})).toBeVisible({timeout:30000});
  await expect(page.getByText('Process handoffs',{exact:true})).toBeVisible();
  const review=await browserRequest(page,`${url}/api/consultant/reviews/missing-owner`,{method:'POST',data:{action:'finding_annotate',scope:'intake',note:'Invented reviewer requests an owner; no policy approval.'}});
  expect(review.status()).toBe(202);
  const reviewJob=await review.json();
  await expect.poll(async()=>{const r=await browserRequest(page,`${url}/api/consultant/reviews/missing-owner?runId=${reviewJob.runId}`);return (await r.json()).state;},{timeout:30000}).toBe('completed');
  const reviewResult=await (await browserRequest(page,`${url}/api/consultant/reviews/missing-owner?runId=${reviewJob.runId}`)).json();
  expect(reviewResult.policy_promoted).toBe(false);
  await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await expect(page.getByText('Invented reviewer requests an owner; no policy approval.',{exact:true})).toBeVisible({timeout:30000});
  await expect(page.getByText('Invented event preview only. Actual company measurements remain unavailable.',{exact:true})).toBeVisible();
  await expect(page.getByText('Review decisions do not establish company policy.',{exact:true})).toBeVisible();
  if(process.env.ORACLE2_WORKFLOW_SCREENSHOT)await page.screenshot({path:process.env.ORACLE2_WORKFLOW_SCREENSHOT,fullPage:true});
  const logout=await browserRequest(page,`${url}/api/consultant/session`,{method:'DELETE'});expect(logout.ok()).toBeTruthy();
  await page.getByRole('button',{name:'Refresh',exact:true}).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect(page.getByRole('img',{name:'Reported workflow Invented intake'})).toHaveCount(0);
  expect((await browserRequest(page,`${url}/api/consultant/source`)).status()).toBe(401);
});
