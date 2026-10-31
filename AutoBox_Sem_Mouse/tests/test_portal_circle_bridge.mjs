import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=fs.readFileSync(new URL('../browser_session.py',import.meta.url),'utf8');
const script=JSON.parse(source.match(/^NPC_SCRIPT = (.+)$/m)[1]);
const sent=[],npc={id:'npc',respawnRevision:1,x:500,y:500,hp:100};
const me={x:1200,y:1000,hp:100,maxHp:100,mapId:'a',respawnRevision:1,attacking:true,targetId:'npc'};
const gate={id:'gate',x:1000,y:1000,to:'b'};
const state={me,npcs:[npc],map:{gates:[gate]},world:{width:2000,height:2000}};
const renderer={state,worldAt:()=>({x:0,y:0}),hitTarget:()=>npc};
const env={window:{PeriodWindows:{renderer},DarkOrbitGroups:{onFollow:p=>sent.push(p)}},document:{getElementById:()=>({})}};
vm.createContext(env);const run=vm.runInContext('('+script+')',env);
const request={action:'portal_lure',id:'npc',revision:1,map:'a',life:1,min_hp:40};
assert.equal(run(request).action,'luring');
assert.equal(sent.at(-1).x,1080);
// Moving towards a waypoint must not move that waypoint every frame.
me.x=1150;run(request);assert.equal(renderer.__autoboxPortalCircle.x,1080);
for(let i=0;i<100;i++){
 me.x=renderer.__autoboxPortalCircle.x;me.y=renderer.__autoboxPortalCircle.y;
 run(request);
 const p=renderer.__autoboxPortalCircle;
 assert.ok(Math.abs(Math.hypot(p.x-gate.x,p.y-gate.y)-80)<1e-6);
 assert.ok(p.x>=80&&p.y>=80&&p.x<=1920&&p.y<=1920);
}
// All four corners must offer an inward orbit even when both initial arcs are outside.
for(const [x,y] of [[90,90],[1910,90],[90,1910],[1910,1910]]){
 npc.x=x;npc.y=y;me.x=x;me.y=y;
 renderer.__autoboxMove=null;
 assert.equal(run({...request,action:'orbit',radius:450,rotate:true}).action,'orbiting');
 const p=sent.at(-1);assert.ok(p.x>=80&&p.y>=80&&p.x<=1920&&p.y<=1920);
}
// Portal beside map edge uses a smaller circle, without clipping its shape.
gate.x=120;gate.y=120;me.x=200;me.y=120;renderer.__autoboxPortalCircle=null;
run(request);assert.ok(Math.abs(Math.hypot(renderer.__autoboxPortalCircle.x-120,renderer.__autoboxPortalCircle.y-120)-40)<1e-6);
console.log('Portal waypoints, bounded circles and four-corner orbits passed.');
// Radial corrections are bounded; preferred direction stays stable in clear space.
state.world={width:10000,height:10000};npc.x=5000;npc.y=5000;
for(const [distance,expected] of [[300,450],[450,450],[700,450]]){
 me.x=5000+distance;me.y=5000;renderer.__autoboxMove=null;
 const result=run({...request,action:'orbit',radius:450,rotate:true,direction:-1});
 assert.equal(result.action,'orbiting');assert.equal(result.direction,-1);
 const p=sent.at(-1);assert.ok(Math.abs(Math.hypot(p.x-5000,p.y-5000)-expected)<1e-6);
}
// Pick the less crowded side, then retain it when the risk disappears.
me.x=5450;me.y=5000;
state.npcs=[npc,{id:'crowd',x:5400,y:5200,hp:100}];renderer.__autoboxMove=null;
const safer=run({...request,action:'orbit',radius:450,rotate:true,direction:1});
assert.equal(safer.direction,-1);
state.npcs=[npc];renderer.__autoboxMove=null;
assert.equal(run({...request,action:'orbit',radius:450,rotate:true,direction:safer.direction}).direction,-1);
// Repeated movement around corner targets stays within playable bounds.
state.world={width:2000,height:2000};
for(const [x,y] of [[90,90],[1910,90],[90,1910],[1910,1910]]){
 npc.x=x;npc.y=y;me.x=1000;me.y=1000;let direction=1;
 for(let i=0;i<80;i++){
  renderer.__autoboxMove=null;
  const result=run({...request,action:'orbit',radius:450,rotate:true,direction});
  assert.equal(result.action,'orbiting');direction=result.direction;
  const p=sent.at(-1);assert.ok(p.x>=80&&p.y>=80&&p.x<=1920&&p.y<=1920);
  me.x=p.x;me.y=p.y;
 }
}
console.log('Adaptive radius, direction stability, NPC clearance and sustained corner motion passed.');
// Exploration has no NPC requirement, but cannot run during combat or leave bounds.
state.npcs=[];me.attacking=false;me.x=1000;me.y=1000;renderer.__autoboxMove=null;
assert.equal(run({...request,action:'roam',x:500,y:500}).action,'move_sent');
const sentBefore=sent.length;
assert.equal(run({...request,action:'roam',x:-20,y:500}).action,'blocked');
me.attacking=true;
assert.equal(run({...request,action:'roam',x:500,y:500}).action,'blocked');
me.attacking=false;me.hp=30;
assert.equal(run({...request,action:'roam',x:500,y:500}).action,'low_hp');
me.hp=100;
assert.equal(run({...request,action:'roam',map:'other',x:500,y:500}).action,'changed');
assert.equal(sent.length,sentBefore);
console.log('Exploration: no-NPC navigation, combat/HP/context and bounds guards passed.');

// Far targets do not silently cap a requested 800-unit stand-off at 550 units.
state.world={width:10000,height:10000};state.npcs=[npc];npc.x=5000;npc.y=5000;
me.x=7000;me.y=5000;me.hp=100;me.attacking=true;renderer.__autoboxMove=null;
assert.equal(run({...request,action:'approach',radius:800}).action,'move_sent');
assert.ok(Math.abs(Math.hypot(sent.at(-1).x-npc.x,sent.at(-1).y-npc.y)-800)<1e-6);
// Applying a new distance changes the next orbit destination in either direction.
for(const radius of [150,350,650,800,250]){
 renderer.__autoboxMove=null;
 assert.equal(run({...request,action:'orbit',radius,rotate:true,direction:1}).action,'orbiting');
 assert.ok(Math.abs(Math.hypot(sent.at(-1).x-npc.x,sent.at(-1).y-npc.y)-radius)<1e-6);
}
console.log('Configured radius survives approach, orbit and repeated distance changes.');
