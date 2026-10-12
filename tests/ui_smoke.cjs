// Run with Node and Playwright installed: node tests/ui_smoke.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
(async()=>{
 const html=fs.readFileSync(path.join(__dirname,'../components/meter_setup/web_ui.h'),'utf8').split('R"HTML(')[1].split(')HTML"')[0];
 const browser=await chromium.launch({...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:800,height:1000}});
 let confirmReset=false;const errors=[],posts=[],dialogs=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',async d=>{dialogs.push(d.message());if(d.type()==='confirm'&&confirmReset)await d.accept();else await d.dismiss()});
 const state={boxes:Array.from({length:8},()=>[0,0,0,0]),decimals:3,interval:60,max_step:1000,baseline:0,reset_count:0,calibrated:false,busy:false,paused:true,frame:0,digits:'',confidence:0,message:'Noch nicht eingerichtet',illumination_available:true,illumination_led_count:8,illumination_led_capacity:64,illumination_enabled:false,illumination_brightness:30,illumination_settle_ms:1000,illumination_on:false,light_test:false,alignment_enabled:false,references:Array.from({length:2},()=>[0,0,0,0]),reference_ready:false,alignment_ms:0,alignment_result:'Ausgeschaltet'};
 await page.route('http://meter.test/**',async route=>{
  const u=new URL(route.request().url());
  if(u.pathname==='/setup')return route.fulfill({contentType:'text/html',body:html});
  if(u.pathname==='/meter/status')return route.fulfill({contentType:'application/json',body:JSON.stringify(state)});
  if(u.pathname==='/meter/snapshot')return route.fulfill({contentType:'image/svg+xml',headers:{'X-Meter-Frame':String(state.frame)},body:'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480"><rect width="640" height="480" fill="#ccc"/></svg>'});
  posts.push({url:u,headers:route.request().headers()});
  if(u.pathname==='/meter/light_on'){state.light_test=state.illumination_on=true;}
  if(u.pathname==='/meter/light_off'){state.light_test=state.illumination_on=false;}
  if(u.pathname==='/meter/light_save'){state.illumination_led_count=+u.searchParams.get('led_count');state.illumination_enabled=u.searchParams.get('enabled')==='1';state.illumination_brightness=+u.searchParams.get('brightness');state.illumination_settle_ms=+u.searchParams.get('settle_ms');}
  if(u.pathname==='/meter/reference'){state.reference_ready=true;state.references=Array.from({length:2},(_,i)=>u.searchParams.get('references').split(',').slice(i*4,i*4+4).map(Number));state.message='Referenzen vorbereitet'}
  if(u.pathname==='/meter/capture')state.frame++;
  if(u.pathname==='/meter/reset'){state.reset_count++;state.boxes=Array.from({length:8},()=>[0,0,0,0]);state.digits='';state.calibrated=false;state.message='Zählerkonfiguration gelöscht'}
  return route.fulfill({status:200,body:'Aktion vorgemerkt'});
 });
 await page.goto('http://meter.test/setup');await page.waitForFunction(()=>document.getElementById('message').textContent.includes('Noch nicht'));
 await page.click('#capture');await page.waitForFunction(()=>ready);
 let bounds=await page.locator('#image').boundingBox();
 const xy=(x,y)=>[bounds.x+x*bounds.width/640,bounds.y+y*bounds.height/480];
 await page.mouse.move(...xy(40,100));await page.mouse.down();await page.mouse.move(...xy(600,170));await page.mouse.up();await page.click('#split');
 const boxes=await page.evaluate(()=>boxes);assert.equal(boxes.length,8);assert.deepEqual(boxes[0],[41,100,109,170]);assert.deepEqual(boxes[7],[531,100,599,170]);
 await page.click('#test');await page.waitForTimeout(100);const test=posts.find(p=>p.url.pathname==='/meter/test');assert(test);assert.equal(test.url.searchParams.get('boxes').split(',').length,32);assert.equal(test.headers['x-meter-setup'],'1');assert.deepEqual(dialogs,[], 'Accepted test commands must not show an error dialog');
 await page.click('#save');assert(dialogs.some(s=>s.includes('8 Ziffern')));assert(!posts.some(p=>p.url.pathname==='/meter/save'));
 await page.fill('#baseline','00123456');await page.click('#save');await page.waitForTimeout(100);assert.equal(posts.find(p=>p.url.pathname==='/meter/save').url.searchParams.get('baseline'),'00123456');
 await page.locator('#image').scrollIntoViewIfNeeded();bounds=await page.locator('#image').boundingBox();await page.selectOption('#digit','7');await page.selectOption('#tool','move');await page.locator('#image').scrollIntoViewIfNeeded();bounds=await page.locator('#image').boundingBox();await page.mouse.move(...xy(560,130));await page.mouse.down();await page.mouse.move(...xy(630,150));await page.mouse.up();const moved=await page.evaluate(()=>boxes[7]);assert.equal(moved[2],640);assert.equal(moved[3]-moved[1],70);
 await page.click('[data-adjust="left"]');assert.equal((await page.evaluate(()=>boxes[7]))[0],moved[0]-1);
 await page.selectOption('#step','5');await page.click('[data-adjust="narrow"]');assert.equal((await page.evaluate(()=>boxes[7]))[2]-(await page.evaluate(()=>boxes[7]))[0],moved[2]-moved[0]-5);
 await page.fill('#box_x','500');await page.locator('#box_x').press('Tab');assert.equal((await page.evaluate(()=>boxes[7]))[0],500);
 await page.locator('#image').focus();await page.keyboard.press('ArrowLeft');assert.equal((await page.evaluate(()=>boxes[7]))[0],499);
 await page.keyboard.press('Shift+ArrowUp');assert.equal((await page.evaluate(()=>boxes[7]))[1],moved[1]-10);
 await page.fill('#led_count','6');await page.check('#led_enabled');await page.locator('#led_brightness').fill('45');await page.fill('#led_settle','1500');await page.click('#light_on');await page.waitForFunction(()=>document.getElementById('light_info').textContent.includes('aktiv'));const light=posts.find(p=>p.url.pathname==='/meter/light_on');assert.equal(light.url.searchParams.get('led_count'),'6');assert.equal(light.url.searchParams.get('brightness'),'45');assert.equal(light.url.searchParams.get('settle_ms'),'1500');await page.click('#light_save');await page.waitForTimeout(100);assert(posts.some(p=>p.url.pathname==='/meter/light_save'));await page.click('#light_off');
 await page.check('#alignment');await page.selectOption('#digit','8');await page.selectOption('#tool','draw');await page.locator('#image').scrollIntoViewIfNeeded();bounds=await page.locator('#image').boundingBox();
 await page.mouse.move(...xy(100,250));await page.mouse.down();await page.mouse.move(...xy(132,282));await page.mouse.up();await page.selectOption('#digit','9');await page.mouse.move(...xy(450,250));await page.mouse.down();await page.mouse.move(...xy(482,282));await page.mouse.up();
 assert.deepEqual(await page.evaluate(()=>references),[[100,250,132,282],[450,250,482,282]]);await page.click('#reference');await page.waitForFunction(()=>document.getElementById('reference_state').textContent.includes('aufgenommen'));const ref=posts.find(p=>p.url.pathname==='/meter/reference');assert.equal(ref.url.searchParams.get('frame'),'1');
 await page.click('#save');await page.waitForTimeout(100);assert.equal(posts.filter(p=>p.url.pathname==='/meter/save').at(-1).url.searchParams.get('alignment'),'1');await page.uncheck('#alignment');assert.equal(await page.inputValue('#digit'),'0');await page.click('#test');await page.waitForTimeout(100);assert.equal(posts.filter(p=>p.url.pathname==='/meter/test').at(-1).url.searchParams.get('alignment'),'0');
 await page.setViewportSize({width:1440,height:1000});
 const sidebar=await page.locator('.sidebar').boundingBox(),workspace=await page.locator('.workspace').boundingBox();
 assert(sidebar.x+sidebar.width<workspace.x,'Desktop settings must be left of camera');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.locator('.sidebar').evaluate(el=>el.scrollTop=el.scrollHeight);
 const stableCamera=await page.locator('#image').boundingBox();
 assert(stableCamera.y>=0&&stableCamera.y+stableCamera.height<=1000,'Camera stays visible while settings scroll');
 const cameraWrap=await page.locator('.camera-wrap').boundingBox();assert(Math.abs(stableCamera.width-cameraWrap.width)<1,'Camera uses full workspace width');
 assert(Math.abs(stableCamera.width/stableCamera.height-4/3)<0.01,'Larger camera preserves aspect ratio');
 await page.locator('.sidebar').evaluate(el=>el.scrollTop=0);
 await page.click('.crop:nth-child(3)');assert.equal(await page.inputValue('#digit'),'2');
 if(process.env.UI_SCREENSHOTS){await page.screenshot({path:'/tmp/water-setup-desktop.png',fullPage:true});}
 state.busy=true;await page.waitForFunction(()=>document.getElementById('reset').disabled);assert.equal(await page.locator('#restart').isEnabled(),true);confirmReset=true;await page.click('#restart');await page.waitForTimeout(100);assert(posts.some(p=>p.url.pathname==='/meter/restart'));confirmReset=false;state.busy=false;await page.waitForFunction(()=>!document.getElementById('reset').disabled);
 await page.click('#reset');assert(!posts.some(p=>p.url.pathname==='/meter/reset'));confirmReset=true;
 await page.click('#reset');await page.waitForFunction(()=>boxes.every(b=>b.every(v=>v===0)));assert(posts.some(p=>p.url.pathname==='/meter/reset'));assert.equal(await page.inputValue('#baseline'),'');
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 if(process.env.UI_SCREENSHOTS)await page.screenshot({path:'/tmp/water-setup-mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);await browser.close();console.log('UI smoke tests passed: scaled ROI drawing, split, move/clamp, test, baseline/save, pixel adjustments, keyboard, confirmed reset, mobile layout');
})().catch(e=>{console.error(e);process.exit(1)});
