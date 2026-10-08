// Node >=22 built-in WebSocket + installed Chromium; no npm dependencies.
// Start Bureau on the supplied loopback URL with selected evidence and a
// pinned buyer, then run: node tests/browser_smoke.mjs http://127.0.0.1:8766
import {spawn} from 'node:child_process';
import {mkdtemp, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';
const base = new URL(process.argv[2] || 'http://127.0.0.1:8766');
if (!['127.0.0.1', 'localhost'].includes(base.hostname)) throw Error('local fixture only');
const profile = await mkdtemp(join(tmpdir(), 'bureau-ui-'));
const browser = spawn('chromium', ['--headless', '--no-sandbox', '--disable-dev-shm-usage',
  '--disable-gpu', '--disable-background-networking', '--no-proxy-server',
  `--user-data-dir=${profile}`, '--remote-debugging-port=9223', 'about:blank'], {stdio:'ignore'});
let ws;
const deadline = setTimeout(() => { browser.kill('SIGKILL'); process.exitCode = 1; }, 30000);
try {
  let pages;
  for (let i=0;i<50;i++) {
    try { pages = await (await fetch('http://127.0.0.1:9223/json')).json(); break; }
    catch { await new Promise(r=>setTimeout(r,250)); }
  }
  if (!pages?.length) throw Error('Chromium debugging target unavailable');
  ws = new WebSocket(pages[0].webSocketDebuggerUrl);
  await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  let sequence=0;const pending=new Map();
  ws.onmessage=ev=>{const x=JSON.parse(ev.data);if(x.id&&pending.has(x.id)){const [r,j]=pending.get(x.id);pending.delete(x.id);x.error?j(x.error):r(x.result);}};
  const call=(method,params={})=>new Promise((r,j)=>{const id=++sequence;pending.set(id,[r,j]);ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{
    const result=await call('Runtime.evaluate',{expression,returnByValue:true});
    if(result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  await call('Page.enable');await call('Page.navigate',{url:base.href});
  for(let i=0;i<40;i++) {if(await evaluate('document.querySelectorAll(".card").length')===3)break;await new Promise(r=>setTimeout(r,100));}
  if(await evaluate('document.querySelectorAll(".card").length')!==3)throw Error('three candidate cards were not rendered');
  const text=await evaluate('document.body.innerText');
  for(const expected of ['Seller A','Seller B','Seller C','cannot yet be ranked reliably','NOT MEASURABLE'])if(!text.includes(expected))throw Error('missing state: '+expected);
  await evaluate('document.querySelector("dd button").click()');
  await evaluate('document.querySelector("#detail .receipt").click()');
  for(let i=0;i<30;i++){if((await evaluate('document.querySelector("#detail").textContent')).includes('source_repo'))break;await new Promise(r=>setTimeout(r,100));}
  if(!(await evaluate('document.querySelector("#detail").textContent')).includes('source_repo'))throw Error('metric did not open receipt provenance');
  await evaluate('document.querySelector("[data-view=ledger]").click()');
  for(let i=0;i<30;i++){if(await evaluate('document.querySelectorAll("table tr").length')>0)break;await new Promise(r=>setTimeout(r,100));}
  if(await evaluate('document.querySelectorAll("table tr").length')===0)throw Error('receipt ledger did not render');
  console.log('PASS: three workers, unknown history, metric → signed receipt/provenance, existing ledger navigation');
} finally {
  clearTimeout(deadline);ws?.close();
  const exited=once(browser,'exit');browser.kill();await exited;
  await rm(profile,{recursive:true,force:true,maxRetries:5,retryDelay:100});
}
