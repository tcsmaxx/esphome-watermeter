// Run with Node and Playwright installed: node tests/ui_smoke.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');
(async()=>{
 const html=fs.readFileSync(path.join(__dirname,'../components/meter_setup/web_ui.h'),'utf8').split('R"HTML(')[1].split(')HTML"')[0];
 const browser=await chromium.launch({...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:800,height:1000}});
 let rejectSave=null;let snapshotDelay=1600,captureBusyReplies=0,statusRequests=0;let captureDelay=0;let rawPreview=null;let confirmReset=false;const errors=[],posts=[],dialogs=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',async d=>{dialogs.push(d.message());if(d.type()==='confirm'&&confirmReset)await d.accept();else await d.dismiss()});
 const state={digit_count:8,rotation_tenths:0,camera_standby_available:true,camera_standby_enabled:true,camera_weak_drive:false,camera_power_status:'Sensor im Software-Standby',autofocus_available:true,autofocus_before_reading:true,autofocus_status:'Bereit · noch nicht fokussiert',autofocus_error:0,boxes:Array.from({length:8},()=>[0,0,0,0]),decimals:3,interval:60,max_step:1000,baseline:0,reset_count:0,calibrated:false,busy:false,paused:true,frame:7,digits:'',confidence:0,message:'Noch nicht eingerichtet',illumination_available:true,illumination_led_count:8,illumination_led_capacity:64,illumination_enabled:false,illumination_brightness:30,illumination_settle_ms:1000,illumination_on:false,light_test:false,alignment_enabled:false,references:Array.from({length:2},()=>[0,0,0,0]),reference_ready:false,alignment_ms:0,alignment_result:'Ausgeschaltet',preview_available:false,preview_sequence:0,preview_corrected:false,warning_after:300,config_revision:0,reading_age:null,stale:false,digit_confidences:[]};
 await page.route('http://meter.test/**',async route=>{
  const wireURL=new URL(route.request().url()),u=new URL(wireURL);
  if(route.request().method()==='POST'&&route.request().postData()&&u.pathname!=='/meter/import'){
   assert.equal(wireURL.search,'','Setup writes must not put settings in the URL');
   assert.equal(route.request().headers()['content-type'],'application/x-www-form-urlencoded');
   assert(Buffer.byteLength(route.request().postData())<=1024,'ESPHome form body limit');
   for(const [key,value] of new URLSearchParams(route.request().postData()))u.searchParams.set(key,value);
  }
  if(u.pathname==='/setup')return route.fulfill({contentType:'text/html',body:html});
  if(u.pathname==='/meter/export')return route.fulfill({contentType:'application/json',body:JSON.stringify({format:'esphome-watermeter',version:1,settings:{interval:120},warning_after:600})});
  if(u.pathname==='/meter/status'){++statusRequests;return route.fulfill({contentType:'application/json',body:JSON.stringify(state)});}
  if(u.pathname==='/meter/processed'){if(!state.preview_corrected&&rawPreview)return route.fulfill({contentType:'image/jpeg',headers:{'X-Meter-Image':String(state.preview_sequence),'X-Meter-Boxes':JSON.stringify(state.boxes),'X-Meter-References':JSON.stringify(state.references)},body:rawPreview});const pixels=Buffer.alloc(640*480*3);for(let i=0;i<pixels.length;i+=3){pixels[i]=20;pixels[i+1]=140;pixels[i+2]=220;}return route.fulfill({contentType:'application/octet-stream',headers:{'X-Meter-Image':String(state.preview_sequence),'X-Meter-Boxes':JSON.stringify(state.boxes),'X-Meter-References':JSON.stringify(state.references)},body:pixels});}
  if(u.pathname==='/meter/snapshot'){const snapshotFrame=state.frame;if(snapshotDelay)await new Promise(r=>setTimeout(r,snapshotDelay));return route.fulfill({contentType:'image/svg+xml',headers:{'X-Meter-Frame':String(snapshotFrame)},body:'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480"><rect width="640" height="480" fill="#ccc"/></svg>'});}
  posts.push({url:u,wireURL,headers:route.request().headers()});
  if(u.pathname==='/meter/save_all'&&rejectSave)return route.fulfill({status:rejectSave.status,body:rejectSave.body});
  if(u.pathname==='/meter/preview'&&captureBusyReplies>0){--captureBusyReplies;state.busy=true;state.reader_phase='autofocus';setTimeout(()=>{state.busy=false;state.reader_phase='idle'},1700);return route.fulfill({status:409,body:'Bitte laufende Aktion abwarten'});}
  if(u.pathname==='/meter/import'){const incoming=JSON.parse(new URLSearchParams(route.request().postData()).get('data'));state.interval=incoming.settings.interval;state.warning_after=incoming.warning_after;state.config_revision++;state.message='Sicherung importiert; Automatik pausiert';state.paused=true;}
  if(u.pathname==='/meter/light_on'){state.light_test=state.illumination_on=true;}
  if(u.pathname==='/meter/light_off'){state.light_test=state.illumination_on=false;}
  if(u.pathname==='/meter/power_save'){state.camera_standby_enabled=u.searchParams.get('standby')==='1';state.camera_weak_drive=u.searchParams.get('weak_drive')==='1';}
  if(u.pathname==='/meter/focus_save'){state.autofocus_before_reading=u.searchParams.get('enabled')==='1';state.manual_focus_enabled=u.searchParams.get('manual')==='1';state.manual_focus_position=Number(u.searchParams.get('position'));}
  if(u.pathname==='/meter/focus_only'){state.manual_focus_applied=Number(u.searchParams.get('position'));}
  if(u.pathname==='/meter/manual_focus'){state.manual_focus_applied=Number(u.searchParams.get('position'));state.frame++;}
  if(u.pathname==='/meter/focus'){state.autofocus_status='Fokus gefunden';state.frame++;}
  if(u.pathname==='/meter/light_save'){state.illumination_led_count=+u.searchParams.get('led_count');state.illumination_enabled=u.searchParams.get('enabled')==='1';state.illumination_brightness=+u.searchParams.get('brightness');state.illumination_settle_ms=+u.searchParams.get('settle_ms');}
  if(u.pathname==='/meter/reference'){state.reference_ready=true;state.references=Array.from({length:2},(_,i)=>u.searchParams.get('references').split(',').slice(i*4,i*4+4).map(Number));state.message='Referenzen vorbereitet'}
  if(u.pathname==='/meter/live_start'){state.live=true;state.live_remaining=120;state.frame++;}
  if(u.pathname==='/meter/live_stop'){state.live=false;state.message='Livebild beendet';}
  if(u.pathname==='/meter/preview'){if(captureDelay)await new Promise(r=>setTimeout(r,captureDelay));state.frame++;state.message='Kamerabild aufgenommen';state.autofocus_status=u.searchParams.get('focus_mode')==='manual'?'Manuell eingestellt':'Fokus gefunden';}
  if(u.pathname==='/meter/save_all'){
   state.rotation_tenths=Number(u.searchParams.get('rotation'));state.save_attempt=(state.save_attempt||0)+1;state.save_ok=true;state.config_revision++;state.alignment_enabled=u.searchParams.get('alignment')==='1';
   if(state.digit_count!==Number(u.searchParams.get('digit_count')))state.digits='';state.digit_count=Number(u.searchParams.get('digit_count'));state.decimals=Number(u.searchParams.get('decimals'));
   state.boxes=Array.from({length:state.digit_count},(_,i)=>u.searchParams.get('boxes').split(',').slice(i*4,i*4+4).map(Number));
   if(u.searchParams.get('baseline_changed')==='1'){state.baseline=Number(u.searchParams.get('baseline'));state.calibrated=u.searchParams.get('baseline_provided')==='1'&&state.boxes.every(b=>b[0]<b[2]&&b[1]<b[3]);}
   state.autofocus_before_reading=u.searchParams.get('focus_mode')==='auto';state.manual_focus_enabled=!state.autofocus_before_reading;state.manual_focus_position=Number(u.searchParams.get('position'));
   state.camera_standby_enabled=u.searchParams.get('standby')==='1';state.camera_weak_drive=u.searchParams.get('weak_drive')==='1';
   state.illumination_led_count=Number(u.searchParams.get('led_count'));state.illumination_enabled=u.searchParams.get('enabled')==='1';state.illumination_brightness=Number(u.searchParams.get('brightness'));state.illumination_settle_ms=Number(u.searchParams.get('settle_ms'));
  }
  if(u.pathname==='/meter/reset'){state.digit_count=8;state.decimals=3;state.rotation_tenths=0;state.reset_count++;state.boxes=Array.from({length:8},()=>[0,0,0,0]);state.digits='';state.calibrated=false;state.message='Zählerkonfiguration gelöscht'}
  return route.fulfill({status:200,body:'Aktion vorgemerkt'});
 });
 async function settings(key){if(!await page.evaluate(()=>document.getElementById('settings_dialog').open))await page.click('#settings_open');await page.click('#tab_'+key);}
 async function closeSettings(){if(await page.evaluate(()=>document.getElementById('settings_dialog').open))await page.click('#settings_close');}
 async function fillBaseline(value){await page.locator('#baseline_editor').evaluate(el=>el.open=true);await page.fill('#baseline',value);}
 await page.goto('http://meter.test/setup');await page.waitForFunction(()=>document.getElementById('message').textContent.includes('Noch nicht'));
 captureDelay=1200;await page.click('#capture');await page.waitForFunction(()=>document.getElementById('message').textContent.includes('Neue Aufnahme wird angefordert'));await page.waitForTimeout(1300);assert(statusRequests>=2,'Status polling must continue while the initial image loads');await page.waitForFunction(f=>ready&&photoFrame===f,state.frame);snapshotDelay=0;captureDelay=0;await page.waitForFunction(()=>document.getElementById('message').textContent.includes('Kamerabild aufgenommen'));
 captureBusyReplies=1;const capturesBefore=posts.filter(p=>p.url.pathname==='/meter/preview').length,frameBefore=state.frame;
 await page.click('#capture');assert(await page.isDisabled('#focus_image'),'Other operations lock immediately');await page.evaluate(()=>document.getElementById('focus_image').click());
 await page.waitForFunction(f=>photoFrame>f,frameBefore);assert.equal(posts.filter(p=>p.url.pathname==='/meter/preview').length,capturesBefore+2,'One busy response is retried after the status becomes idle');assert.deepEqual(dialogs,[],'A busy device must not open a popup');await page.waitForFunction(()=>!document.getElementById('capture').disabled);
 await page.click('#live');await page.waitForFunction(()=>document.getElementById('live').textContent==='Livebild stoppen');assert(await page.isDisabled('#capture'));assert(await page.isDisabled('#focus_image'));assert((await page.textContent('#message')).includes('Debug-Livebild'));state.frame++;await page.waitForFunction(f=>photoFrame===f,state.frame);await page.click('#live');await page.waitForFunction(()=>document.getElementById('live').textContent==='Livebild starten');assert.equal(await page.isDisabled('#capture'),false);
 state.busy=true;state.reader_phase='autofocus';await page.waitForFunction(()=>document.getElementById('message').textContent.includes('Objektiv wird scharfgestellt'));state.busy=false;state.reader_phase='idle';await page.waitForFunction(()=>!document.getElementById('capture').disabled);
 let bounds=await page.locator('#image').boundingBox();
 const xy=(x,y)=>[bounds.x+x*bounds.width/640,bounds.y+y*bounds.height/480];
 await page.mouse.move(...xy(40,100));await page.mouse.down();await page.mouse.move(...xy(600,170));await page.mouse.up();await page.click('#split');
 const boxes=await page.evaluate(()=>boxes);assert.equal(boxes.length,8);assert.deepEqual(boxes[0],[41,100,109,170]);assert.deepEqual(boxes[7],[531,100,599,170]);
 await page.click('#test');await page.waitForTimeout(100);const test=posts.find(p=>p.url.pathname==='/meter/test');assert(test);assert.equal(test.url.searchParams.get('boxes').split(',').length,32);assert.equal(test.headers['x-meter-setup'],'1');assert.deepEqual(dialogs,[], 'Accepted test commands must not show an error dialog');
 await page.click('#save');await page.waitForFunction(()=>!dirty&&!activeAction);assert(!state.calibrated,'Draft save must not activate OCR without a baseline');assert((await page.textContent('#save_state')).includes('Gespeichert'));
 await fillBaseline('00123456');await page.click('#save');await page.waitForTimeout(100);assert.equal(posts.filter(p=>p.url.pathname==='/meter/save_all').at(-1).url.searchParams.get('baseline'),'00123456');
 await page.locator('#image').scrollIntoViewIfNeeded();bounds=await page.locator('#image').boundingBox();await page.selectOption('#digit','7');await page.selectOption('#tool','move');await page.locator('#image').scrollIntoViewIfNeeded();bounds=await page.locator('#image').boundingBox();await page.mouse.move(...xy(560,130));await page.mouse.down();await page.mouse.move(...xy(630,150));await page.mouse.up();const moved=await page.evaluate(()=>boxes[7]);assert.equal(moved[2],640);assert.equal(moved[3]-moved[1],70);
 await page.locator('#fine_details').evaluate(el=>el.open=true);await page.click('[data-adjust="left"]');assert.equal((await page.evaluate(()=>boxes[7]))[0],moved[0]-1);
 await page.selectOption('#step','5');await page.click('[data-adjust="narrow"]');assert.equal((await page.evaluate(()=>boxes[7]))[2]-(await page.evaluate(()=>boxes[7]))[0],moved[2]-moved[0]-5);
 await page.fill('#box_x','500');await page.locator('#box_x').press('Tab');assert.equal((await page.evaluate(()=>boxes[7]))[0],500);
 await page.locator('#image').focus();await page.keyboard.press('ArrowLeft');assert.equal((await page.evaluate(()=>boxes[7]))[0],499);
 await page.keyboard.press('Shift+ArrowUp');assert.equal((await page.evaluate(()=>boxes[7]))[1],moved[1]-10);
 await settings('camera');await page.waitForFunction(()=>document.getElementById('camera_standby').checked);await page.check('#camera_weak_drive');assert(!state.camera_weak_drive,'Editing power settings must not persist');
 assert.equal(await page.locator('#focus_mode option').count(),2);await page.selectOption('#focus_mode','manual');assert(await page.isVisible('#manual_controls'));assert((await page.textContent('#focus_help')).includes('nur die Linse'));
 await page.fill('#focus_position','620');await page.locator('#focus_position').press('Tab');await page.waitForFunction(()=>!activeAction);const unmovedFrame=state.frame;
 await page.click('[data-focus-step="1"]');await page.waitForFunction(()=>!activeAction);assert.equal(state.manual_focus_applied,621);assert.equal(state.frame,unmovedFrame,'Step buttons must not capture a frame');
 await page.click('#focus_image');await page.waitForFunction(()=>!activeAction);assert.equal(state.frame,unmovedFrame+1);assert.equal(posts.filter(p=>p.url.pathname==='/meter/preview').at(-1).url.searchParams.get('focus_mode'),'manual');
 await page.fill('#focus_position','');await page.selectOption('#focus_mode','auto');assert(!(await page.isVisible('#manual_controls')));assert((await page.textContent('#focus_help')).includes('automatisch scharf'));await page.click('#focus_image');await page.waitForFunction(()=>!activeAction);assert.equal(posts.filter(p=>p.url.pathname==='/meter/preview').at(-1).url.searchParams.get('focus_mode'),'auto','New image uses the unsaved selected mode');
 await settings('light');await page.fill('#led_count','6');await page.check('#led_enabled');await page.locator('#led_brightness').fill('45');await page.fill('#led_settle','1500');await page.click('#light_on');await page.waitForFunction(()=>document.getElementById('light_info').textContent.includes('aktiv'));await page.click('#light_off');
 await closeSettings();assert((await page.textContent('#save_state')).includes('Ungespeicherte'));await page.click('#save');await page.waitForFunction(()=>!dirty&&!activeAction);assert(state.camera_weak_drive&&state.illumination_led_count===6&&state.illumination_brightness===45&&state.autofocus_before_reading,'One save persists all sections');
 assert.equal(await page.locator('#focus_save,#light_save,#power_save').count(),0);
 await page.locator('#reference_panel').evaluate(el=>el.open=true);await page.check('#alignment');await page.selectOption('#digit','8');await page.selectOption('#tool','draw');await page.locator('#image').scrollIntoViewIfNeeded();bounds=await page.locator('#image').boundingBox();
 await page.mouse.move(...xy(100,250));await page.mouse.down();await page.mouse.move(...xy(132,282));await page.mouse.up();await page.selectOption('#digit','9');await page.mouse.move(...xy(450,250));await page.mouse.down();await page.mouse.move(...xy(482,282));await page.mouse.up();
 assert.deepEqual(await page.evaluate(()=>references),[[100,250,132,282],[450,250,482,282]]);await page.click('#reference');await page.waitForFunction(()=>document.getElementById('reference_state').textContent.includes('aufgenommen'));const ref=posts.find(p=>p.url.pathname==='/meter/reference');assert.equal(ref.url.searchParams.get('frame'),String(state.frame));
 await page.click('#save');await page.waitForTimeout(100);assert.equal(posts.filter(p=>p.url.pathname==='/meter/save_all').at(-1).url.searchParams.get('alignment'),'1');await page.waitForFunction(()=>!activeAction&&!dirty);await page.uncheck('#alignment');assert.equal(await page.inputValue('#digit'),'0');await page.click('#test');await page.waitForTimeout(100);assert.equal(posts.filter(p=>p.url.pathname==='/meter/test').at(-1).url.searchParams.get('alignment'),'0');
 await page.setViewportSize({width:1440,height:1000});
 const sidebar=await page.locator('.sidebar').boundingBox(),workspace=await page.locator('.workspace').boundingBox();
 assert(sidebar.x+sidebar.width<workspace.x,'Desktop settings must be left of camera');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.locator('.sidebar').evaluate(el=>el.scrollTop=el.scrollHeight);
 const stableCamera=await page.locator('#image').boundingBox();
 assert(stableCamera.y>=0&&stableCamera.y+stableCamera.height<=1000,'Camera stays visible while settings scroll');
 const cameraWrap=await page.locator('.camera-wrap').boundingBox();assert(Math.abs(stableCamera.width-cameraWrap.width)<3,'Camera uses the adjustable image frame width');
 assert(Math.abs(stableCamera.width/stableCamera.height-4/3)<0.01,'Larger camera preserves aspect ratio');
 await page.locator('.sidebar').evaluate(el=>el.scrollTop=0);
 await page.click('.crop:nth-child(3)');assert.equal(await page.inputValue('#digit'),'2');
 if(process.env.UI_SCREENSHOTS){await page.screenshot({path:'/tmp/water-setup-desktop.png',fullPage:true});}
 state.boxes=await page.evaluate(()=>boxes);state.preview_available=true;state.preview_sequence=1;state.preview_corrected=true;
 await page.waitForFunction(()=>previewAvailable);await page.selectOption('#view','processed');await page.waitForFunction(()=>processedReady);
 assert.equal(await page.locator('#box_x').isDisabled(),true);assert.equal(await page.locator('#split').isDisabled(),true);
 assert.deepEqual(await page.evaluate(()=>Array.from(processedPhoto.getContext('2d').getImageData(0,0,1,1).data)),[20,140,220,255]);
 assert.deepEqual(await page.evaluate(()=>allBoxes().slice(0,8)),state.boxes);
 const preserved=await page.evaluate(()=>JSON.stringify(boxes));await page.locator('#image').focus();await page.keyboard.press('ArrowLeft');assert.equal(await page.evaluate(()=>JSON.stringify(boxes)),preserved);
 state.preview_sequence=2;await page.waitForFunction(()=>processedSequence===2);
 rawPreview=Buffer.from((await page.evaluate(()=>processedPhoto.toDataURL('image/jpeg'))).split(',')[1],'base64');state.preview_corrected=false;state.preview_sequence=3;await page.waitForFunction(()=>processedSequence===3&&!previewCorrected);assert.equal(await page.evaluate(()=>allBoxes().length),8);
 if(process.env.UI_SCREENSHOTS)await page.screenshot({path:'/tmp/water-setup-processed.png',fullPage:true});
 state.preview_available=false;await page.waitForFunction(()=>!processedReady);assert((await page.textContent('#view_info')).includes('Kein gültiges'));
 await page.selectOption('#view','raw');assert.equal(await page.locator('#box_x').isEnabled(),true);
 await settings('diagnosis');const [download]=await Promise.all([page.waitForEvent('download'),page.click('#export')]);assert.equal(download.suggestedFilename(),'wasserzaehler-backup.json');
 confirmReset=true;await page.locator('#import_file').setInputFiles({name:'backup.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({format:'esphome-watermeter',version:1,settings:{interval:120},warning_after:600}))});
 await page.waitForFunction(()=>document.getElementById('interval').value==='120');assert.equal(await page.inputValue('#warning_after'),'600');assert(posts.some(p=>p.url.pathname==='/meter/import'));confirmReset=false;await closeSettings();
 state.digit_confidences=[99.2,98.5,84.4,99.1,97.3,98.1,94.2,92.7];state.reading_age=700;state.stale=true;
 await page.waitForFunction(()=>document.getElementById('reading_health').textContent.includes('WARNUNG'));assert((await page.textContent('.crop:nth-child(3)')).includes('84.4 %'));
 state.stale=false;state.reading_age=0;await page.waitForFunction(()=>!document.getElementById('reading_health').textContent.includes('WARNUNG'));
 state.busy=true;await page.waitForFunction(()=>document.getElementById('reset').disabled);await settings('diagnosis');assert.equal(await page.locator('#restart').isEnabled(),true);confirmReset=true;await page.click('#restart');await page.waitForTimeout(100);assert(posts.some(p=>p.url.pathname==='/meter/restart'));confirmReset=false;state.busy=false;await page.waitForFunction(()=>!document.getElementById('reset').disabled);await closeSettings();
 // Rejected saves retain the real cause across background polling and can be retried.
 rejectSave={status:400,body:'Referenzbereiche zuerst aus dem angezeigten Bild übernehmen'};
 await page.click('#save');await page.waitForFunction(()=>!activeAction&&document.getElementById('save_state').textContent.includes('Referenzbereiche'));
 await page.waitForTimeout(1300);assert((await page.textContent('#save_state')).includes('Referenzbereiche'));assert(await page.evaluate(()=>dirty));
 rejectSave={status:431,body:'<html><body>Request Header Fields Too Large</body></html>'};
 await page.click('#save');await page.waitForFunction(()=>!activeAction&&document.getElementById('save_state').textContent.includes('HTTP 431'));assert(!(await page.textContent('#save_state')).includes('<html>'));
 rejectSave=null;
 // Rotation updates locally, preserves the raw source and requires confirmation before clearing ROIs.
 const rotationPosts=posts.length,oldBoxes=await page.evaluate(()=>JSON.stringify(boxes));
 await page.click('#rotation_toggle');await page.click('[data-rotate="900"]');assert.equal(await page.inputValue('#rotation'),'0');assert.equal(await page.evaluate(()=>JSON.stringify(boxes)),oldBoxes);
 confirmReset=true;await page.click('[data-rotate="900"]');confirmReset=false;
 assert.equal(await page.inputValue('#rotation'),'90');assert(await page.evaluate(()=>boxes.every(b=>b.every(v=>!v))));assert.equal(posts.length,rotationPosts);
 await page.evaluate(async()=>{const c=document.createElement('canvas');c.width=640;c.height=480;const x=c.getContext('2d');x.fillStyle='#fff';x.fillRect(0,0,640,480);x.fillStyle='#ff0000';x.fillRect(80,80,40,40);x.fillStyle='#0000ff';x.fillRect(480,380,40,40);photo=new Image();photo.src=c.toDataURL();await photo.decode();draw()});
 assert.deepEqual(await page.evaluate(()=>Array.from(ctx.getImageData(425,75,1,1).data)),[255,0,0,255]);
 assert.deepEqual(await page.evaluate(()=>Array.from(ctx.getImageData(200,375,1,1).data)),[0,0,255,255]);
 assert.deepEqual(await page.evaluate(()=>Array.from(ctx.getImageData(0,0,1,1).data)),[0,0,0,255]);
 await page.click('[data-rotate="1"]');assert.equal(await page.inputValue('#rotation'),'90.1');
 await page.click('#save');await page.waitForFunction(()=>!activeAction&&document.getElementById('save_state').textContent.includes('Gespeichert'));assert.equal(state.rotation_tenths,901);
 assert.equal(Number(posts.filter(p=>p.url.pathname==='/meter/save_all').at(-1).url.searchParams.get('rotation')),901);
 await page.reload();await page.waitForFunction(()=>loaded);assert.equal(await page.inputValue('#rotation'),'90.1');
 // Variable meter layouts affect every setup control and persist across reloads.
 confirmReset=true;await page.fill('#digit_count','7');await page.press('#digit_count','Tab');await page.waitForFunction(()=>digitCount===7);
 assert.equal(await page.locator('#crops .crop').count(),7);assert.equal(await page.locator('#digit option').count(),9);assert.equal(await page.getAttribute('#baseline','maxlength'),'11');assert((await page.textContent('#digit_help')).includes('4 ganze und 3 Nachkommastellen'));
 await page.evaluate(()=>{boxes[0]=[80,100,560,150];draw()});await page.click('#split');assert.equal(await page.evaluate(()=>boxes.length),7);
 await fillBaseline('0123456');await page.click('#save');await page.waitForFunction(()=>!activeAction&&!dirty);assert.equal(state.digit_count,7);assert.equal(state.boxes.length,7);assert.equal(state.baseline,123456);
 const seven=posts.filter(p=>p.url.pathname==='/meter/save_all').at(-1);assert.equal(seven.url.searchParams.get('boxes').split(',').length,28);
 state.digits='0123456';state.confidence=99;state.result_decimals=3;await page.waitForFunction(()=>document.getElementById('digits').textContent==='0123.456 m³');
 state.result_decimals=2;await page.waitForFunction(()=>document.getElementById('digits').textContent==='01234.56 m³');state.result_decimals=3;
 await page.locator('#reference_panel').evaluate(el=>el.open=true);await page.check('#alignment');await page.selectOption('#digit','7');await page.evaluate(()=>changeBox(100,250,32,32));assert.deepEqual(await page.evaluate(()=>references[0]),[100,250,132,282]);await page.uncheck('#alignment');
 state.preview_available=true;state.preview_sequence++;state.preview_corrected=true;await page.waitForFunction(()=>previewAvailable);await page.selectOption('#view','processed');await page.waitForFunction(()=>processedReady);assert.equal(await page.locator('#crops .crop').count(),7);await page.selectOption('#view','raw');
 await page.fill('#digit_count','9');await page.press('#digit_count','Tab');await page.waitForFunction(()=>digitCount===9);assert.equal(await page.locator('#crops .crop').count(),9);assert.equal(await page.locator('#digit option').count(),11);
 await page.evaluate(()=>{boxes[0]=[80,100,560,150];draw()});await page.click('#split');await fillBaseline('999999999');await page.click('#save');await page.waitForFunction(()=>!activeAction&&!dirty);assert.equal(state.digit_count,9);assert.equal(state.boxes.length,9);assert.equal(state.baseline,999999999);
 await page.reload();await page.waitForFunction(()=>loaded);assert.equal(await page.inputValue('#digit_count'),'9');assert.equal(await page.inputValue('#baseline'),'999999,999');
 await page.fill('#digit_count','1');await page.press('#digit_count','Tab');await page.waitForFunction(()=>digitCount===1);assert.equal(await page.inputValue('#decimals'),'0');assert.equal(await page.locator('#crops .crop').count(),1);
 await page.click('#save');await page.waitForFunction(()=>!activeAction&&!dirty);assert.equal(state.calibrated,false,'Saving an empty baseline must remain a draft, including one-digit meters');
 await fillBaseline('9');await page.click('#save');await page.waitForFunction(()=>!activeAction&&!dirty);assert.equal(state.digit_count,1);assert.equal(state.calibrated,true);assert.equal(state.baseline,9);
 await page.reload();await page.waitForFunction(()=>loaded);assert.equal(await page.inputValue('#digit_count'),'1');assert.equal(await page.locator('#digit option').count(),3);confirmReset=false;
 await settings('diagnosis');await page.click('#reset');assert(!posts.some(p=>p.url.pathname==='/meter/reset'));confirmReset=true;
 await page.click('#reset');await page.waitForFunction(()=>boxes.every(b=>b.every(v=>v===0))&&document.getElementById('baseline').value==='');assert(posts.some(p=>p.url.pathname==='/meter/reset'));assert.equal(await page.inputValue('#baseline'),'');
 await closeSettings();await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 if(process.env.UI_SCREENSHOTS)await page.screenshot({path:'/tmp/water-setup-mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);await browser.close();console.log('UI smoke tests passed: scaled ROI drawing, split, move/clamp, test, baseline/save, pixel adjustments, keyboard, confirmed reset, mobile layout');
})().catch(e=>{console.error(e);process.exit(1)});
