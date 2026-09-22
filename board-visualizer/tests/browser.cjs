const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const endpoint = process.env.BOARD_URL || 'http://127.0.0.1:8080';

(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_PATH || '/usr/bin/google-chrome', args:['--no-sandbox']});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(endpoint);
    const snapshot = async () => (await page.request.get(endpoint+'/api/state')).json();
    const control = async (body) => {
      const response = await page.request.post(endpoint+'/api/control',{data:body});
      assert.equal(response.status(),200); return response.json();
    };
    await page.waitForFunction(async()=> { const state=await (await fetch('/api/state')).json(); return state.status==='ready' && state.xvc_connected; },null,{timeout:600000});
    await control({running:false});
    await control({switch:0,value:false});
    await control({button:'btnC',value:true}); await control({step:1}); await control({button:'btnC',value:false});
    await page.waitForFunction(()=>document.querySelector('#led-hex').textContent==='0x0000');
    await page.getByRole('switch',{name:'Switch 0',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#sw-0').getAttribute('aria-checked')==='true');
    await page.getByRole('button',{name:'Step',exact:false}).click();
    await page.waitForFunction(()=>document.querySelector('#led-hex').textContent==='0x0001');
    assert.equal((await snapshot()).leds[0],1);
    const reset = page.getByRole('button',{name:'Center pushbutton'});
    await reset.focus(); await page.keyboard.down('Space');
    await page.waitForFunction(()=>document.querySelector('#btnC').getAttribute('aria-pressed')==='true');
    await control({step:1});
    assert.ok((await snapshot()).leds.every(bit=>bit===0));
    await page.keyboard.up('Space');
    await page.waitForFunction(()=>document.querySelector('#btnC').getAttribute('aria-pressed')==='false');
    await page.getByRole('button',{name:'Run',exact:false}).click();
    const before = (await snapshot()).cycles;
    await page.waitForFunction(async before=>(await (await fetch('/api/state')).json()).cycles>before+4,before);
    await page.getByRole('button',{name:'Pause',exact:false}).click();
    await control({button:'btnC',value:true}); await control({step:1}); await control({button:'btnC',value:false});
    await control({step:90});
    await page.waitForFunction(()=>document.querySelector('#led-hex').textContent==='0x005A');
    assert.equal(await page.locator('.board-led.on').count(),4);
    await page.screenshot({path:'build/board-desktop.png',fullPage:true});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:'build/board-mobile.png',fullPage:true});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
    assert.equal(await page.getByRole('switch').count(),16);
    assert.equal(await page.locator('.board-button').count(),5);
    assert.deepEqual(errors,[]);
    const result = await snapshot();
    assert.equal(result.xvc_connected,true,'Keep hw_server/XVC active for Phase 4 acceptance');
    fs.writeFileSync('build/phase4-acceptance.json',JSON.stringify({status:'PASS',...result,checks:['switch input','single-cycle step','pushbutton hold/release','LED bit pattern','run/pause','desktop/mobile rendering','XVC still connected']},null,2)+'\n');
    console.log('PHASE4_PASS: live board inputs and LEDs verified through browser; XVC connected');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1);});
