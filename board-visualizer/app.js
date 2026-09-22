const $ = (id) => document.getElementById(id);
const positions = [59,83,109,135,161,186,212,237,264,289,315,340,365,391,416,442];
const rates = [1,32,100,256,1000];
let state = null;
let stopped = false;
const activeButtons = new Set();

function place(element, x, y) {
  element.style.left = `${x / 5}%`;
  element.style.top = `${y / 3.13}%`;
}
for (let index = 0; index < 16; index++) {
  const x = positions[15 - index];
  const sw = document.createElement('button');
  sw.className = 'board-switch'; sw.id = `sw-${index}`;
  sw.setAttribute('role', 'switch'); sw.setAttribute('aria-checked', 'false');
  sw.setAttribute('aria-label', `Switch ${index}`); sw.title = `SW${index}`;
  sw.innerHTML = '<span class="switch-thumb"></span>';
  place(sw, x, 276);
  sw.addEventListener('click', () => control({switch:index,value:!state?.switches[index]}));
  $('switch-overlays').appendChild(sw);
  const led = document.createElement('span');
  led.className = 'board-led unknown'; led.id = `led-${index}`;
  led.setAttribute('role', 'img'); led.setAttribute('aria-label', `LED ${index}: unknown`);
  place(led, x + 2, 247);
  $('led-overlays').appendChild(led);
}
const buttonPositions = {btnC:[360,195],btnU:[360,167],btnD:[360,223],btnL:[330,195],btnR:[395,195]};
const buttonLabels = {btnC:'Center',btnU:'Up',btnD:'Down',btnL:'Left',btnR:'Right'};
function release(name) {
  if (activeButtons.delete(name)) control({button:name,value:false});
}
for (const [name, [x,y]] of Object.entries(buttonPositions)) {
  const button = document.createElement('button');
  button.id = name; button.className = 'board-button'; button.title = `${buttonLabels[name]} pushbutton`;
  button.setAttribute('aria-label', `${buttonLabels[name]} pushbutton`); button.setAttribute('aria-pressed', 'false');
  place(button,x,y);
  const press = () => { if (!activeButtons.has(name)) { activeButtons.add(name); control({button:name,value:true}); } };
  button.addEventListener('pointerdown', (event) => { event.preventDefault(); button.focus(); button.setPointerCapture(event.pointerId); press(); });
  ['pointerup','pointercancel','lostpointercapture','blur'].forEach(type => button.addEventListener(type, () => release(name)));
  button.addEventListener('keydown', event => { if ([' ','Enter'].includes(event.key)) { event.preventDefault(); press(); } });
  button.addEventListener('keyup', event => { if ([' ','Enter'].includes(event.key)) { event.preventDefault(); release(name); } });
  $('button-overlays').appendChild(button);
}
window.addEventListener('blur', () => [...activeButtons].forEach(release));
$('run').addEventListener('click', () => control({running:!state?.running}));
$('step').addEventListener('click', () => control({step:1}));
$('rate').addEventListener('input', () => control({rate:rates[Number($('rate').value)]}));

function hex(bits) { return bits.includes(null) ? '0x----' : '0x'+bits.reduce((n,b,i)=>n+(b<<i),0).toString(16).padStart(4,'0').toUpperCase(); }
function render(next) {
  state = next;
  $('connection').textContent = next.xvc_connected ? 'XVC connected' : 'XVC listening';
  $('connection-dot').classList.toggle('live', next.xvc_connected);
  $('endpoint').textContent = next.endpoint;
  $('status').textContent = next.status === 'ready' ? (next.running ? 'RUNNING' : 'PAUSED') : next.status.toUpperCase();
  $('status').className = `status ${next.status}`;
  const descriptions = {
    ready:['Your design is live','Use the board controls to interact with the programmed logic.'],
    programming:['Programming the FPGA','Receiving configuration from Vivado. The board will be ready shortly.'],
    decoding:['Preparing your design','Reconstructing the fabric and connecting its physical inputs and outputs.'],
    error:['Design needs attention','This configuration could not be simulated. Details appear below.'],
    unconfigured:['Ready for your design','Connect Vivado to the XVC target and program an Artix-7 bitstream to begin.']
  };
  [$('design-title').textContent, $('design-description').textContent] = descriptions[next.status] || descriptions.unconfigured;
  $('run').disabled = $('step').disabled = next.status !== 'ready';
  $('run-label').textContent = next.running ? 'Pause' : 'Run';
  $('run-icon').textContent = next.running ? 'Ⅱ' : '▶';
  $('cycles').textContent = next.cycles.toLocaleString(); $('cells').textContent = next.cells || '—';
  $('rate-value').textContent = next.rate;
  if (document.activeElement !== $('rate')) $('rate').value = Math.max(0, rates.indexOf(next.rate));
  $('led-hex').textContent = hex(next.leds); $('switch-hex').textContent = hex(next.switches);
  $('led-bits').textContent = [...next.leds].reverse().map(v=>v===null?'–':v).join('').match(/.{1,4}/g).join(' ');
  next.switches.forEach((value,i) => $(`sw-${i}`).setAttribute('aria-checked', Boolean(value)));
  next.leds.forEach((value,i) => { const led=$(`led-${i}`); led.classList.toggle('on',value===1); led.classList.toggle('unknown',value===null); led.setAttribute('aria-label', `LED ${i}: ${value===null?'unknown':value?'on':'off'}`); });
  Object.entries(next.buttons).forEach(([name,value]) => $(name).setAttribute('aria-pressed', Boolean(value)));
  $('configuration-dot').classList.toggle('live',next.status==='ready');
  $('configuration-text').textContent = next.status==='ready' ? 'Programmed over JTAG' : next.status==='unconfigured' ? 'Waiting for a bitstream' : next.status==='error' ? 'Simulation unavailable' : 'Configuration in progress';
  $('fingerprint').textContent = next.sha256 ? next.sha256.slice(0,12)+'…' : '—';
  $('error').hidden = !next.error; $('error').textContent = next.error || '';
}
let controls = Promise.resolve();
function control(command) {
  // Preserve pointer-down/up and rapid switch changes in order.
  controls = controls.then(async () => {
    const response = await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(command)});
    const data = await response.json(); if (!response.ok) throw new Error(data.error); render(data);
  }).catch(error => { $('error').hidden=false; $('error').textContent=error.message; });
  return controls;
}
async function poll() {
  try { const response=await fetch('/api/state'); if (!response.ok) throw new Error('Connection unavailable'); render(await response.json()); }
  catch { $('connection').textContent='Companion disconnected'; $('connection-dot').classList.remove('live'); $('run').disabled=$('step').disabled=true; }
  if (!stopped) setTimeout(poll,150);
}
window.addEventListener('pagehide',()=>{stopped=true;});
poll();
