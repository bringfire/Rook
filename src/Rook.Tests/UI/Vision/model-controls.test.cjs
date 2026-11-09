const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const resources = path.resolve(__dirname, '../../../Rook/UI/Vision/Resources');
class Element {
  constructor(tag='div') { this.tagName=tag.toUpperCase(); this.value=''; this.textContent=''; this.children=[]; this.dataset={}; this.handlers={}; this.attributes={}; this.style={setProperty(){}}; const s=new Set(); this.classList={add:x=>s.add(x),remove:x=>s.delete(x),contains:x=>s.has(x),toggle(x,on){on?s.add(x):s.delete(x)}}; }
  appendChild(x){this.children.push(x); x.parentNode=this; if(this.tagName==='SELECT' && this.children.length===1)this.value=x.value; return x;}
  replaceChildren(...xs){this.children=[];xs.forEach(x=>this.appendChild(x));}
  addEventListener(n,fn){(this.handlers[n] ||= []).push(fn);}
  removeEventListener(n,fn){this.handlers[n]=(this.handlers[n]||[]).filter(x=>x!==fn);}
  async fire(n){for(const f of [...this.handlers[n]||[]])await f({target:this});}
  setAttribute(k,v){this.attributes[k]=String(v);} removeAttribute(k){delete this.attributes[k];}
  get options(){return this.children;} querySelectorAll(){return [];} closest(){return this;}
  set innerHTML(v){this.html=v;this.children=[];for(const m of v.matchAll(/<option value="([^"]*)"[^>]*>(.*?)<\/option>/g)){this.appendChild(Object.assign(new Element('option'),{value:m[1],textContent:m[2]}));}}
  get innerHTML(){return this.html||'';}
}
function descriptor(extra={}) { return {model_id:'synthetic/image',operation_id:'text_to_image',operations:['text_to_image'],definition_hash:'hash-a',revision:'1',submission_contract:'image_job',selectable:true,pricing_available:true,pricing_status:'available',request_fields:[{key:'prompt',scope:'request',type:'string',required:true,max_length:1000,label:'Prompt'},{key:'seed',scope:'request',type:'integer',min:-9007199254740991,max:9007199254740991,default:0}], options:[{key:'audio',scope:'options',type:'boolean',default:true,ui:{order:0}},{key:'count',scope:'options',type:'integer',min:0,max:10,default:1,ui:{order:1}},{key:'strength',scope:'options',type:'number',min:0.1,max:1,step:0.2,default:0.1,ui:{order:2}},{key:'caption',scope:'options',type:'string',max_length:10,ui:{order:3}},{key:'quality',scope:'options',type:'enum',values:['small','large'],default:'small',ui:{group:'advanced',order:4}}],media:[],constraints:[],...extra}; }
function harness(responses={}) {
 const nodes=new Map();const get=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};const calls=[];
 const context=vm.createContext({console,URL,setTimeout:()=>1,clearTimeout(){},document:{createElement:tag=>new Element(tag),addEventListener(){},getElementById:get,querySelectorAll(){return [];}},window:{confirm:()=>true,rookBridge:{async invoke(domain,args){calls.push(JSON.parse(JSON.stringify(args)));return responses[args.op]?await responses[args.op](args):{success:true,data:args.op==='list_artifacts'?{artifacts:[]}:args.op==='image_job_status'?{job_id:'j1',state:'complete'}:args.op==='image_job_result'?{result_artifact_id:'artifact1'}:{job_id:'j1',state:'queued'}};}}}});
 const controlsPath=path.join(resources,'model-controls.js'); if(fs.existsSync(controlsPath))vm.runInContext(fs.readFileSync(controlsPath,'utf8'),context);
 vm.runInContext(fs.readFileSync(path.join(resources,'app.js'),'utf8'),context);
 const run=code=>vm.runInContext(code,context); const mount=d=>{context.d=d; return run('createConfiguredModelForm(document.getElementById("form"), {model_id:d.model_id,operations:[d]}, () => {})');};
 return {context,run,get,calls,mount};
}
function descendants(el){return [el,...el.children.flatMap(descendants)];}
function field(container,key){return descendants(container).find(x=>x.dataset.field===key && x.dataset.control==='value');}
async function input(container,key,value){const el=field(container,key);assert.ok(el,`Missing control ${key}`);el.value=String(value);await el.fire(el.tagName==='SELECT'?'change':'input');return el;}
const plain=x=>JSON.parse(JSON.stringify(x));
module.exports={Element,descriptor,harness,descendants,field,input,plain};
if(require.main===module){
 test('boolean false and numeric zero survive; displayed defaults stay absent',async()=>{const h=harness();h.context.d=descriptor();const c=h.run('window.RookModelControls.create(document.getElementById("controls"), d, () => {})');assert.deepEqual(plain(c.readOptions()),{});await input(h.get('controls'),'options.audio','false');await input(h.get('controls'),'options.count','0');assert.deepEqual(plain(c.readOptions()),{audio:false,count:0});});
 test('all five field types honor order, advanced groups and plain-text labels',()=>{const h=harness();const d=descriptor();d.options[0].label='<img onerror=bad>';h.context.d=d;h.run('window.RookModelControls.create(document.getElementById("controls"),d,()=>{})');const all=descendants(h.get('controls'));assert.deepEqual(all.filter(x=>x.dataset.control==='value').map(x=>x.dataset.type),['boolean','integer','number','string','enum']);assert.ok(all.some(x=>x.tagName==='DETAILS'));assert.ok(all.some(x=>x.textContent==='<img onerror=bad>'));});
 for(const raw of ['9007199254740993','-9007199254740992','1.1'])test('rejects unsafe raw integer '+raw,async()=>{const h=harness();h.context.d={options:[descriptor().request_fields[1]]};const c=h.run('window.RookModelControls.create(document.getElementById("controls"),d,()=>{})');await input(h.get('controls'),'request.seed',raw);assert.throws(()=>c.readOptions(),/safe integer|integer/i);});
 for(const raw of ['0.1234567890123456789012345678','1000000000.0000001','1e-7'])test('rejects lossy decimal before conversion '+raw,async()=>{const h=harness();h.context.d={options:[{key:'n',type:'number',scope:'options'}]};const c=h.run('window.RookModelControls.create(document.getElementById("controls"),d,()=>{})');await input(h.get('controls'),'options.n',raw);assert.throws(()=>c.readOptions(),/six|precision|number|decimal/i);});
 test('decimal step originates at min and uses exact arithmetic',async()=>{const h=harness();h.context.d=descriptor();const c=h.run('window.RookModelControls.create(document.getElementById("controls"),d,()=>{})');await input(h.get('controls'),'options.strength','0.3000000');assert.equal(c.readOptions().strength,0.3);await input(h.get('controls'),'options.strength','0.2');assert.throws(()=>c.readOptions(),/step/i);});

 test('admitted numeric boundaries and zero serialize as ordinary exact numbers',async()=>{const h=harness();const d=descriptor({options:[{key:'n',scope:'options',type:'number',min:-1000000000,max:1000000000,step:0.000001}]});h.context.d=d;const c=h.run('window.RookModelControls.create(document.getElementById("controls"),d,()=>{})');for(const value of ['-1000000000','1000000000','0','0.000001','-0.000001','0.1234560000']){await input(h.get('controls'),'options.n',value);assert.equal(c.readOptions().n,Number(value));}});
 test('conditional enum restrictions intersect without dropping explicit conflicting values',async()=>{const h=harness();h.context.d=descriptor({constraints:[{kind:'allowed_values',field:'options.quality',values:['large'],when:[]}]});const c=h.run('window.RookModelControls.create(document.getElementById("controls"),d,()=>{})');c.updateContext({values:{},media:[]});const select=field(h.get('controls'),'options.quality');assert.equal(select.options.find(o=>o.value==='small').disabled,true);assert.equal(select.options.find(o=>o.value==='large').disabled,false);await input(h.get('controls'),'options.quality','small');assert.equal(c.readOptions().quality,'small');});
 test('field errors clear and disposed listeners do not fire',async()=>{const h=harness();h.context.d=descriptor();h.run('var changes=0; var c=window.RookModelControls.create(document.getElementById("controls"),d,()=>changes++)');h.run('c.setValidation([{field:"options.audio",message:"Audio conflict"}])');assert.ok(descendants(h.get('controls')).some(x=>x.textContent==='Audio conflict'));await input(h.get('controls'),'options.audio','false');assert.ok(!descendants(h.get('controls')).some(x=>x.textContent==='Audio conflict'));const node=field(h.get('controls'),'options.audio');h.run('c.dispose()');await node.fire('change');assert.equal(h.run('changes'),1);});
}
