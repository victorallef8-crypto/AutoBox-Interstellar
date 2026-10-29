"""Coleta 2: somente o PET coleta; a nave recebe destinos sem cliques em objetos."""
import math
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
 if(t.action==='move'){
   const box=W.state.boxes?.find(b=>b.id===t.id&&b.revision===t.revision);
   if(!box)return {...result,action:'gone'};
   if(![undefined,null,'box','bonus'].includes(box.kind))throw Error('Somente boxes bônus na Coleta 2.');
   if(![box.x,box.y].every(finite)||Math.hypot(t.x-box.x,t.y-box.y)<300||Math.hypot(t.x-box.x,t.y-box.y)>400)
     throw Error('Destino deve ficar entre 300 e 400 unidades da box.');
 }
 const width=W.state.map?.width??W.state.world?.width,height=W.state.map?.height??W.state.world?.height;
 if(!finite(width)||!finite(height)||t.x<0||t.y<0||t.x>width||t.y>height)throw Error('Destino fora do mapa.');
 if(typeof G?.onFollow!=='function'||typeof G?.onFollowCancel!=='function'||G.isPingArmed?.())
   throw Error('Controle de movimento indisponível. Desative a marcação de grupo.');
 // Only a movement destination: never pointerdown, collectObject or collection endpoints.
 G.cancelFollow?.(false);
 G.onFollow({x:t.x,y:t.y,mapId:me.mapId});
 return {...result,action:'move'};
}"""


def approach_point(position, box, bounds=None):
    """Stay 350 units from the target, preferring the near side of the box."""
    x,y=box['x'],box['y']; dx=position[0]-x;dy=position[1]-y
    length=math.hypot(dx,dy)
    if not all(math.isfinite(v) for v in (*position,x,y)):
        raise ValueError('Coordenadas inválidas.')
    if length==0:dx,dy,length=1,0,1
    near=(x+350*dx/length,y+350*dy/length)
    candidates=[near,(x+350,y),(x-350,y),(x,y+350),(x,y-350)]
    # A known map rectangle is mandatory: never guess its limits.
    if not bounds or len(bounds)!=4 or not all(type(v) in (int,float) and math.isfinite(v) for v in bounds):raise ValueError('Limites do mapa indisponíveis.')
    lo_x,lo_y,hi_x,hi_y=bounds
    valid=[p for p in candidates if lo_x<=p[0]<=hi_x and lo_y<=p[1]<=hi_y]
    if not valid:raise ValueError('Não há aproximação válida para esta box.')
    return min(valid,key=lambda p:math.dist(position,p))


def orbit_point(position, center, bounds):
    # Advance around the collection area, selecting a point inside the real map.
    if not bounds or len(bounds)!=4 or not all(type(v) in (int,float) and math.isfinite(v) for v in bounds):
        raise ValueError('Limites do mapa indisponíveis.')
    angle=math.atan2(position[1]-center[1],position[0]-center[0])
    for i in range(16):
        theta=angle+math.pi/3+i*math.pi/8
        point=(center[0]+350*math.cos(theta),center[1]+350*math.sin(theta))
        if bounds[0]<=point[0]<=bounds[2] and bounds[1]<=point[1]<=bounds[3] and math.dist(position,point)>120:
            return point
    raise ValueError('Sem espaço para continuar o voo nesta área.')


class PetCollector:
    def __init__(self,session,stop_event,emit,clock=None,settings=None):
        self.session=session;self.stop=stop_event;self.emit=emit
        self.clock=clock or time.monotonic;self.settings=settings or {};self.identity={}
        self.error=None;self.target=None;self.deferred={};self.pending=None;self.last_move=0
        self.waypoint=None;self.cruise_center=None;self.wait_since=None;self.best=float('inf');self.progress=0
        self.last_status=None
        self.cloak=CloakKeeper(session,stop_event,emit,self.clock) if self.settings.get('cloak') else None
    def status(self,text):
        if text!=self.last_status:self.emit('status',text);self.last_status=text
    def request(self,action,**extra):
        return self.session.request('pet_collect',dict(self.identity,action=action,**extra),
                                    allowed=lambda:not self.stop.is_set())
    def step(self,snapshot,now):
        if not snapshot.get('fresh') or snapshot.get('dead') or (snapshot.get('hp_percent') or 0)<=25:
            raise ValueError('Dados atuais e nave com mais de 25% de vida são necessários.')
        if self.identity and (snapshot['map']!=self.identity['map'] or snapshot.get('respawn_revision')!=self.identity['life']):
            raise ValueError('Mapa ou vida mudou. Reinicie a Coleta 2.')
        if self.cloak:self.cloak.step()
        pet=self.request('inspect' if self.pending else 'ensure')
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
        self.deferred={k:v for k,v in self.deferred.items() if v>now}
        key=lambda b:(b['id'],b.get('revision'))
        position=snapshot['position']
        size=snapshot.get('map_size')
        bounds=(0,0,*size) if size and len(size)==2 else None
        if not bounds or not all(type(v) in (int,float) and math.isfinite(v) and v>=0 for v in bounds):
            raise ValueError('Limites do mapa indisponíveis.')
        old_key=key(self.target) if self.target else None
        if self.target:
            self.target=next((b for b in boxes if key(b)==old_key),None)
        if self.target and math.dist(position,(self.target['x'],self.target['y']))<=450:
            # Visit other boxes while the PET works; revisit later if still present.
            self.deferred.setdefault(key(self.target),now+8)
            alternatives=[b for b in boxes if key(b) not in self.deferred]
            if alternatives:self.target=min(alternatives,key=lambda b:math.dist(position,(b['x'],b['y'])))
        if self.target is None:
            available=[b for b in boxes if key(b) not in self.deferred]
            if available:self.target=min(available,key=lambda b:math.dist(position,(b['x'],b['y'])))
        new_key=key(self.target) if self.target else None
        if new_key!=old_key:
            self.best=float('inf');self.progress=now;self.last_move=-float('inf');self.waypoint=None
        if self.target:
            center=(self.target['x'],self.target['y'])
            self.cruise_center=center
            d=math.dist(position,center)
            if d<self.best-10:self.best=d;self.progress=now
            if d>450 and now-self.progress>15:
                self.deferred[key(self.target)]=now+30;self.target=None;self.waypoint=None
                self.status('Aproximação sem progresso; continuando o voo para outra área.')
            elif d>450:
                if now-self.last_move>=2:
                    point=approach_point(position,self.target,bounds)
                    self.request('move',id=self.target['id'],revision=self.target.get('revision'),x=point[0],y=point[1])
                    self.waypoint=point;self.last_move=now
                self.status('Coleta 2: passando próximo às boxes para o PET coletar.')
                return
        speed=snapshot.get('speed')
        lead=max(120,min(250,speed*.75)) if type(speed) in (int,float) and math.isfinite(speed) and speed>0 else 200
        # Replace a nearby destination before the ship reaches it; never stop to wait for a box.
        if self.waypoint is not None and math.dist(position,self.waypoint)>lead and now-self.last_move<2:
            return
        if self.target:
            center=(self.target['x'],self.target['y'])
            point=orbit_point(position,center,bounds)
            self.request('move',id=self.target['id'],revision=self.target.get('revision'),x=point[0],y=point[1])
        else:
            center=self.cruise_center or position
            # Keep the empty-area circuit inside the map, including corners.
            center=(max(350,min(size[0]-350,center[0])),max(350,min(size[1]-350,center[1])))
            point=orbit_point(position,center,bounds)
            self.request('cruise',x=point[0],y=point[1])
        self.waypoint=point;self.last_move=now
        self.status('Coleta 2: voo contínuo enquanto o PET coleta e procura boxes.')
    def run(self):
        self.emit('running',True)
        try:
            while not self.stop.is_set():
                self.step(self.session.get_world_snapshot(),self.clock())
                if self.stop.wait(.25):break
        except Exception as exc:
            self.error=str(exc);self.status('Coleta 2 parada: '+str(exc))
        finally:
            # One explicit stop is allowed after cancellation; no further flight/PET actions.
            try:
                if self.identity:self.session.request('pet_collect',dict(self.identity,action='stop'),timeout=3)
            except Exception:pass
            self.stop.set();self.emit('running',False)
