// Exercise the buttons alongside the generated standard ESPHome root page.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
const {chromium} = require('playwright');
(async()=>{
 const root=path.join(__dirname,'..');
 const main=fs.readFileSync(path.join(root,'.esphome/build/wasserzaehler/src/main.cpp'),'utf8');
 const resource=name=>{const match=main.match(new RegExp('ESPHOME_WEBSERVER_'+name+'\\[\\d+\\] PROGMEM = \\{([^}]+)\\}'));assert(match, 'Generate the ESPHome source first');return Buffer.from(match[1].split(',').map(Number))};
 const html=resource('INDEX_HTML').toString();
 const script=zlib.gunzipSync(resource('JS_INCLUDE')).toString();
 assert(html.includes('src=/0.js'));
 assert(html.includes('<esp-app>'));
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:390,height:844}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',async route=>{
  const u=new URL(route.request().url());
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:html});
  if(u.pathname==='/0.js')return route.fulfill({contentType:'text/javascript',body:script});
  return route.fulfill({contentType:'text/javascript',body:"customElements.define('esp-app',class extends HTMLElement{connectedCallback(){this.attachShadow({mode:'open'}).innerHTML='<p>ESPHome sensors</p>'}})"});
 });
 await page.goto('http://meter.test/');
 await page.waitForSelector('#meter-navigation');
 assert.equal(await page.locator('#meter-navigation a').count(),2);
 assert.equal(await page.getByRole('link',{name:'Wasserzähler einrichten'}).getAttribute('href'),'/setup');
 assert.equal(await page.getByRole('link',{name:'Status / Diagnose'}).getAttribute('href'),'/meter/status');
 assert(await page.locator('esp-app').isVisible());
 assert(await page.getByRole('link',{name:'Wasserzähler einrichten'}).isVisible());
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.addScriptTag({content:script});
 assert.equal(await page.locator('#meter-navigation').count(),1);
 assert.deepEqual(errors,[]);
 await browser.close();
 console.log('Navigation tests passed: generated index, both links, standard app, mobile layout, no duplicates');
})().catch(e=>{console.error(e);process.exit(1)});
