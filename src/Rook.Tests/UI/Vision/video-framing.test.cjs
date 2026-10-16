const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const test = require('node:test');
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'Fixtures/video-framing-bridge.json'), 'utf8'));
const source = fs.readFileSync(path.resolve(__dirname, '../../../Rook/UI/Vision/Resources/app.js'), 'utf8').replace(/\r\n/g, '\n');
class Element {
  constructor() { this.value=''; this.dataset={}; this.handlers={}; this.options=[]; this.attributes={}; this.style={setProperty(){}}; const classes=new Set(); this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x),toggle(x,on){on?classes.add(x):classes.delete(x)}}; }
  addEventListener(name, fn) { this.handlers[name]=fn; }
  fire(name,event={}) { return this.handlers[name]?.({target:this,preventDefault(){},...event}); }
  appendChild(x){this.options.push(x);} focus(){this.focused=true;}
  querySelectorAll(){return [];} querySelector(){return null;} setAttribute(k,v){this.attributes[k]=v;} getAttribute(k){return this.attributes[k];}
  set innerHTML(value) { this.htmlWrites=(this.htmlWrites||0)+1; this.html=value; this.options=[...value.matchAll(/<option value="([^"]*)"[^>]*>/g)].map(m=>({value:m[1]})); if(this.options.length)this.value=this.options[0].value; }
  get innerHTML(){return this.html||'';}
}
const input={kind:'artifact_id',artifact_id:'11111111-1111-1111-1111-111111111111',role:'image'};
function preview(args) {
  const data=JSON.parse(JSON.stringify(fixture.preview));
  const height=args.resolution==='720p'?720:1080, width=height===720?1280:1920;
  for(const mode of ['fit','fill']) {
    data[mode].slots=(args.end_frame?['start_frame','end_frame']:['start_frame']).map((role,i)=>{
      const slot={...data[mode].slots[0],role}; const ref=args[role];
      slot.sha256=crypto.createHash('sha256').update(JSON.stringify([args.model,args.resolution,args.aspect_ratio,mode,ref.artifact_id,role])).digest('hex');
      slot.width=args.aspect_ratio==='9:16'?height:width; slot.height=args.aspect_ratio==='9:16'?width:height;
      return slot;
    });
  }
  return data;
}
function estimate(args){const selected=preview(args)[args.source_framing||'fit'];return {model:args.model,resolution:args.resolution,duration_seconds:args.duration_seconds,number_of_videos:1,dollars_usd:3.2,maximum_estimated_cost_usd:3.2,estimate_fingerprint:'v1:'+'a'.repeat(64),pricing:{pricing_source:'test'},source_preparation:args.source_framing?{mode:args.source_framing,slots:selected.slots.map(s=>({role:s.role,prepared_sha256:s.sha256,width:s.width,height:s.height}))}:null};}
async function harness(responses={}) {
  const nodes=new Map(), timers=new Map();let timerId=0; const get=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
  const modes=['t2v','i2v','interp'].map((v,i)=>Object.assign(new Element(),{value:v,checked:i===0}));
  const calls=[];const cap={name:'Veo',status:'preview',resolutions:['720p','1080p'],durations:[4,6,8],aspect_ratios:['16:9','9:16'],modes:['t2v','i2v','interp'],supports_reference_images:true,max_reference_images:3,must_8s_with:['1080p','referenceImages']};
  const catalog=[{model_id:'veo-3.1-generate-preview',provider_name:'veo',pricing_kind:'per_second',pricing_source:'test',capability:cap,can_generate:true,credential_configured:true,new_submission_available:true}];
  const context=vm.createContext({console,URL,setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id),document:{createElement:()=>new Element(),addEventListener(){},getElementById:get,querySelectorAll:q=>q.includes('video-mode')?modes:[]},window:{confirm:()=>true,rookBridge:{async invoke(domain,args){calls.push(args);if(responses[args.op])return await responses[args.op](args);return {success:true,data:args.op==='list_video_models'?{models:catalog}:args.op==='list_video_jobs'?{jobs:[]}:args.op==='preview_video_framing'?(args.cancel_only?{}:preview(args)):args.op==='estimate_video_job'?estimate(args):{job_id:'job-1',state:'queued'}};}}}});
  const exports='        cacheEls, wireEvents, onEnter, refreshFramingPreview, selectFraming, runEstimate, ensureCurrentEstimate, onGenerateClicked, refreshAvailability, onLeave, buildSubmitArgs,\n        testFrames(a,b) { startFrame=a; endFrame=b||null; scheduleEstimate(); }, testState() { return {framing:framingState, estimate:estimateState, selected:selectedFraming}; },';
  vm.runInContext(source.replace('        cacheEls,\n        wireEvents,\n        onEnter,',exports),context);const run=code=>vm.runInContext(code,context);
  run('Video.cacheEls(); Video.wireEvents();'); get('video-prompt').value='A moving garden'; await run('Video.onEnter()');
  get('video-resolution-select').value='1080p';get('video-duration-select').value='8';
  const mode=async(value='i2v',frame=input,end)=>{modes.forEach(m=>m.checked=m.value===value);await modes.find(m=>m.checked).fire('change');context.frame=frame;context.end=end;run('Video.testFrames(frame,end)');await run('Video.refreshFramingPreview()');};
  return {run,get,calls,context,modes,catalog,mode};
}
test('both actual cards show sources and preserve deliberate Fill across edits',async()=>{
  const h=await harness();await h.mode();assert.match(h.get('video-framing-fit-preview').innerHTML,/\/blob\//);assert.match(h.get('video-framing-fill-preview').innerHTML,/\/blob\//);
  h.run('Video.selectFraming("fill")');h.get('video-aspect-select').value='9:16';h.get('video-aspect-select').fire('change');await h.run('Video.refreshFramingPreview()');
  assert.equal(h.run('Video.testState().selected'),'fill');assert.equal(h.get('video-framing-fill').getAttribute('aria-checked'),'true');
  await h.mode('interp',input,{...input,artifact_id:'44444444-4444-4444-4444-444444444444'});assert.match(h.get('video-framing-fill-preview').innerHTML,/Start image/);assert.match(h.get('video-framing-fill-preview').innerHTML,/End image/);
});
test('estimate failure survives Generate and retry without editing fields',async()=>{
  let attempts=0;const h=await harness({estimate_video_job:async args=>++attempts===1?fixture.route_unavailable:{success:true,data:estimate(args)}});await h.mode();
  await h.run('Video.runEstimate()');await h.run('Video.onGenerateClicked()');assert.match(h.get('video-status-message').textContent,/Google API key/);assert.doesNotMatch(h.get('video-status-message').textContent,/adjust a field|out of date/i);
  assert.equal(h.calls.filter(c=>c.op==='submit_video_job').length,0);await h.get('video-retry-preflight').fire('click');assert.equal(h.run('Video.testState().estimate.status'),'ready');
});
test('late source preview cannot confirm another source',async()=>{
  let release;let first=true;const h=await harness({preview_video_framing:args=>args.cancel_only?{success:true,data:{}}:first?(first=false,new Promise(r=>release=()=>r({success:true,data:preview(args)}))):{success:true,data:preview(args)}});
  h.modes.forEach(m=>m.checked=m.value==='i2v');h.context.frame=input;h.run('Video.testFrames(frame)');const old=h.run('Video.refreshFramingPreview()');
  h.context.frame={...input,artifact_id:'55555555-5555-5555-5555-555555555555'};h.run('Video.testFrames(frame)');await h.run('Video.refreshFramingPreview()');release();await old;
  const state=JSON.parse(h.run('JSON.stringify(Video.testState())'));assert.match(state.framing.key,/55555555/);await h.run('Video.ensureCurrentEstimate()');assert.equal(h.get('video-generate-btn').disabled,false);
});
test('failed Fill remains selected and offers working Fit',async()=>{
  const h=await harness({preview_video_framing:args=>({success:true,data:args.cancel_only?{}:{...preview(args),fill:{success:false,slots:[],error:fixture.fill_limits}}})});await h.mode();h.run('Video.selectFraming("fill")');await h.run('Video.onGenerateClicked()');
  assert.equal(h.run('Video.testState().selected'),'fill');assert.equal(h.get('video-generate-btn').disabled,true);assert.equal(h.get('video-use-fit').classList.contains('hidden'),false);
  await h.get('video-use-fit').fire('click');assert.equal(h.run('Video.testState().selected'),'fit');await h.run('Video.ensureCurrentEstimate()');assert.equal(h.get('video-generate-btn').disabled,false);
});
test('pending Generate awaits the current estimate and preview digest mismatch blocks confirmation',async()=>{
  let release,arrived;const entered=new Promise(r=>arrived=r);const h=await harness({estimate_video_job:args=>new Promise(r=>{arrived();release=()=>{const data=estimate(args);data.source_preparation.slots[0].prepared_sha256='b'.repeat(64);r({success:true,data});};})});await h.mode();const pending=h.run('Video.runEstimate()');await entered;const click=h.run('Video.onGenerateClicked()');release();await pending;await click;
  assert.equal(h.get('video-cost-modal').classList.contains('hidden'),true);assert.equal(h.calls.filter(c=>c.op==='submit_video_job').length,0);assert.equal(h.run('Video.testState().estimate.status'),'failed');
});
test('settings refresh beats stale availability and does not reset form',async()=>{
  let count=0,release;const h=await harness();await h.mode();h.run('Video.selectFraming("fill")');
  const current=h.catalog[0];const later={...current,can_generate:false,generation_unavailable_reason:'Needs key',generation_unavailable_detail_code:'video_route_unavailable'};
  h.context.window.rookBridge.invoke=async(domain,args)=>{h.calls.push(args);if(args.op==='list_video_models')return ++count===1?new Promise(r=>release=()=>r({success:true,data:{models:[later]}})):{success:true,data:{models:[current]}};return {success:true,data:{}};};
  const old=h.run('Video.refreshAvailability()');await h.run('Video.refreshAvailability()');release();await old;assert.equal(h.run('Video.testState().selected'),'fill');assert.equal(h.get('video-prompt').value,'A moving garden');assert.equal(h.run('Video.testState().estimate.status')==='failed',false);
});
test('leaving sends cancel-only and T2V omits source framing',async()=>{
  const h=await harness();await h.mode();assert.equal(h.run('Video.buildSubmitArgs().source_framing'),'fit');await h.mode('t2v');assert.equal(h.run('Video.buildSubmitArgs().source_framing'),undefined);await h.run('Video.onLeave()');assert.equal(h.calls.filter(c=>c.op==='preview_video_framing').at(-1).cancel_only,true);
});
test('prompt edits and framing selection do not reload unchanged preview images',async()=>{
  const h=await harness();await h.mode();const node=h.get('video-framing-fit-preview'),writes=node.htmlWrites;
  h.get('video-prompt').value='A new camera move';h.get('video-prompt').fire('input');h.run('Video.selectFraming("fill")');
  assert.equal(node.htmlWrites,writes);assert.equal(h.calls.filter(c=>c.op==='preview_video_framing'&&!c.cancel_only).length,1);
});
