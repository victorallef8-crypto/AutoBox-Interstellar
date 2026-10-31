"""Coleta 2: somente o PET coleta; a nave recebe destinos sem cliques em objetos."""
import math
import random
import time
from controller import CloakKeeper

PET_COLLECT_SCRIPT = r"""t => {
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
}"""


def approach_point(position, box, bounds=None):
    """Destination beyond the box, on the same line, with room to keep flying."""
    if not bounds or len(bounds)!=4 or not all(type(v) in (int,float) and math.isfinite(v) for v in bounds):
        raise ValueError('Limites do mapa indisponíveis.')
    x,y=box['x'],box['y'];dx=x-position[0];dy=y-position[1];length=math.hypot(dx,dy)
    if not all(math.isfinite(v) for v in (*position,x,y)) or length<1:
        raise ValueError('Box já alcançada ou coordenadas inválidas.')
    ux,uy=dx/length,dy/length;runout=1200
    for value,unit,low,high in ((x,ux,bounds[0]+40,bounds[2]-40),(y,uy,bounds[1]+40,bounds[3]-40)):
        if unit>0:runout=min(runout,(high-value)/unit)
        elif unit<0:runout=min(runout,(low-value)/unit)
    if runout<300:raise ValueError('Sem espaço depois da box para atravessar em voo contínuo.')
    return (x+ux*runout,y+uy*runout)


def random_patrol_point(position, size, rng):
    """Choose an interior destination, favoring distance over short reversals."""
    if len(size)!=2 or not all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in size):
        raise ValueError('Limites do mapa indisponíveis.')
    width,height=size; margin=min(250,width/4,height/4)
    points=[(rng.uniform(margin,width-margin),rng.uniform(margin,height-margin)) for _ in range(12)]
    minimum=min(1800,min(size)*.4)
    distant=[point for point in points if math.dist(position,point)>=minimum]
    return rng.choice(distant) if distant else max(points,key=lambda point:math.dist(position,point))


def segment_distance(point, start, end):
    """Closest approach during the actual movement between two readings."""
    dx,dy=end[0]-start[0],end[1]-start[1]
    length2=dx*dx+dy*dy
    fraction=0 if length2==0 else max(0,min(1,((point[0]-start[0])*dx+(point[1]-start[1])*dy)/length2))
    return math.dist(point,(start[0]+fraction*dx,start[1]+fraction*dy))


class PetCollector:
    def __init__(self,session,stop_event,emit,clock=None,settings=None,rng=None):
        self.session=session;self.stop=stop_event;self.emit=emit
        self.clock=clock or time.monotonic;self.settings=settings or {};self.identity={}
        self.error=None;self.target=None;self.passed=set();self.deferred={};self.pending=None;self.last_move=-float('inf')
        self.waypoint=None;self.wait_since=None;self.best=float('inf');self.progress=0
        self.rng=rng if rng is not None else random.Random()
        self.patrol_goal=None;self.patrol_size=None
        self.flight_goal=None;self.flight_origin=None;self.flight_progress=0
        self.flight_amplitude=0;self.flight_waves=1
        self.pass_heading=None
        self.previous_position=None
        self.last_status=None;self.last_pet=None;self.pet_checked=-float('inf');self.command_latency=0
        self.cloak=CloakKeeper(session,stop_event,emit,self.clock) if self.settings.get('cloak') else None
    def status(self,text):
        if text!=self.last_status:self.emit('status',text);self.last_status=text
    def request(self,action,**extra):
        started=self.clock()
        record=getattr(self.session,'record_pet_diagnostic',None)
        try:
            result=self.session.request('pet_collect',dict(self.identity,action=action,**extra),
                                        allowed=lambda:not self.stop.is_set())
        except Exception as exc:
            if record:record(action,error=str(exc))
            raise
        if record:record(action,result=result)
        self.command_latency=max(self.clock()-started,self.command_latency*.9)
        return result
    def flight_point(self,position,goal,size,lead,straight_distance=1500):
        """Follow one stable wave per leg; no fresh random steering each tick.

        Blend back onto the direct approach for the final 1500 world units.
        """
        if self.flight_goal!=goal:
            self.flight_goal=goal;self.flight_origin=position;self.flight_progress=0
            length=math.dist(position,goal)
            self.flight_amplitude=self.rng.uniform(100,220)*self.rng.choice((-1,1))
            self.flight_amplitude*=min(1,length/2000)
            self.flight_waves=self.rng.uniform(1,2)
        origin=self.flight_origin
        dx,dy=goal[0]-origin[0],goal[1]-origin[1];length=math.hypot(dx,dy)
        if length<1:return goal
        projected=((position[0]-origin[0])*dx+(position[1]-origin[1])*dy)/length
        self.flight_progress=max(self.flight_progress,projected)
        along=min(length,self.flight_progress+max(600,lead*1.5))
        t=max(0,along/length)
        taper=min(1,max(0,(length-along-straight_distance)/700))
        offset=self.flight_amplitude*math.sin(2*math.pi*self.flight_waves*t)*math.sin(math.pi*t)*taper
        x=origin[0]+dx*t-dy/length*offset
        y=origin[1]+dy*t+dx/length*offset
        margin=min(40,min(size)/4)
        return (max(margin,min(size[0]-margin,x)),max(margin,min(size[1]-margin,y)))

    def step(self,snapshot,now):
        if not snapshot.get('fresh') or snapshot.get('dead') or (snapshot.get('hp_percent') or 0)<=25:
            raise ValueError('Dados atuais e nave com mais de 25% de vida são necessários.')
        if self.identity and (snapshot['map']!=self.identity['map'] or snapshot.get('respawn_revision')!=self.identity['life']):
            raise ValueError('Mapa ou vida mudou. Reinicie a Coleta 2.')
        if self.cloak:self.cloak.step()
        if self.pending or self.last_pet is None or now-self.pet_checked>=1:
            pet=self.request('inspect' if self.pending else 'ensure')
            self.last_pet=pet;self.pet_checked=now
        else:pet=self.last_pet
        if not pet or pet.get('action')=='cancelled':return
        if not self.identity:self.identity={k:pet[k] for k in ('owner','life','map','configuration')}
        if pet['action']=='sent':self.pending=(now,pet)
        if self.pending:
            started,expected=self.pending
            if pet['action']!='sent' and pet.get('active')==expected['expected_active'] and (
                    'expected_mode' not in expected or pet.get('mode')==expected['expected_mode']):self.pending=None
            elif now-started>=15:raise ValueError('PET sem confirmação. Confira no jogo antes de reiniciar.')
            self.status('Aguardando confirmação de ativação/modo do PET.');return
        if pet['action']!='ready':
            if self.wait_since is None:self.wait_since=now
            if now-self.wait_since>30:raise ValueError('PET não ficou pronto em 30 segundos.')
            self.status('Aguardando PET ficar pronto.');return
        self.wait_since=None
        boxes=[b for b in snapshot.get('candidates',[]) if b.get('kind') in (None,'box','bonus')]
        key=lambda b:(b['id'],b.get('revision'))
        position=snapshot['position']
        previous_position=self.previous_position or position
        self.previous_position=position
        size=snapshot.get('map_size')
        if not size or len(size)!=2:raise ValueError('Limites do mapa indisponíveis.')
        bounds=(0,0,*size)
        speed=snapshot.get('speed')
        age=snapshot.get('age',0)
        age=age if type(age) in (int,float) and math.isfinite(age) and age>=0 else 0
        velocity=speed if type(speed) in (int,float) and math.isfinite(speed) and speed>0 else 400
        lead=min(max(80,min(size)/4),max(350,min(1200,velocity*(age+2*self.command_latency+.85))))
        # Cross the box before releasing it; do not switch destinations on approach.
        old_key=key(self.target) if self.target else None
        if self.target and self.pass_heading:
            px,py=position[0]-self.target['x'],position[1]-self.target['y']
            if (px*self.pass_heading[0]+py*self.pass_heading[1]>=0 and
                    segment_distance((self.target['x'],self.target['y']),previous_position,position)<=120):
                self.passed.add(old_key)
        self.deferred={k:until for k,until in self.deferred.items() if until>now}
        self.passed.update(key(b) for b in boxes if math.dist(position,(b['x'],b['y']))<1)
        if self.target:
            self.target=next((b for b in boxes if key(b)==old_key and key(b) not in self.passed),None)
        if self.target is None:
            # Use every reported bonus box, nearest first; the patrol is a fallback.
            available=sorted((b for b in boxes if key(b) not in self.passed and key(b) not in self.deferred),
                             key=lambda b:math.dist(position,(b['x'],b['y'])))
            for box in available:
                try:approach_point(position,box,bounds)
                except ValueError:
                    self.deferred[key(box)]=now+10
                    continue
                self.target=box
                break
        new_key=key(self.target) if self.target else None
        force_move=new_key!=old_key
        if force_move:
            self.best=float('inf');self.progress=now;self.waypoint=None
            self.pass_heading=None
            self.flight_goal=None
            if self.target:
                dx,dy=self.target['x']-position[0],self.target['y']-position[1]
                length=math.hypot(dx,dy)
                if length>0:self.pass_heading=(dx/length,dy/length)
        if self.target:
            d=math.dist(position,(self.target['x'],self.target['y']))
            if d<self.best-10:self.best=d;self.progress=now
            if now-self.progress>15:
                self.deferred[key(self.target)]=now+30;self.target=None;force_move=True
            else:
                try:point=approach_point(position,self.target,bounds)
                except ValueError:
                    self.deferred[key(self.target)]=now+10;self.target=None;force_move=True
                    point=None
                curved=d>max(1500,lead*2)
                if point is not None and curved:
                    point=self.flight_point(position,(self.target['x'],self.target['y']),size,lead)
                if point is not None and (force_move or now-self.last_move>=.5 or (self.waypoint and math.dist(position,self.waypoint)<=lead)):
                    if curved:
                        result=self.request('cruise',x=point[0],y=point[1])
                    else:
                        result=self.request('move',id=self.target['id'],revision=self.target.get('revision'),x=point[0],y=point[1])
                    if result and result.get('action') in ('gone','blocked','passed'):
                        if result['action']=='passed':self.passed.add(key(self.target))
                        else:self.deferred[key(self.target)]=now+(10 if result['action']=='blocked' else 2)
                        self.target=None;force_move=True;point=None
                    else:
                        dest=(result or {}).get('destination')
                        self.waypoint=(dest['x'],dest['y']) if dest else point
                        self.last_move=now
                if point is not None:
                    self.status('Coleta 2: aproximando em curva suave.' if curved else 'Coleta 2: atravessando a box em voo contínuo, sem coletar com a nave.')
                    return
        # Empty area: a new interior destination, never a fixed sweep or grid.
        if (self.patrol_goal is None or self.patrol_size!=tuple(size) or
                math.dist(position,self.patrol_goal)<=max(lead*1.5,600)):
            self.patrol_goal=random_patrol_point(position,size,self.rng)
            self.patrol_size=tuple(size)
            self.flight_goal=None
        route_point=self.flight_point(position,self.patrol_goal,size,lead,straight_distance=0)
        if (force_move or self.waypoint is None or now-self.last_move>=.5 or snapshot.get('moving') is False or
                math.dist(position,self.waypoint)<=lead):
            self.request('cruise',x=route_point[0],y=route_point[1])
            self.waypoint=route_point;self.last_move=now
        self.status('Coleta 2: explorando por destinos variados e curvas suaves.')
    def run(self):
        record=getattr(self.session,'record_pet_diagnostic',None)
        if record:record('start')
        self.emit('running',True)
        try:
            while not self.stop.is_set():
                self.step(self.session.get_world_snapshot(),self.clock())
                if self.stop.wait(.1):break
        except Exception as exc:
            self.error=str(exc)
            if record:record('worker',error=str(exc))
            self.status('Coleta 2 parada: '+str(exc))
        finally:
            # One explicit stop is allowed after cancellation; no further flight/PET actions.
            try:
                if self.identity:self.session.request('pet_collect',dict(self.identity,action='stop'),timeout=3)
            except Exception:pass
            if record:record('end',result={'action':'error' if self.error else 'cancelled'})
            self.stop.set();self.emit('running',False)

