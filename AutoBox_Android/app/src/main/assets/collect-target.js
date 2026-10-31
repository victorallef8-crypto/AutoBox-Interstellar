((target) => {
 const r=window.PeriodWindows?.renderer, groups=window.DarkOrbitGroups;
 const canvas=document.getElementById('space');
 if(!r || !canvas || typeof r.worldAt!=='function' || typeof r.hitBonusBox!=='function' || typeof groups?.onFollow!=='function')
   throw Error('Integração do cliente indisponível. Entre no mapa novamente.');
 if(groups.isPingArmed?.()) throw Error('Desative a marcação de grupo antes de coletar.');
 const rect=canvas.getBoundingClientRect(), cx=rect.left+rect.width/2, cy=rect.top+rect.height/2;
 if(rect.width<=0||rect.height<=0) throw Error('Canvas do jogo indisponível.');
 const a=r.worldAt(cx,cy), b=r.worldAt(cx+10,cy), c=r.worldAt(cx,cy+10);
 const xx=(b.x-a.x)/10, xy=(c.x-a.x)/10, yx=(b.y-a.y)/10, yy=(c.y-a.y)/10;
 const det=xx*yy-xy*yx;
 if(![a.x,a.y,xx,xy,yx,yy,det].every(Number.isFinite)||Math.abs(det)<1e-8) throw Error('Projeção do mapa indisponível.');
 const dx=target.x-a.x, dy=target.y-a.y;
 const px=cx+(dx*yy-dy*xy)/det, py=cy+(dy*xx-dx*yx)/det;
 if(!Number.isFinite(px)||!Number.isFinite(py)) throw Error('Projeção inválida.');
 const projected=r.worldAt(px,py);
 if(!projected||!Number.isFinite(projected.x)||!Number.isFinite(projected.y)||Math.hypot(projected.x-target.x,projected.y-target.y)>.5) throw Error('Projeção do cliente mudou. Coleta pausada.');
 for(const [ox,oy] of [[0,0],[0,-4],[0,4],[-4,0],[4,0]]) {
   const x=px+ox,y=py+oy;
   if(x<rect.left+2||x>=rect.right-2||y<rect.top+2||y>=rect.bottom-2) continue;
   const hit=r.hitBonusBox(x,y);
   if(!hit||hit.id!==target.id||hit.revision!==target.revision||(hit.kind==='booty'&&!target.allow_green)) continue;
   if(r.hitTarget?.(x,y)||r.hitWorldButton?.(x,y)) continue;
   if(!target.can_collect) return {action:'wait'};
   canvas.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,buttons:1,
       pointerId:9381,pointerType:'mouse',clientX:x,clientY:y}));
   return {action:'collect',id:hit.id,revision:hit.revision};
 }
 if(!target.can_move) return {action:'wait'};
 groups.onFollow({x:target.x,y:Math.max(0,target.y-120),mapId:target.map});
 return {action:'move',id:target.id,revision:target.revision};
})
