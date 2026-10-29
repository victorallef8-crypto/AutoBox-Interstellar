import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync(new URL('../pet_collection.py',import.meta.url),'utf8');
const script=source.match(/PET_COLLECT_SCRIPT = r"""([\s\S]*?)"""/)[1];
const fn=eval('('+script+')');
const calls=[];
globalThis.window={PeriodWindows:{state:{me:{id:'p',mapId:'1-1',respawnRevision:1,activeConfiguration:1,x:100,y:100,hp:100,maxHp:100,
 pet:{active:true,mode:'petal1',level:2,hp:100,fuel:100,fuelRate:1,configurations:[{gears:['petal1']}] }},map:{width:2000,height:2000},boxes:[{id:'b',revision:1,x:1000,y:100,kind:'bonus'}]},
 petRequest:t=>calls.push(t)},DarkOrbitServices:{items:{petal1:{petGear:true,family:'al',tier:1,minLevel:0,value:700}}},
 DarkOrbitGroups:{onFollow:t=>calls.push(t),onFollowCancel:()=>calls.push('stop')}};
const t={owner:'p',life:1,map:'1-1',configuration:1};
assert.equal(fn({...t,action:'ensure'}).action,'ready');
assert.equal(fn({...t,action:'move',id:'b',revision:1,x:1600,y:100}).action,'move');
assert.deepEqual(calls,[{x:1960,y:100,mapId:'1-1'}]);
assert.equal(fn({...t,action:'cruise',x:350,y:350}).action,'move');
assert.throws(()=>fn({...t,action:'cruise',x:-1,y:0}),/fora do mapa/);
assert.equal(fn({...t,action:'move',id:'b',revision:1,x:1000,y:100}).destination.x,1960);
window.PeriodWindows.state.me.pet.fuel=0;
assert.throws(()=>fn({...t,action:'move',id:'b',revision:1,x:1600,y:100}),/combustível/);
assert.equal(fn({...t,action:'stop'}).action,'stopped');
window.PeriodWindows.state.me.pet.fuel=100;
window.PeriodWindows.state.me.pet.configurations[0].gears=[];
assert.throws(()=>fn({...t,action:'ensure'}),/Auto-looter/);
window.PeriodWindows.state.me.pet.configurations[0].gears=['petal1'];
window.PeriodWindows.state.me.pet.active=false;
assert.equal(fn({...t,action:'ensure'}).expected_active,true);
assert.deepEqual(calls.at(-1),{action:'launch'});
window.PeriodWindows.state.me.pet.active=true;
window.PeriodWindows.state.me.y=200;
assert.doesNotThrow(()=>fn({...t,action:'move',id:'b',revision:1,x:1600,y:100}),'A newer live position must not abort flight after a turn');
const live=calls.at(-1),me=window.PeriodWindows.state.me;
assert.ok(Math.abs((live.x-1000)*(100-me.y)-(live.y-100)*(1000-me.x))<.01);
window.PeriodWindows.state.boxes=[];
assert.equal(fn({...t,action:'move',id:'b',revision:1,x:1600,y:100}).action,'gone');
assert.throws(()=>fn({...t,life:2,action:'move'}),/mudou/);
console.log('PET: level 2/tier 1, move-only commands, fuel/equipment/session/offset guards passed.');
