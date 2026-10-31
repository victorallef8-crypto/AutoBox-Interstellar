(t => {
 const W=window.PeriodWindows,S=window.DarkOrbitServices,G=window.DarkOrbitGroups;
 const me=W?.state?.me,p=me?.pet,gear=S?.items?.petal1;
 if(W?.readOnly||!me||!p)throw Error('PET indisponível.');
 const finite=v=>typeof v==='number'&&Number.isFinite(v);
 if(t.owner!==undefined&&(t.owner!==me.id||t.life!==me.respawnRevision||t.map!==me.mapId||t.configuration!==me.activeConfiguration))
   throw Error('Conta, mapa, vida ou configuração mudou. Reinicie a Coleta 2.');
 if(!finite(me.x)||!finite(me.y)||!finite(me.hp)||me.hp<=0||me.deadUntil)throw Error('Nave indisponível.');
 const result={owner:me.id,life:me.respawnRevision,map:me.mapId,configuration:me.activeConfiguration,
   active:p.active,mode:p.mode,level:p.level,fuel:p.fuel,hp:p.hp};
 if(t.action==='stop'){
   if(typeof G?.onFollowCancel!=='function')throw Error('Parada da nave indisponível.');
   G.onFollowCancel();return {...result,action:'stopped'};
 }
 if(!finite(me.maxHp)||me.maxHp<=0||me.hp/me.maxHp<=.25)throw Error('Recupere a vida da nave.');
 if(![1,2].includes(me.activeConfiguration)||typeof p.active!=='boolean'||!finite(p.level)||p.level<2||
    !finite(p.hp)||p.hp<=0||!finite(p.fuelRate)||p.fuelRate<=0||!finite(p.fuel)||p.fuel<p.fuelRate)
   throw Error('Confira vida, nível e combustível do PET. Nenhuma compra ou reparo automático.');
 const gears=p.configurations?.[me.activeConfiguration-1]?.gears;
 if(!Array.isArray(gears)||!gears.includes('petal1')||gear?.petGear!==true||gear.family!=='al'||gear.tier!==1||
    gear.implemented===false||!finite(gear.minLevel)||p.level<gear.minLevel||!finite(gear.value)||gear.value<700)
   throw Error('Equipe o módulo Auto-looter nível 1 na configuração ativa do PET.');
 if(me.attacking||me.secondaryVolley||me.pendingJump)throw Error('Interrompa o combate ou salto antes da Coleta 2.');
 if(t.action==='inspect')return {...result,action:p.active&&p.mode==='petal1'?'ready':'snapshot'};
 if(W.petPending||W.equipPending||p.tradeRemaining>0)return {...result,action:'wait'};
 if(t.action==='ensure'){
   if(typeof W.petRequest!=='function')throw Error('Controle do PET indisponível.');
   if(!p.active){void W.petRequest({action:'launch'});return {...result,action:'sent',expected_active:true};}
   if(p.mode==='petal1')return {...result,action:'ready'};
   if((p.gearCooldowns?.al||0)>0)return {...result,action:'wait'};
   void W.petRequest({action:'mode',mode:'petal1'});
   return {...result,action:'sent',expected_active:true,expected_mode:'petal1'};
 }
 if(!['move','cruise'].includes(t.action)||!p.active||p.mode!=='petal1')throw Error('PET não está pronto para coletar.');
 if(![t.x,t.y].every(finite))throw Error('Destino inválido.');
 const width=W.state.map?.width??W.state.world?.width,height=W.state.map?.height??W.state.world?.height;
 if(!finite(width)||!finite(height)||width<=0||height<=0)throw Error('Limites do mapa indisponíveis.');
 let x=t.x,y=t.y;
 if(t.action==='move'){
   const box=W.state.boxes?.find(b=>b.id===t.id&&b.revision===t.revision);
   if(!box)return {...result,action:'gone'};
   if(![undefined,null,'box','bonus'].includes(box.kind))throw Error('Somente boxes bônus na Coleta 2.');
   if(![box.x,box.y].every(finite))throw Error('Coordenadas da box indisponíveis.');
   const dx=box.x-me.x,dy=box.y-me.y,length=Math.hypot(dx,dy);
   if(length<1)return {...result,action:'passed'};
   // Compute from the live ship position, not a delayed Python snapshot after a turn.
   const ux=dx/length,uy=dy/length;let runout=1200;
   for(const [value,unit,low,high] of [[box.x,ux,40,width-40],[box.y,uy,40,height-40]]){
     if(unit>0)runout=Math.min(runout,(high-value)/unit);
     else if(unit<0)runout=Math.min(runout,(low-value)/unit);
   }
   if(runout<300)return {...result,action:'blocked'};
   x=box.x+ux*runout;y=box.y+uy*runout;
 }
 if(x<0||y<0||x>width||y>height)throw Error('Destino fora do mapa.');
 if(typeof G?.onFollow!=='function'||typeof G?.onFollowCancel!=='function'||G.isPingArmed?.())
   throw Error('Controle de movimento indisponível. Desative a marcação de grupo.');
 // Only a movement destination: never pointerdown, collectObject or collection endpoints.
 G.cancelFollow?.(false);
 G.onFollow({x,y,mapId:me.mapId});
 return {...result,action:'move',destination:{x,y}};
})
