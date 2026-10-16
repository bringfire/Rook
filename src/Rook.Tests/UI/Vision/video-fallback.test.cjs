const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'Fixtures/video-fallback-bridge.json'), 'utf8'));
const source = fs.readFileSync(path.resolve(__dirname, '../../../Rook/UI/Vision/Resources/app.js'), 'utf8').replace(/\r\n/g, '\n');
class Element {
  constructor() { this.value=''; this.dataset={}; this.handlers={}; this.options=[]; this.style={setProperty(){}}; const classes=new Set(); this.classList={add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x),toggle(x,on){on?classes.add(x):classes.delete(x)}}; }
  addEventListener(name, fn) { this.handlers[name]=fn; }
  fire(name) { return this.handlers[name]?.({target:this}); }
  appendChild(x){this.options.push(x);}
  querySelectorAll(){return [];} querySelector(){return null;} setAttribute(){}
  set innerHTML(value) { this.html=value; this.options=[...value.matchAll(/<option value="([^"]*)"[^>]*>/g)].map(m=>({value:m[1]})); if(this.options.length)this.value=this.options[0].value; }
  get innerHTML(){return this.html||'';}
}
async function harness(responses={}) {
  const nodes=new Map(); const get=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
  const modes=['t2v','i2v','interp'].map((v,i)=>Object.assign(new Element(),{value:v,checked:i===0}));
  const calls=[]; const timers=[];
  const estimate=fixture.estimate.Data || fixture.estimate.data;
  const cap={name:'Veo',status:'preview',resolutions:['720p','1080p'],durations:[4,6,8],aspect_ratios:['16:9','9:16'],modes:['t2v','i2v','interp'],supports_reference_images:true,max_reference_images:3,must_8s_with:['1080p','referenceImages']};
  const catalog=[{model_id:'veo-3.1-generate-preview',provider_name:'veo',pricing_kind:'per_second',pricing_source:'test',capability:cap},{model_id:'fal-ai/veo3.1',provider_name:'fal',pricing_kind:'per_second',pricing_source:'test',capability:cap,new_submission_available:false,availability_reason:'endpoint_continuity_unverified'}];
  const context=vm.createContext({console,URL,setTimeout:fn=>(timers.push(fn),timers.length),clearTimeout(){},document:{createElement:()=>new Element(),addEventListener(){},getElementById:get,querySelectorAll:q=>q.includes('video-mode')?modes:[]},window:{confirm:()=>true,rookBridge:{async invoke(domain,args){calls.push(args);if(responses[args.op])return await responses[args.op](args);return {success:true,data:args.op==='list_video_models'?{models:catalog}:args.op==='list_video_jobs'?{jobs:[]}:args.op==='estimate_video_job'?estimate:args.op==='get_video_job'?{job_id:'job-1',state:'complete'}:{job_id:'job-1',state:'queued'}};}}}});
  const instrumented=source.replace('        cacheEls,\n        wireEvents,\n        onEnter,','        cacheEls, wireEvents, onEnter, runEstimate, openCostModalIfHaveEstimate, buildSubmitArgs, testFilter: setQueueFilter,\n        testMedia(value) { startFrame=value; },');
  vm.runInContext(instrumented,context); const run=code=>vm.runInContext(code,context);
  run('Video.cacheEls(); Video.wireEvents(); providerSecretKeyByProvider.set("fal","fal.api_key"); providerSecretKeyByProvider.set("gemini","gemini.api_key");'); get('video-prompt').value='A moving garden'; await run('Video.onEnter()');
  get('video-duration-select').value='4'; get('video-resolution-select').value='720p';
  return {run,get,calls,context,modes,estimate,catalog};
}
test('untouched_vs_explicit_people_control', async()=>{
  const h=await harness(); assert.deepEqual(JSON.parse(h.run('JSON.stringify(Video.buildSubmitArgs().options)')),{});
  h.get('video-person-gen-select').value='allow_adult'; h.get('video-person-gen-select').fire('change');
  assert.equal(h.run('Video.buildSubmitArgs().options.person_generation'),'allow_adult');
  h.get('video-person-gen-select').value='allow_all'; h.get('video-person-gen-select').fire('change'); assert.equal(h.run('Video.buildSubmitArgs().options.person_generation'),'allow_all');
});
test('conditional_prices_and_maximum_are_confirmed', async()=>{
  const h=await harness(); await h.run('Video.runEstimate()'); h.run('Video.openCostModalIfHaveEstimate()'); await h.get('video-cost-confirm-btn').fire('click');
  const submit=h.calls.find(c=>c.op==='submit_video_job'); assert.equal(submit.estimate_fingerprint,h.estimate.estimate_fingerprint); assert.equal(submit.max_estimated_cost_usd,h.estimate.maximum_estimated_cost_usd);
  assert.match(h.get('video-cost-breakdown-body').innerHTML,/veo|fal/i);
});
test('stale_estimate_response_cannot_enable_submit', async()=>{
  let release; const h=await harness({estimate_video_job:()=>new Promise(r=>release=r)}); const pending=h.run('Video.runEstimate()');
  h.get('video-prompt').value='changed'; h.get('video-prompt').fire('input'); release(fixture.estimate.Data?{success:true,data:fixture.estimate.Data}:fixture.estimate); await pending; await h.get('video-cost-confirm-btn').fire('click'); assert.equal(h.calls.filter(c=>c.op==='submit_video_job').length,0);
});
test('price_revision_requires_fresh_confirmation', async()=>{
  const h=await harness({submit_video_job:async()=>({success:false,data:{code:'invalid_request',detail_code:'estimate_stale',message:'Estimate changed.'}})});
  await h.run('Video.runEstimate()'); h.run('Video.openCostModalIfHaveEstimate()'); await h.get('video-cost-confirm-btn').fire('click'); await h.get('video-cost-confirm-btn').fire('click');
  assert.equal(h.calls.filter(c=>c.op==='submit_video_job').length,1); assert.equal(h.get('video-prompt').value,'A moving garden');
});
for (const kind of ['missing','rejected','403']) test('direct_fal_credentials_without_receipt '+kind, async()=>{
  const h=await harness({list_video_jobs:async()=>({success:true,data:{jobs:[{job_id:'direct-job',request_summary:{model:'fal-ai/veo3.1'},...fixture['direct_'+kind].data}]}})});
  await h.get('video-refresh-queue').fire('click');
  assert.equal(h.run('sessionValidationBySecret.get(secretOverlayKey("fal", "fal.api_key"))')||null,kind==='rejected'?'invalid':null);
});
test('stop_and_unknown_outcome_preserve_form_media', async()=>{
  const h=await harness({submit_video_job:async()=>{throw new Error('Lost start response');}});
  h.context.media={kind:'artifact_id',artifact_id:'image-1',role:'image'}; h.run('Video.testMedia(media)');
  await h.run('Video.runEstimate()'); h.run('Video.openCostModalIfHaveEstimate()'); await h.get('video-cost-confirm-btn').fire('click');
  assert.equal(h.calls.filter(c=>c.op==='submit_video_job').length,1); assert.equal(h.run('Video.buildSubmitArgs().start_frame.artifact_id'),'image-1'); assert.equal(h.get('video-prompt').value,'A moving garden'); assert.match(h.get('video-status-message').textContent,/unknown.*history/i);
});
test('marker_warning_keeps_completed_video_and_stop_persistence_is_distinct', async()=>{
  const h=await harness({list_video_jobs:async()=>({success:true,data:{jobs:[{job_id:'completed',state:'complete',result_artifact_id:'saved',warnings:['artifact_marker_pending'],request_summary:{model:'veo-3.1-generate-preview'}},{job_id:'stopped',state:'polling',execution_stopped:true,stop_persistence:'failed',cleanup:'unknown',request_summary:{model:'veo-3.1-generate-preview'}}]}})});
  // Select all via the real filter handler.
  h.run('Video.testFilter("all")');
  assert.match(h.get('video-queue-list').innerHTML,/Video saved; publication marker repair pending/); assert.match(h.get('video-queue-list').innerHTML,/data-id="saved"/); assert.match(h.get('video-queue-list').innerHTML,/stop persistence failed/);
});
test('labels_have_readable_separators',()=>assert.equal(source.includes('\uFFFD'),false));

test('network_fallback_notice_explains_non_acceptance_without_claiming_a_bad_key',async()=>{
  const h=await harness();
  const text=h.run('videoExecutionNotice({effective_provider:"fal",video_route:{fallback_reason:"google_not_accepted"}})');
  assert.match(text,/Google.*not accepted/i);
  assert.doesNotMatch(text,/credential unavailable|key missing|key rejected/i);
});
