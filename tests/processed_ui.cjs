// Run: node tests/processed_ui.cjs
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));
 const html=fs.readFileSync('components/meter_setup/web_ui.h','utf8').split('R"HTML(')[1].split(')HTML"')[0];
 await page.goto('about:blank');
 const jpg=Buffer.from(await page.evaluate(()=>{const c=document.createElement('canvas');c.width=640;c.height=480;const x=c.getContext('2d');x.fillStyle='rgb(20,140,220)';x.fillRect(0,0,640,480);return c.toDataURL('image/jpeg',.95).split(',')[1]}),'base64');
 const boxes=Array.from({length:8},(_,i)=>[20+i*35,100,45+i*35,150]),references=[[0,0,0,0],[0,0,0,0]];
 let mode='prepare',calls=0,posts=0;
 const state={digit_count:8,boxes,references,decimals:3,interval:60,max_step:1000,warning_after:300,frame:0,busy:false,paused:true,calibrated:true,preview_available:true,preview_sequence:1,config_revision:0,reset_count:0,alignment_result:'Ausgerichtet',illumination_available:false};
 await page.route('http://meter.test/**',async r=>{
 const u=new URL(r.request().url());
 if(u.pathname==='/setup')return r.fulfill({contentType:'text/html',body:html});
 if(u.pathname==='/meter/status')return r.fulfill({json:state});
 if(u.pathname==='/meter/processed'){
 calls++;
 if(mode==='prepare'){mode='jpeg';return r.fulfill({status:409,headers:{'X-Meter-Preview-State':'preparing'},body:'Vorbereitung'});}
 if(mode==='error')return r.fulfill({status:500,body:'Bildspeicher nicht verfügbar'});
 return r.fulfill({contentType:'image/jpeg',headers:{'X-Meter-Image':String(state.preview_sequence),'X-Meter-Boxes':JSON.stringify(boxes),'X-Meter-References':JSON.stringify(references),'X-Meter-Decimals':'3','X-Meter-Corrected':'1'},body:jpg});
 }
 if(r.request().method()==='POST'){posts++;state.preview_available=true;state.preview_sequence++;return r.fulfill({body:'Test gestartet'});}
 return r.fulfill({status:404,body:'missing'});
 });
 await page.goto('http://meter.test/setup');await page.waitForFunction(()=>loaded);
 await page.selectOption('#view','processed');
 await page.waitForFunction(()=>processedReady);assert(calls>=2);assert.equal(posts,0,'Selecting the view must not trigger a capture');
 assert(await page.evaluate(()=>previewCorrected));
 const pixel=await page.evaluate(()=>Array.from(processedPhoto.getContext('2d').getImageData(200,200,1,1).data));assert(Math.abs(pixel[1]-140)<5);
 mode='error';await page.click('#processed_reload');await page.waitForFunction(()=>previewError.includes('Bildspeicher'));
 const failedCalls=calls;await page.waitForTimeout(2200);assert.equal(calls,failedCalls,'No download retry on every status poll');
 assert((await page.textContent('#processed_status')).includes('Bildspeicher'));
 mode='jpeg';await page.click('#processed_reload');await page.waitForFunction(()=>processedReady&&!previewError);
 state.preview_available=false;state.alignment_result='Referenzen fehlen oder sind nicht eindeutig';await page.waitForFunction(()=>!previewAvailable);
 assert((await page.textContent('#processed_status')).includes('Referenzen fehlen'));assert.equal(await page.textContent('#processed_reload'),'Rahmen testen');
 await page.setViewportSize({width:320,height:800});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.deepEqual(errors,[]);await browser.close();console.log('Processed UI passed: JPEG preparation, rendering, stable errors, reload, absent references, mobile layout');
})().catch(e=>{console.error(e);process.exit(1)});
