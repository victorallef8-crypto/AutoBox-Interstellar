import fs from 'node:fs';import vm from 'node:vm';import assert from 'node:assert/strict';
const src=fs.readFileSync(new URL('../browser_session.py',import.meta.url),'utf8');
const script=JSON.parse(src.match(/^SKYLAB_SCRIPT = (.+)$/m)[1]);
const lab={initialized:true,revision:1,now:1000,stock:{prometium:100,endurium:100,terbium:100},
 power:{demand:50,available:200},modules:{basic:{level:2,enabled:true},solar:{level:1,enabled:true},transport:{level:1,enabled:true},prometium:{level:1,enabled:true}}};
const me={id:'test',respawnRevision:1,hp:100,credits:1000,skylab:lab};
const S={ids:Object.keys(lab.modules),raw:['prometium','endurium','terbium'],
 modules:Object.fromEntries(Object.keys(lab.modules).map(id=>[id,{name:id,maxLevel:id==='transport'?1:20}])),
 power:level=>level>0?15+level*level:0,
 quote:(id,level)=>level>=(id==='transport'?1:20)?null:{level:level+1,credits:100,ore:10,seconds:60}};
let clicks=0;const normal={disabled:false,click:()=>clicks++},tab={click:()=>{},hidden:false},select={click:()=>{}};
const panel={hidden:false,querySelector:selector=>{
 if(selector==='.manufacturing-content')return {dataset:{manufacturingTab:'skylab'}};
 if(selector.startsWith('[data-lab-module='))return select;
 if(selector==='[data-lab-tab="upgrade"]')return tab;
 if(selector==='[data-lab-upgrade="normal"]')return normal;
 throw Error('Unexpected selector: '+selector);
}};
const W={state:{me},readOnly:false};
const env={window:{PeriodWindows:W,InterstellarSkylab:S},document:{getElementById:id=>{assert.equal(id,'period-manufacturing');return panel;}}};
vm.createContext(env);const run=vm.runInContext('('+script+')',env);
const inspect=()=>run({action:'inspect'});
const command=()=>({action:'upgrade',owner:'test',life:1,revision:lab.revision,module:'prometium',level:1,target:20,reserve:0});
assert.equal(inspect().rows.find(r=>r.id==='transport').reason,'concluido');
assert.equal(run(command()).action,'sent');assert.equal(clicks,1);
lab.modules.basic.level=1;assert.equal(inspect().rows.find(r=>r.id==='prometium').reason,'modulo_basico');
assert.equal(run(command()).action,'wait');lab.modules.basic.level=2;
me.credits=99;assert.equal(run(command()).action,'wait');me.credits=1000;
assert.equal(run({...command(),reserve:950}).action,'wait');
lab.stock.terbium=0;assert.equal(run(command()).action,'wait');lab.stock.terbium=100;
lab.power.available=50;assert.equal(run(command()).action,'wait');lab.power.available=200;
lab.modules.solar.job={level:2,end:60000};assert.equal(run(command()).action,'wait');
assert.equal(inspect().rows.find(r=>r.id==='solar').remaining,59);delete lab.modules.solar.job;
assert.equal(run({...command(),revision:0}).action,'changed');
assert.throws(()=>run({...command(),life:2}),/mudou/);
panel.hidden=true;assert.throws(()=>run(command()),/aberto/);panel.hidden=false;
normal.disabled=true;assert.throws(()=>run(command()),/indisponível/);normal.disabled=false;
me.hp=0;assert.throws(()=>inspect(),/destruída/);me.hp=100;
W.readOnly=true;assert.throws(()=>inspect(),/Abra/);W.readOnly=false;
for(const action of ['finish','instant','send','buy-robots'])assert.throws(()=>run({...command(),action}),/não permitida/);
assert.equal(clicks,1);
console.log('Skylab: only normal construction; costs, prerequisites, energy, job, life and UI guards passed.');
