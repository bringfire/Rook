"""Execute the existing panel module in Node with a small synthetic DOM; no media calls."""
import shutil
import subprocess
from pathlib import Path

SCRIPT = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const source=fs.readFileSync(process.argv[1],'utf8').replace(/\r\n/g,'\n');
let module=source.slice(source.indexOf('const Video = (() => {'),source.indexOf('// ─── Reconstruct module'));
module=module.replace('        cacheEls,\n',`        testSetup() {
            catalog=[{model_id:'vertex_ai/veo-3.1-fast-generate-001',provider_name:'vertex_ai'}]; selectedCapability={};
            ve.modelSelect={value:catalog[0].model_id};ve.durationSelect={value:'4'};ve.resolutionSelect={value:'720p'};
            ve.aspectSelect={value:'16:9'};ve.personGenSelect={value:'allow_adult'};ve.prompt={value:'building'};
            ve.modeRadios=[{checked:true,value:'t2v'}];
            ve.generateBtn={};ve.costConfirmBtn={};ve.costModal={classList:{add(){}}};
            ve.statusMessage={textContent:'',classList:{remove(){}}};ve.costStrip={dataset:{}};
            ve.costStrip.dataset.lastEstimateArgs=JSON.stringify(buildSubmitArgs());
            renderQueue=()=>{};startPolling=()=>{};
        },submitJob,cancelJob,onGenerateClicked,videoPriceLabel,
        addJob(entry){queue.set(entry.job_id,{entry});},status(){return ve.statusMessage.textContent;},
        clearStatus(){ve.statusMessage.textContent='';},
        cacheEls,
`);
let calls=0,resolve,reject,stopState='interrupted',confirmed=true,confirmText='';
const context={console,setTimeout,clearTimeout,window:{confirm(text){confirmText=text;return confirmed;}},
    bridgeCall(op){calls++;if(op==='cancel_video_job')return Promise.resolve({state:stopState});return new Promise((a,b)=>{resolve=a;reject=b;});},
    errorToText:e=>e.message};
vm.createContext(context);vm.runInContext(module+'\nthis.testVideo=Video;',context);
(async()=>{
    const video=context.testVideo;video.testSetup();
    const first=video.submitJob();await video.submitJob();assert.equal(calls,1);
    reject(new Error('Google submission outcome is unknown'));await first;assert.equal(calls,1);
    assert.match(video.status(),/unknown/);
    video.addJob({job_id:'unknown',state:'interrupted',error:{message:'Stopped',submission_outcome_unknown:true},request_summary:{model:'vertex_ai/model'}});
    confirmed=false;video.onGenerateClicked();assert.match(confirmText,/another billed generation/);assert.equal(calls,1);
    assert.match(video.videoPriceLabel({dollars_usd:0,pricing:{pricing_source:'vertex-project-billing-unpriced'}}),/price unavailable/);
    video.addJob({job_id:'active',state:'polling',request_summary:{model:'vertex_ai/model'}});
    confirmed=true;await video.cancelJob('active');assert.match(video.status(),/Local monitoring stopped/);assert.match(confirmText,/incur charges/);
    stopState='complete';video.clearStatus();await video.cancelJob('active');assert.equal(video.status(),'');
    console.log('double-click, unknown billing warning, local stop and completion race passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''

def test_panel_submission_and_local_stop_behaviors():
    node=shutil.which('node')
    assert node, 'Existing Node runtime is required for panel behavior acceptance.'
    source=Path(__file__).resolve().parents[2]/'src/Rook/UI/Vision/Resources/app.js'
    result=subprocess.run([node,'-e',SCRIPT,str(source)],capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
