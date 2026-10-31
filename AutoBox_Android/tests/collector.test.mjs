import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=fs.readFileSync(new URL('../app/src/main/assets/collector.js',import.meta.url),'utf8');
function fixture(){
  let time=10000;const calls=[],petCalls=[];
  const me={id:'ship',mapId:'3-2',respawnRevision:1,activeConfiguration:1,x:1000,y:1000,hp:100,maxHp:100,uridium:20,achievements:{counters:{bonusboxes:0}}};
  const s={me,time:1,map:{width:20000,height:12000},boxes:[{id:'a',revision:1,kind:'box',x:1300,y:1000},{id:'b',revision:1,kind:'box',x:3000,y:1000}]};
  const G={onFollow:p=>calls.push(['move',p]),onFollowCancel:()=>calls.push(['cancel']),isPingArmed:()=>false};
  let pet={action:'ready',active:true,mode:'petal1'};
  const env={window:{PeriodWindows:{renderer:{state:s}},DarkOrbitGroups:G,
    AutoBoxAndroidTarget:t=>{calls.push(['collect',t.id]);return {action:'collect'};},
    AutoBoxAndroidPet:t=>{petCalls.push(t);if(pet.action==='ready'&&['move','cruise'].includes(t.action))return {action:'move',destination:{x:2500,y:1000}};return pet;}},Date:{now:()=>time}};
  vm.createContext(env);vm.runInContext(source,env);const bot=env.window.AutoBoxAndroid;
  return {bot,s,me,calls,petCalls,G,env,clock:n=>time=n,pet:p=>pet=p,ready(mode='ship'){bot.start(mode);bot.tick();s.time++;time+=500;return bot.tick();}};
}
{
 const f=fixture();f.bot.start('ship');f.bot.tick();assert.equal(f.calls.filter(c=>c[0]==='collect').length,0);
 f.s.time++;f.clock(11000);assert.equal(f.bot.tick().running,true);
 assert.deepEqual(f.calls.filter(c=>c[0]==='collect').map(c=>c[1]),['a']);
 f.me.x=1300;f.s.time++;f.clock(14050);f.bot.tick();
 f.s.boxes.shift();f.me.achievements.counters.bonusboxes=1;f.s.time++;f.clock(14500);
 assert.equal(f.bot.tick().confirmed,1);assert.equal(f.calls.at(-1)[1],'b');
}
{
 const f=fixture();f.ready();const count=f.calls.length;f.bot.stop();f.s.time++;f.bot.tick();
 assert.equal(f.calls.length,count+1);assert.equal(f.calls.at(-1)[0],'cancel');
}
for(const mutation of [f=>f.me.hp=24,f=>f.me.deadUntil=10,f=>f.me.attacking=true,f=>f.me.secondaryVolley=true,f=>f.me.pendingJump=true,f=>f.me.mapId='1-1',f=>f.me.respawnRevision++,f=>f.me.id='other',f=>f.me.activeConfiguration=2]){
 const f=fixture();f.ready();mutation(f);f.s.time++;f.clock(11500);
 assert.equal(f.bot.tick().running,false);assert.equal(f.calls.at(-1)[0],'cancel');
}
{
 const f=fixture();f.ready();f.clock(20000);assert.equal(f.bot.tick().running,false);
}
{
 const f=fixture();f.s.boxes=[{id:'green',revision:1,kind:'booty',x:1200,y:1000},{id:'edge',revision:1,x:20,y:20}];
 f.ready();assert.equal(f.calls.filter(c=>c[0]==='collect').length,0);
 const move=f.calls.find(c=>c[0]==='move')[1];assert.ok(move.x>=80&&move.y>=80&&move.x<=19920&&move.y<=11920);
}
{
 const f=fixture();f.ready();f.s.boxes.shift();f.s.time++;f.clock(11500);
 assert.equal(f.bot.tick().confirmed,0); // Disappearance alone is not a collection proof.
}
{
 const f=fixture();f.pet({action:'sent',expected_active:true,active:false});f.ready('pet');
 f.pet({action:'snapshot',active:false,mode:'passive'});
 for(let i=0;i<4;i++){f.s.time++;f.clock(12000+i*500);f.bot.tick();}
 assert.equal(f.petCalls.filter(c=>c.action==='ensure').length,1);
 assert.equal(f.calls.filter(c=>c[0]==='collect').length,0);
 f.clock(33000);f.s.time++;assert.equal(f.bot.tick().running,false);
}
{
 const f=fixture();f.pet({action:'ready',active:true,mode:'petal1'});f.ready('pet');
 assert.equal(f.calls.filter(c=>c[0]==='collect').length,0);
 assert.ok(f.petCalls.some(c=>c.action==='move'));
}
// No attack/shop/repair/respawn integrations are included in this controller.
for(const command of ['onAttack','onBuy','repairRobot','pressCtrl','respawnOverlay'])assert.equal(source.includes(command),false);
console.log('Android collector: foreground controller, freshness, cancellation, context, HP, bounds, collection evidence and PET acknowledgement passed.');
