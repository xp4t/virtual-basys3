const {chromium} = require('playwright');
const assert = require('node:assert/strict');

const endpoint = process.env.BOARD_URL || 'http://127.0.0.1:8080';

(async () => {
  const browser = await chromium.launch({headless:true,
    executablePath:process.env.CHROME_PATH || '/usr/bin/google-chrome',
    args:['--no-sandbox']});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1050}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(endpoint);
    await page.waitForFunction(async () =>
      (await (await fetch('/api/state')).json()).status === 'ready', null, {timeout:600000});
    const defaultProbes = Array.from({length:8}, (_, index) => `pin:led[${index}]`);
    const reset = await page.request.post(endpoint+'/api/logic', {data:{action:'configure',
      probes:defaultProbes, depth:16, trigger:{mode:'immediate'}}});
    assert.equal(reset.status(),200);
    await page.reload();
    await page.waitForFunction(() =>
      document.querySelector('#logic-probe-count')?.textContent?.startsWith('8 / 16'));
    if ((await page.locator('#run-label').textContent()).trim() === 'Pause') {
      await page.locator('#run').click();
    }
    await page.locator('#vio-word').fill('0x0001');
    await page.locator('#vio-apply').click();
    await page.waitForFunction(() => document.querySelector('#sw-0').getAttribute('aria-checked') === 'true');
    await page.locator('#logic-depth').selectOption('16');
    await page.locator('#logic-capture').click();
    await page.waitForFunction(async () =>
      (await (await fetch('/api/logic')).json()).phase === 'complete');
    const data = await (await page.request.get(endpoint+'/api/logic')).json();
    assert.equal(data.samples.length,16);
    assert.equal(data.probes.length,8);
    await page.waitForFunction(() => document.querySelectorAll('#logic-waveform svg path').length >= 8);
    assert.ok(await page.locator('#logic-waveform svg path').count() >= 8);
    const csv = await (await page.request.get(endpoint+'/api/logic.csv')).text();
    assert.equal(csv.trim().split(/\r?\n/).length,17);
    await page.locator('#logic-probe-search').fill('FDRE');
    await page.locator('#logic-search-results button').first().click();
    await page.waitForFunction(() => document.querySelector('#logic-probe-count').textContent.startsWith('9 / 16'));
    await page.locator('#logic-trigger-mode').selectOption('rising');
    await page.locator('#logic-trigger-probe').selectOption('pin:led[0]');
    await page.locator('#logic-arm').click();
    await page.waitForFunction(async () =>
      (await (await fetch('/api/logic')).json()).phase === 'waiting');
    await page.evaluate(() => window.boardControl({step:32}));
    await page.waitForFunction(async () =>
      (await (await fetch('/api/logic')).json()).phase === 'complete');
    const triggered = await (await page.request.get(endpoint+'/api/logic')).json();
    assert.ok(triggered.trigger_index > 0);
    assert.equal(triggered.samples[triggered.trigger_index].values[0],1);
    await page.screenshot({path:'build/local-logic-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:'build/local-logic-mobile.png',fullPage:true});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
    assert.deepEqual(errors,[]);
    console.log('LOCAL_LOGIC_BROWSER_PASS: VIO word, probe search, 16-sample waveform, rising trigger, CSV, mobile layout');
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exit(1);});
