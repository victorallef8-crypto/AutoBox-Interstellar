from pathlib import Path
import os
import queue
import threading
import math
import json
import re
import time
from urllib.parse import urlsplit

NPC_SCRIPT = "t => {\n const r=window.PeriodWindows?.renderer, s=r?.state, canvas=document.getElementById('space');\n if(!s?.me||!canvas||typeof r.worldAt!=='function'||typeof r.hitTarget!=='function')\n   throw Error('Cliente de combate indispon\u00edvel.');\n if(s.me.mapId!==t.map||s.me.respawnRevision!==t.life) return {action:'changed'};\n const npc=s.npcs?.find(n=>String(n.id)===String(t.id)&&n.respawnRevision===t.revision);\n const active=s.me.attacking===true;\n const pressCtrl=()=>{canvas.focus({preventScroll:true});\n   for(const type of ['keydown','keyup']) canvas.dispatchEvent(new KeyboardEvent(type,\n     {bubbles:true,cancelable:true,code:'ControlLeft',key:'Control',ctrlKey:type==='keydown'}));};\n function select(allowOffscreen=false){\n   if(!npc||npc.hp<=0) return false;\n   const rect=canvas.getBoundingClientRect(),cx=rect.left+rect.width/2,cy=rect.top+rect.height/2;\n   const a=r.worldAt(cx,cy),b=r.worldAt(cx+10,cy),c=r.worldAt(cx,cy+10);\n   const xx=(b.x-a.x)/10,xy=(c.x-a.x)/10,yx=(b.y-a.y)/10,yy=(c.y-a.y)/10,det=xx*yy-xy*yx;\n   if(![a.x,a.y,xx,xy,yx,yy,det].every(Number.isFinite)||Math.abs(det)<1e-8) return false;\n   const dx=npc.x-a.x,dy=npc.y-a.y,px=cx+(dx*yy-dy*xy)/det,py=cy+(dy*xx-dx*yx)/det;\n   for(const [ox,oy] of [[0,0],[0,-4],[0,4],[-4,0],[4,0]]){\n     const x=px+ox,y=py+oy;\n     if(!allowOffscreen&&(x<rect.left+2||x>=rect.right-2||y<rect.top+2||y>=rect.bottom-2)) continue;\n     const hit=r.hitTarget(x,y),point=r.worldAt(x,y);\n     if(!hit||String(hit.id)!==String(npc.id)||(hit.respawnRevision!==undefined&&hit.respawnRevision!==npc.respawnRevision)||\n        r.hitWorldButton?.(x,y)||!Number.isFinite(point?.x)||!Number.isFinite(point?.y)) continue;\n     canvas.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,button:2,buttons:2,clientX:x,clientY:y}));\n     return true;\n   }\n   return false;\n }\n if(t.action==='stop'){\n   if(select(true)) return {action:'stop_sent'};\n   if(!npc&&!active) return {action:'stopped'};\n   return {action:'stop_unavailable'};\n }\n if(t.action==='retreat'){\n   if(s.me.deadUntil||s.me.hp<=0||active||s.me.secondaryVolley) return {action:'blocked'};\n   const gates=(s.map?.gates||[]).filter(g=>!g.galaxy&&Number.isFinite(g.x)&&Number.isFinite(g.y)&&typeof g.to==='string');\n   const gate=t.gate?gates.find(g=>g.id===t.gate):gates.sort((a,b)=>Math.hypot(a.x-s.me.x,a.y-s.me.y)-Math.hypot(b.x-s.me.x,b.y-s.me.y))[0];\n   if(!gate||typeof window.DarkOrbitGroups?.onFollow!=='function') return {action:'no_portal'};\n   const d=Math.hypot(gate.x-s.me.x,gate.y-s.me.y);\n   if(d>80) window.DarkOrbitGroups.onFollow({x:gate.x,y:gate.y,mapId:s.me.mapId});\n   let repair=s.me.repairing?'enabled':'waiting';\n   if(t.enable_repair&&!s.me.repairing){\n     const button=document.getElementById('repairButton');\n     if(!window.DarkOrbitStarter?.repairRobot?.(s.me.loadout)||!button) repair='unavailable';\n     else {button.click();repair='sent';}\n   }\n   return {action:'retreating',gate:gate.id,distance:d,repair};\n }\n if(s.me.deadUntil||s.me.hp<=0||!s.me.maxHp||s.me.hp/s.me.maxHp*100<=t.min_hp)\n   return {action:'low_hp'};\n if(!npc||npc.hp<=0) return {action:'gone'};\n if(window.DarkOrbitGroups?.isPingArmed?.()) throw Error('Desative a marca\u00e7\u00e3o de grupo.');\n if(t.action==='select') return {action:select()?'select_sent':'not_visible'};\n const d=Math.hypot(npc.x-s.me.x,npc.y-s.me.y);\n if(t.action==='approach'){\n   if(typeof window.DarkOrbitGroups?.onFollow!=='function'||!Number.isFinite(d)) throw Error('Movimento indispon\u00edvel.');\n   const stand=t.close_approach===true?60:450;\n   if(d<=(t.close_approach===true?80:520)) return {action:'in_range'};\n   const x=npc.x+(s.me.x-npc.x)*stand/d, y=npc.y+(s.me.y-npc.y)*stand/d;\n   if(x<0||y<0||x>s.world.width||y>s.world.height) return {action:'blocked'};\n   window.DarkOrbitGroups.onFollow({x,y,mapId:s.me.mapId});\n   return {action:'move_sent'};\n }\n if(t.action==='orbit'){\n   if(String(s.me.targetId)!==String(npc.id)||!active) return {action:'not_attacking'};\n   if(typeof window.DarkOrbitGroups?.onFollow!=='function') return {action:'blocked'};\n   const radius=Math.max(150,Math.min(500,Number(t.radius)||450));\n   const angle=Math.atan2(s.me.y-npc.y,s.me.x-npc.x);\n   const margin=80, candidates=[];\n   for(const direction of [t.direction===-1?-1:1,t.direction===-1?1:-1]){\n     const a=angle+direction*.35, x=npc.x+Math.cos(a)*radius,y=npc.y+Math.sin(a)*radius;\n     if(x<margin||y<margin||x>s.world.width-margin||y>s.world.height-margin) continue;\n     let clearance=2000;\n     for(const other of s.npcs||[]){\n       if(other.id===npc.id||other.hp<=0) continue;\n       for(const f of [.25,.5,.75,1]) clearance=Math.min(clearance,Math.hypot(s.me.x+(x-s.me.x)*f-other.x,s.me.y+(y-s.me.y)*f-other.y));\n     }\n     candidates.push({x,y,direction,clearance});\n   }\n   if(!candidates.length) return {action:'blocked'};\n   let chosen=candidates[0];\n   if(candidates[1]&&candidates[1].clearance>chosen.clearance+100) chosen=candidates[1];\n   window.DarkOrbitGroups.onFollow({x:chosen.x,y:chosen.y,mapId:s.me.mapId});\n   return {action:'orbiting',direction:chosen.direction,radius};\n }\n if(String(s.me.targetId)!==String(npc.id)) return {action:'not_selected'};\n if(t.action==='attack'){\n   if(d>550) return {action:'out_of_range'};\n   if(s.me.selectedAmmo!=='lcb10') throw Error('Selecione LCB-10 no jogo antes de iniciar.');\n   if(!(s.me.ammunitionStock?.lcb10??s.me.ammo)) throw Error('Muni\u00e7\u00e3o LCB-10 esgotada.');\n   if(active) return {action:'attacking'};\n   pressCtrl();return {action:'attack_sent'};\n }\n throw Error('A\u00e7\u00e3o de combate desconhecida.');\n}"

TRAVEL_SCRIPT = "async t => {\n const renderer=window.PeriodWindows?.renderer;\n const s=renderer?.state, nav=window.DarkOrbitNavigation, model=window.DarkOrbitStarSystemModel;\n if(!s?.me||!s.map||typeof model?.courseState!=='function'||typeof nav?.course!=='function'||typeof nav?.jump!=='function')\n   throw Error('Navegação do cliente indisponível. Exporte a integração atual em Avançado.');\n if(s.me.mapId!==t.map||s.me.respawnRevision!==t.respawn_revision) return {action:'wait'};\n if(s.me.deadUntil||s.me.hp<=0||!s.me.maxHp||s.me.hp/s.me.maxHp<=.25) return {action:'blocked',reason:'Recupere a vida antes de viajar.'};\n if(s.me.attacking||s.me.secondaryVolley) return {action:'blocked',reason:'Pare o ataque antes de viajar.'};\n if(s.me.pendingJump) return {action:'wait'};\n if(s.me.mapId===t.destination) return {action:'arrived',map:s.me.mapId};\n const course=model.courseState(s,t.destination);\n if(!course||course.disabled||!course.nextGate)\n   return {action:'blocked',reason:String(course?.reason||'Nenhuma rota permitida para esse mapa.').slice(0,180)};\n const gate=s.map.gates?.find(g=>g.id===course.nextGate.id);\n if(!gate||gate.galaxy||!Number.isFinite(gate.x)||!Number.isFinite(gate.y)||typeof gate.to!=='string')\n   return {action:'blocked',reason:'Portal normal da rota não confirmado.'};\n const access=window.DarkOrbitMaps?.access?.(gate.to,s.me);\n if(!access?.allowed) return {action:'blocked',reason:String(access?.reason||'Acesso ao próximo mapa não confirmado.').slice(0,180)};\n const distance=Math.hypot(gate.x-s.me.x,gate.y-s.me.y);\n if(!Number.isFinite(distance)) throw Error('Posição indisponível.');\n const result={action:'route',map:s.me.mapId,next_map:gate.to,gate:gate.id,distance};\n if(!t.execute) return result;\n if(distance<=80){await nav.jump(gate.id);return {...result,action:'jump'};}\n nav.course(t.destination);\n return {...result,action:'move'};\n}"

HOME_URL = "https://interstellar-verse.com/"
GAME_URL = "https://interstellar-verse.com/play/#play"

DATA_TARGET_SCRIPT = "(target) => {\n const r=window.PeriodWindows?.renderer, groups=window.DarkOrbitGroups;\n const canvas=document.getElementById('space');\n if(!r || !canvas || typeof r.worldAt!=='function' || typeof r.hitBonusBox!=='function' || typeof groups?.onFollow!=='function')\n   throw Error('Integração do cliente indisponível. Entre no mapa novamente.');\n if(groups.isPingArmed?.()) throw Error('Desative a marcação de grupo antes de coletar.');\n const rect=canvas.getBoundingClientRect(), cx=rect.left+rect.width/2, cy=rect.top+rect.height/2;\n if(rect.width<=0||rect.height<=0) throw Error('Canvas do jogo indisponível.');\n const a=r.worldAt(cx,cy), b=r.worldAt(cx+10,cy), c=r.worldAt(cx,cy+10);\n const xx=(b.x-a.x)/10, xy=(c.x-a.x)/10, yx=(b.y-a.y)/10, yy=(c.y-a.y)/10;\n const det=xx*yy-xy*yx;\n if(![a.x,a.y,xx,xy,yx,yy,det].every(Number.isFinite)||Math.abs(det)<1e-8) throw Error('Projeção do mapa indisponível.');\n const dx=target.x-a.x, dy=target.y-a.y;\n const px=cx+(dx*yy-dy*xy)/det, py=cy+(dy*xx-dx*yx)/det;\n if(!Number.isFinite(px)||!Number.isFinite(py)) throw Error('Projeção inválida.');\n const projected=r.worldAt(px,py);\n if(!projected||!Number.isFinite(projected.x)||!Number.isFinite(projected.y)||Math.hypot(projected.x-target.x,projected.y-target.y)>.5) throw Error('Projeção do cliente mudou. Coleta pausada.');\n for(const [ox,oy] of [[0,0],[0,-4],[0,4],[-4,0],[4,0]]) {\n   const x=px+ox,y=py+oy;\n   if(x<rect.left+2||x>=rect.right-2||y<rect.top+2||y>=rect.bottom-2) continue;\n   const hit=r.hitBonusBox(x,y);\n   if(!hit||hit.id!==target.id||hit.revision!==target.revision||(hit.kind==='booty'&&!target.allow_green)) continue;\n   if(r.hitTarget?.(x,y)||r.hitWorldButton?.(x,y)) continue;\n   if(!target.can_collect) return {action:'wait'};\n   canvas.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,buttons:1,\n       pointerId:9381,pointerType:'mouse',clientX:x,clientY:y}));\n   return {action:'collect',id:hit.id,revision:hit.revision};\n }\n if(!target.can_move) return {action:'wait'};\n groups.onFollow({x:target.x,y:Math.max(0,target.y-120),mapId:target.map});\n return {action:'move',id:target.id,revision:target.revision};\n}"


def find_opera_gx():
    for base in (os.environ.get("LOCALAPPDATA"), os.environ.get("PROGRAMFILES"),
                 os.environ.get("PROGRAMFILES(X86)")):
        if not base:
            continue
        base = Path(base)
        for folder in (base / "Programs" / "Opera GX", base / "Opera GX"):
            for name in ("opera.exe", "launcher.exe"):
                executable = folder / name
                if executable.is_file():
                    return str(executable)
    return ""


class UnsupportedWorldPatch(ValueError):
    def __init__(self, path, patch):
        super().__init__("operacao ainda nao suportada")
        self.path=".".join(path) or "root"
        self.operation=patch[0] if patch[0] in ("a","o","v","s","d","i","r","u","p","k","l") else "unknown"
        self.shape=self.describe(patch)

    @classmethod
    def describe(cls, value, depth=0):
        # Estrutura limitada: nunca conserva textos, IDs, tokens ou campos privados.
        if depth>6: return "depth-limit"
        if isinstance(value,list):
            items=[cls.describe(v,depth+1) for v in value[:8]]
            if value and isinstance(value[0],str) and value[0] in ("a","o","v","s","d","i","r","u","p","k","l"):
                items[0]=value[0]
            return {"list_length":len(value),"items":items}
        if isinstance(value,dict):
            allowed={"id","revision","x","y","type","hp","maxHp"}
            return {"object":{k:cls.describe(v,depth+1) for k,v in value.items() if k in allowed},
                    "omitted_fields":sum(k not in allowed for k in value)}
        if value is None or isinstance(value,bool): return value
        if type(value) in (int,float) and math.isfinite(value): return value
        return "text" if isinstance(value,str) else "unsupported"


class WorldFeed:
    """Reconstrucao somente de campos de navegacao; nao guarda tokens nem chat."""
    ROOT = {"map", "world", "me", "boxes", "npcs", "events", "time", "inputAck"}
    LISTS = (("boxes",),("npcs",),("map","gates"),("events",),("me","repairChoices","options"))
    ME = {"x","y","speed","hp","maxHp","shield","maxShield","moving","destination",
          "mapId","deadUntil","respawnRevision","targetId","attacking","repairing","inputSeq","achievements","credits","uridium","xp","honor","galaxyGates","repairChoices","selectedAmmo","ammo","selectedRocket","rockets","autoRocket","secondaryVolley","repairActive"}
    MAP = {"id","width","height","gates"}
    ENTITY = {"id","revision","x","y","type","kind","hp","maxHp","shield","maxShield","respawnRevision"}
    def __init__(self, clock=None):
        self.clock = clock or time.monotonic
        self.lock = threading.RLock()
        self.stream = None
        self.state = None
        self.epoch = None
        self.sequence = None
        self.updated = None
        self.reason = "Aguardando dados do jogo."
        self.failure = None

    def begin(self, stream):
        with self.lock:
            self.stream = stream
            self.failure = None
            self._invalidate("Aguardando estado completo do jogo.")

    def _invalidate(self, reason):
        self.state = None
        self.sequence = None
        self.epoch = None
        self.updated = None
        self.reason = reason

    def end(self, stream, reason="Fluxo encerrado. Aguardando reconexao."):
        with self.lock:
            if stream == self.stream:
                self._invalidate(reason)

    @classmethod
    def _keys(cls, path):
        if not path: return cls.ROOT
        if path in (("boxes","*"),("npcs","*")): return cls.ENTITY
        if path == ("map","gates","*"): return {"id","to","x","y"}
        if path == ("events","*"): return {"id","time","type","field","amount","petCollected"}
        if path == ("me","galaxyGates"): return {"bootyKeys"}
        if path == ("me","repairChoices"): return {"id","readyAt","baseMap","options"}
        if path == ("me","repairChoices","options","*"): return {"id","cost","available","affordable"}
        if path == ("me",): return cls.ME
        if path == ("map",): return cls.MAP
        if path == ("world",): return {"width","height"}
        if path == ("me","destination"): return {"x","y"}
        if path == ("me","achievements"): return {"counters"}
        if path == ("me","achievements","counters"): return {"bonusboxes"}
        return None

    @classmethod
    def _project(cls, value, path=()):
        keys = cls._keys(path)
        if keys is not None:
            if value is None and path in (("me","destination"),("me","repairChoices"),("me","galaxyGates")): return None
            if not isinstance(value, dict): raise ValueError("objeto esperado")
            return {k:cls._project(v,path+(k,)) for k,v in value.items() if k in keys}
        if path in cls.LISTS:
            if not isinstance(value,list) or len(value)>20000: raise ValueError("lista invalida")
            return [cls._project(item,path+("*",)) for item in value]
        return cls._scalar(value)

    @staticmethod
    def _scalar(value):
        if value is None or isinstance(value,bool): return value
        if isinstance(value,(int,float)) and math.isfinite(value): return value
        if isinstance(value,str) and len(value)<=256: return value
        raise ValueError("valor invalido")

    @classmethod
    def _patch(cls, current, patch, path=(), depth=0):
        if depth>24 or not isinstance(patch,list) or not patch:
            raise ValueError("patch invalido")
        op = patch[0]
        if op == "v" and len(patch)==2:
            return cls._project(patch[1],path)
        if op == "a" and path in cls.LISTS:
            if len(patch)!=3 or not isinstance(current,list):
                raise ValueError("patch de lista invalido")
            length, changes=patch[1:]
            if type(length) is not int or not 0<=length<=20000 or not isinstance(changes,list) or len(changes)>length:
                raise ValueError("tamanho de lista invalido")
            result=current[:length]+[None]*max(0,length-len(current))
            seen=set()
            for entry in changes:
                if not isinstance(entry,list) or len(entry)!=2:
                    raise ValueError("item de lista invalido")
                index, child=entry
                if type(index) is not int or not 0<=index<length or index in seen:
                    raise ValueError("indice de lista invalido")
                seen.add(index)
                result[index]=cls._patch(result[index],child,path+("*",),depth+1)
            if any(not isinstance(item,dict) for item in result):
                raise ValueError("lista incompleta")
            return result
        keys = cls._keys(path)
        if op != "o" or len(patch)!=3 or keys is None or not isinstance(current,dict):
            raise UnsupportedWorldPatch(path,patch)
        changes, deleted = patch[1:]
        if not isinstance(changes,list) or not isinstance(deleted,list):
            raise ValueError("patch de objeto invalido")
        result = dict(current)
        for entry in changes:
            if not isinstance(entry,list) or len(entry)!=2 or not isinstance(entry[0],str):
                raise ValueError("campo invalido")
            key, child = entry
            if key in keys:
                result[key] = cls._patch(result.get(key),child,path+(key,),depth+1)
        for key in deleted:
            if not isinstance(key,str): raise ValueError("remocao invalida")
            result.pop(key,None)
        return result

    def ingest(self, stream, text):
        with self.lock:
            if stream != self.stream: return False
            packet = {}
            try:
                if not isinstance(text,str) or len(text)>2_000_000: raise ValueError("mensagem invalida")
                packet = json.loads(text)
                if not isinstance(packet,dict) or packet.get("transport")!="delta1":
                    return False
                seq, epoch = packet.get("sequence"),packet.get("epoch")
                if type(seq) is not int or seq<1 or not isinstance(epoch,str) or not epoch or len(epoch)>256:
                    raise ValueError("sequencia invalida")
                if self.state is not None and epoch==self.epoch and seq<=self.sequence:
                    return False
                if "full" in packet:
                    updated = self._project(packet["full"])
                else:
                    if (self.state is None or epoch!=self.epoch or
                            packet.get("base")!=self.sequence or seq!=self.sequence+1):
                        raise ValueError("sequencia interrompida")
                    updated = self._patch(self.state,packet.get("patch"))
                self.state, self.epoch, self.sequence = updated, epoch, seq
                self.updated = self.clock()
                self.reason = "Dados recebidos."
                if "full" in packet: self.failure = None
                return True
            except (ValueError,TypeError,KeyError,RecursionError,OverflowError) as exc:
                if self.failure is None:
                    self.failure={"code":"unsupported_patch" if isinstance(exc,UnsupportedWorldPatch) else "invalid_update",
                                  "last_sequence":self.sequence,
                                  "received_sequence":packet.get("sequence") if isinstance(packet,dict) and type(packet.get("sequence")) is int else None}
                    if isinstance(exc,UnsupportedWorldPatch):
                        self.failure.update(path=exc.path,operation=exc.operation,shape=exc.shape)
                detail="Atualizacao de "+self.failure.get("path","dados")+" ainda nao suportada. " if self.failure["code"]=="unsupported_patch" else ""
                self._invalidate("Leitura interrompida: "+detail+"Copie o diagnostico antes de recarregar o jogo.")
                return False

    def diagnostic(self):
        with self.lock:
            return {"fresh":self.summary().get("fresh",False),
                    "failure":json.loads(json.dumps(self.failure))}

    @staticmethod
    def _number(value):
        return type(value) in (int,float) and math.isfinite(value)

    def summary(self, max_age=2.):
        with self.lock:
            if self.state is None:
                return {"fresh":False,"status":self.reason}
            age = max(0.,self.clock()-self.updated)
            if age>max_age:
                return {"fresh":False,"status":"Dados antigos. Aguardando novas atualizacoes.","age":age}
            s = self.state
            me, game_map, world = s.get("me",{}),s.get("map",{}),s.get("world",{})
            x,y = me.get("x"),me.get("y")
            width,height = game_map.get("width",world.get("width")),game_map.get("height",world.get("height"))
            if not all(self._number(v) for v in (x,y,width,height)) or min(width,height)<=0:
                return {"fresh":False,"status":"Estado incompleto: posicao ou limites indisponiveis."}
            if not isinstance(game_map.get("id"),str) or me.get("mapId")!=game_map["id"]:
                return {"fresh":False,"status":"Aguardando sincronizacao do mapa."}
            boxes = [b for b in s.get("boxes",[]) if isinstance(b.get("id"),str) and
                     self._number(b.get("x")) and self._number(b.get("y")) and
                     0<=b["x"]<=width and 0<=b["y"]<=height]
            nearest = min(boxes,key=lambda b:math.hypot(b["x"]-x,b["y"]-y),default=None)
            hp,max_hp = me.get("hp"),me.get("maxHp")
            hp_percent = 100*hp/max_hp if self._number(hp) and self._number(max_hp) and max_hp>0 else None
            return {"fresh":True,"status":"Leitura ao vivo — somente observacao.",
                    "age":age,"sequence":self.sequence,"map":game_map["id"],
                    "position":(x,y),"moving":me.get("moving"),"speed":me.get("speed"),
                    "hp_percent":hp_percent,"boxes":len(boxes),"npcs":len(s.get("npcs",[])),
                    "portals":len(game_map.get("gates",[])),
                    "nearest":dict(nearest,distance=math.hypot(nearest["x"]-x,nearest["y"]-y)) if nearest else None}


    def navigation_snapshot(self):
        with self.lock:
            result=self.summary()
            if not result.get("fresh"): return result
            me=self.state["me"]
            result["candidates"]=[dict(b) for b in self.state.get("boxes",[]) if
                isinstance(b.get("id"),str) and self._number(b.get("x")) and self._number(b.get("y")) and
                0<=b["x"]<=self.state["map"].get("width",self.state.get("world",{}).get("width",0)) and
                0<=b["y"]<=self.state["map"].get("height",self.state.get("world",{}).get("height",0))]
            result["npc_candidates"]=[dict(n) for n in self.state.get("npcs",[]) if
                isinstance(n.get("id"),(str,int)) and self._number(n.get("x")) and self._number(n.get("y"))]
            result["combat"]={k:me.get(k) for k in ("attacking","selectedAmmo","ammo","selectedRocket","rockets","autoRocket","secondaryVolley","repairing","repairActive")}
            result["combat"]["target_id"]=me.get("targetId") if any(str(n.get("id"))==str(me.get("targetId")) for n in self.state.get("npcs",[])) else None
            result["gates"]=[dict(g) for g in self.state["map"].get("gates",[])]
            result["account"]={k:me.get(k) for k in ("credits","uridium","xp","honor")}
            xp=me.get("xp")
            result["account"]["level"]=(1 if xp<10000 else 2+int(math.log2(xp/10000))) if self._number(xp) and xp>=0 else None
            keys=(me.get("galaxyGates") or {}).get("bootyKeys",0)
            result["booty_keys"]=keys if type(keys) is int and keys>=0 else 0
            result["repair"]=json.loads(json.dumps(me.get("repairChoices")))
            result["server_time"]=self.state.get("time")
            result["rewards"]=[dict(e) for e in self.state.get("events",[]) if e.get("type")=="box-collected"]
            result["respawn_revision"]=me.get("respawnRevision")
            result["dead"]=bool(me.get("deadUntil")) or (self._number(me.get("hp")) and me["hp"]<=0)
            result["destination"]=dict(me["destination"]) if isinstance(me.get("destination"),dict) else None
            result["box_counter"]=me.get("achievements",{}).get("counters",{}).get("bonusboxes")
            return result


class ManualCollectProbe:
    """Amostra limitada de comandos ja enviados pelo cliente; nunca reenvia."""
    def __init__(self, feed, clock=None):
        self.feed=feed
        self.clock=clock or time.monotonic
        self.lock=threading.RLock()
        self.until=0
        self.baseline=None
        self.highest=None
        self.samples=[]
        self.counter_before=None
        self.status="Registre uma coleta manual para conferir o comando do jogo."

    def arm(self):
        with self.lock, self.feed.lock:
            if not self.feed.summary().get("fresh"):
                raise ValueError("Aguarde dados ao vivo antes de registrar.")
            server_seq=self.feed.state.get("me",{}).get("inputSeq")
            known=[v for v in (server_seq,self.highest) if type(v) is int]
            self.baseline=max(known) if known else None
            self.samples=[]
            self.counter_before=self.feed.navigation_snapshot().get("box_counter")
            self.until=self.clock()+30
            self.status="Gravando por 30 segundos. Clique manualmente em uma box e espere coletar."
            return True

    @classmethod
    def _collect_detail(cls, value, ids, depth=0, numeric=True, category=False):
        if depth>4: return {"type":"depth-limit"}
        if value is None or isinstance(value,bool): return value
        if WorldFeed._number(value):
            return value if numeric else {"type":"number","value_omitted":True}
        if isinstance(value,str):
            if category and 0<len(value)<=32 and value.isascii() and all(c.isalnum() or c in "_-" for c in value):
                return value
            return {"box_id":value} if value in ids else {"type":"string","value_omitted":True}
        if isinstance(value,list):
            return {"type":"array","length":len(value),
                    "items":[cls._collect_detail(v,ids,depth+1,numeric) for v in value[:8]]}
        if isinstance(value,dict):
            allowed={"kind","id","boxId","targetId","revision","boxRevision","x","y","position","destination","box"}
            return {"type":"object","fields":list(value)[:16],
                    "values":{k:cls._collect_detail(v,ids,depth+1,k in {"revision","boxRevision","x","y"},category=k=="kind")
                              for k,v in list(value.items())[:16] if k in allowed},
                    "omitted_fields":sum(k not in allowed for k in value)}
        return {"type":"unsupported"}

    def observe(self, text):
        try:
            if not isinstance(text,str) or len(text)>200000: return
            packet=json.loads(text)
            if packet.get("inputTransport")!="cumulative-input-v1": return
            commands=packet.get("commands",[])
            if not isinstance(commands,list): return
            with self.lock, self.feed.lock:
                seqs=[c.get("inputSeq") for c in commands if isinstance(c,dict) and type(c.get("inputSeq")) is int]
                if seqs: self.highest=max(seqs+[self.highest] if self.highest is not None else seqs)
                if not self.until or self.clock()>self.until: return
                if self.baseline is None:
                    self.baseline=self.highest
                    self.status="Referencia capturada. Clique agora em uma box para registrar."
                    return
                boxes=self.feed.state.get("boxes",[]) if self.feed.state else []
                ids={b.get("id") for b in boxes}
                for cmd in commands:
                    if not isinstance(cmd,dict): continue
                    seq=cmd.get("inputSeq")
                    if type(seq) is not int or seq<=self.baseline: continue
                    self.baseline=seq
                    sample={"fields":sorted(k for k in cmd if k not in ("inputSeq","respawnRevision"))[:32]}
                    dest=cmd.get("destination")
                    if isinstance(dest,dict) and all(WorldFeed._number(dest.get(k)) for k in ("x","y")):
                        sample["destination"]={k:dest[k] for k in ("x","y")}
                        close=min(boxes,key=lambda b:math.hypot(b.get("x",1e30)-dest["x"],b.get("y",1e30)-dest["y"]),default=None)
                        if close and math.hypot(close["x"]-dest["x"],close["y"]-dest["y"])<=50:
                            sample["near_box_id"]=close["id"]
                    if "collect" in cmd:
                        sample["collect"]=self._collect_detail(cmd["collect"],ids)
                    sample["box_references"]={k:v for k,v in cmd.items() if isinstance(v,str) and v in ids}
                    self.samples=(self.samples+[sample])[-8:]
                if self.samples: self.status="Comando observado. Espere a coleta e copie o diagnostico."
        except (ValueError,TypeError,AttributeError,OverflowError):
            return

    def report(self):
        with self.lock:
            active=self.until>self.clock()
            if self.until and not active and not self.samples:
                self.status="Nenhum comando registrado. Inicie o registro novamente e clique em uma box."
            current=self.feed.navigation_snapshot()
            counter=current.get("box_counter") if current.get("fresh") else None
            increment=(counter-self.counter_before if type(counter) is int and
                       type(self.counter_before) is int and counter>=self.counter_before else None)
            return {"status":self.status,"recording":active,"commands":json.loads(json.dumps(self.samples)),
                    "data_fresh":current.get("fresh",False),"observed_box_increment":increment,
                    "automatic_commands_sent":0,"reader":self.feed.diagnostic()}

class CombatProbe:
    """Registro limitado por índice do transporte, inclusive ataques sem inputSeq."""
    def __init__(self, feed, clock=None):
        self.feed=feed; self.clock=clock or time.monotonic
        self.lock=threading.RLock()
        self.until=0; self.armed=False; self.started=0
        self.highest=None; self.commands=[]; self.frames=[]; self.last_frame=-1.
        self.initial=None; self.status="Registre uma luta manual para validar o combate."

    def arm(self):
        with self.lock:
            snapshot=self.feed.navigation_snapshot()
            if not snapshot.get("fresh") or snapshot.get("dead"):
                raise ValueError("Entre no mapa com a nave viva e aguarde a leitura ao vivo.")
            with self.feed.lock:
                ack=(self.feed.state or {}).get("inputAck")
            self.baseline_observed=self.highest is not None
            self.commands=[]; self.frames=[]; self.last_frame=-1.
            self.initial={"map":snapshot["map"],"transport_baseline_observed":self.baseline_observed,"input_ack":ack,"hp_percent":snapshot.get("hp_percent"),
                          "account":snapshot.get("account",{}),"combat":snapshot.get("combat",{})}
            self.started=self.clock(); self.until=self.started+90; self.armed=True
            self.status="Gravando por 90 segundos: selecione um NPC, ataque, pare e ataque novamente."
            self.sample()

    def stop(self, reason="Registro encerrado. Copie o diagnóstico da luta."):
        with self.lock:
            self.until=0; self.armed=False; self.status=reason

    def sample(self):
        with self.lock:
            if not self.armed: return
            now=self.clock()
            if now>=self.until:
                self.stop(); return
            if now-self.last_frame<1: return
            self.last_frame=now
            data=self.feed.navigation_snapshot()
            if not data.get("fresh"):
                self.stop("Leitura interrompida durante a luta. Copie o diagnóstico."); return
            if data.get("map")!=self.initial["map"]:
                self.stop("Mapa mudou. Registro encerrado; copie o diagnóstico."); return
            combat=data.get("combat",{})
            target=next((n for n in data.get("npc_candidates",[]) if str(n.get("id"))==str(combat.get("target_id"))),None)
            self.frames.append({"seconds":round(now-self.started,2),"position":data.get("position"),
                "hp_percent":data.get("hp_percent"),"dead":data.get("dead",False),
                "combat":combat,"target_npc":target,"account":data.get("account",{})})
            self.frames=self.frames[-90:]

    def observe(self, text):
        try:
            if not isinstance(text,str) or len(text)>200000: return
            packet=json.loads(text)
            if packet.get("inputTransport")!="cumulative-input-v1": return
            start=packet.get("inputStart"); commands=packet.get("commands")
            if type(start) is not int or not isinstance(commands,list): return
            with self.lock:
                recording=self.armed and self.clock()<self.until
                snapshot=self.feed.navigation_snapshot()
                ids={str(n["id"]) for n in snapshot.get("npc_candidates",[])}
                for index,command in enumerate(commands[:256]):
                    number=start+index
                    if self.highest is not None and number<=self.highest: continue
                    self.highest=number
                    if not recording or not isinstance(command,dict): continue
                    values={}
                    for key in ("attacking","repairing","rocket","autoRocket","launcher","autoLauncher"):
                        if type(command.get(key)) is bool: values[key]=command[key]
                    for key in ("selectedAmmo","selectedRocket","selectedLauncherAmmo"):
                        value=command.get(key)
                        if isinstance(value,str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,32}",value):
                            values[key]=value
                    if "targetId" in command:
                        values["targetId"]=command["targetId"] if str(command["targetId"]) in ids else "not_npc"
                    dest=command.get("destination")
                    if isinstance(dest,dict) and all(WorldFeed._number(dest.get(k)) for k in ("x","y")):
                        values["destination"]={k:dest[k] for k in ("x","y")}
                    elif "destination" in command and dest is None:
                        values["destination"]=None
                    if values:
                        self.commands.append({"seconds":round(self.clock()-self.started,2),"values":values})
                        if len(self.commands)>160:
                            movement=next((i for i,c in enumerate(self.commands) if set(c["values"])=={"destination"}),0)
                            self.commands.pop(movement)
                self.sample()
        except (ValueError,TypeError,AttributeError,KeyError):
            return

    def report(self):
        with self.lock:
            self.sample()
            values=[c["values"] for c in self.commands]
            checks={"npc_selected":any(f.get("target_npc") for f in self.frames),
                    "attack_started":any(v.get("attacking") is True for v in values),
                    "attack_stopped":any(v.get("attacking") is False for v in values),
                    "damage_observed":False}
            health={}
            for frame in self.frames:
                npc=frame.get("target_npc")
                if not npc or not WorldFeed._number(npc.get("hp")): continue
                hp=npc["hp"]+(npc.get("shield") if WorldFeed._number(npc.get("shield")) else 0)
                key=str(npc["id"])
                if key in health and hp<health[key]: checks["damage_observed"]=True
                health[key]=hp
            return json.loads(json.dumps({"schema":"autobox-combat-probe-v1","status":self.status,
                "recording":self.armed,"checks":checks,"initial":self.initial,
                "commands":self.commands,"frames":self.frames,
                "reader":self.feed.diagnostic(),"automatic_combat_commands_sent":0}))


class BrowserSession:
    """Dono unico do navegador e da integracao com os dados do jogo."""
    def __init__(self, folder, viewport, factory=None):
        self.folder = Path(folder)
        self.viewport = dict(viewport)
        self.factory = factory
        self.jobs = queue.Queue()
        self.ready = threading.Event()
        self.closed = threading.Event()
        self.closed.set()
        self.error = None
        self.warning = None
        self.thread = None
        self.world_feed = WorldFeed()
        self.probe = ManualCollectProbe(self.world_feed)
        self.combat_probe = CombatProbe(self.world_feed)
        self.data_action = None
        self.data_actions_dispatched = 0

    def start(self, executable):
        if self.thread is not None and self.thread.is_alive():
            return
        self.error = None
        self.warning = None
        self.data_action = None
        self.world_feed.begin(None)
        self.probe = ManualCollectProbe(self.world_feed)
        self.combat_probe = CombatProbe(self.world_feed)
        self.ready.clear()
        self.closed.clear()
        self.thread = threading.Thread(target=self._run, args=(executable,), daemon=True)
        self.thread.start()

    def request(self, operation, payload=None, allowed=None, timeout=8):
        if not self.ready.is_set() and operation != "close":
            raise RuntimeError(self.error or "Abra primeiro a sessao dedicada do Opera GX.")
        reply = queue.Queue(maxsize=1)
        cancelled = threading.Event()
        self.jobs.put((operation, payload, allowed, reply, cancelled))
        try:
            ok, result = reply.get(timeout=timeout)
        except queue.Empty:
            cancelled.set()
            raise RuntimeError("A janela do jogo demorou a responder. Coleta interrompida.")
        if not ok:
            raise RuntimeError(result)
        return result

    def close(self):
        if self.thread is None or not self.thread.is_alive():
            return
        try:
            self.request("close", timeout=8)
        finally:
            self.thread.join(timeout=3)

    @staticmethod
    def _game_page(context):
        pages = [page for page in context.pages if not page.is_closed()
                 and page.url.split("#")[0].split("?")[0].rstrip("/") ==
                 GAME_URL.split("#")[0].rstrip("/")]
        if not pages:
            raise RuntimeError("Abra a pagina de jogo do Interstellar na sessao dedicada.")
        return pages[-1]






    @staticmethod
    def _client_sources(page):
        raw=page.evaluate(r"""async () => {
            const candidates=[...Array.from(document.scripts,s=>s.src).reverse(),
                ...performance.getEntriesByType('resource').filter(r=>r.initiatorType==='script').map(r=>r.name)];
            const urls=[...new Set(candidates)].filter(value=>{
                try { const u=new URL(value,location.href);
                    return u.origin===location.origin && u.protocol==='https:' && u.pathname.endsWith('.js');
                } catch { return false; }
            }).sort((a,b)=>{
                const rank=v=>/star-system|maps\\.js|input|bindings|quickbar|renderer|game\\.js/i.test(new URL(v).pathname)?0:1;
                return rank(a)-rank(b);
            }).slice(0,24);
            return await Promise.all(urls.map(async value=>{
                const u=new URL(value,location.href);
                try {
                    const response=await fetch(u.href,{method:'GET',credentials:'same-origin',
                        cache:'force-cache',redirect:'error',signal:AbortSignal.timeout(8000)});
                    if(!response.ok || !/javascript|text\/plain/i.test(response.headers.get('content-type')||''))
                        return {path:u.pathname,error:'unavailable'};
                    const source=await response.text();
                    return source.length<=1500000 ? {path:u.pathname,source} : {path:u.pathname,error:'too-large'};
                } catch { return {path:u.pathname,error:'unavailable'}; }
            }));
        }""")
        if not isinstance(raw,list) or len(raw)>24:
            raise ValueError("Resposta de arquivos do cliente invalida.")
        files=[]; total=0
        # Remove atribuicoes literais de credenciais; nao exporta cookies ou estado.
        secrets=re.compile(r'''(?i)(["']?(?:password|token|secret|authorization|cookie|inputChannel|mapSessionId|connectionId|membershipToken|sessionId)["']?\s*[:=]\s*)(["'])(?:\\.|(?!\2).)*?\2''')
        for item in raw:
            if not isinstance(item,dict): continue
            name=item.get("path")
            if not isinstance(name,str) or not name.startswith("/") or "?" in name or "#" in name or not name.endswith(".js"): continue
            source=item.get("source")
            if not isinstance(source,str) or len(source)>1500000: continue
            total+=len(source)
            if total>6000000: break
            source=secrets.sub(lambda match:match[1]+match[2]+"<redacted>"+match[2],source)
            files.append({"path":name,"source":source})
        if not files:
            raise ValueError("Nenhum arquivo JavaScript disponivel. Entre no mapa pela janela dedicada.")
        return {"schema":"autobox-client-integration-v1","files":files}

    def _npc_action(self,page,target,allowed):
        action=target.get("action")
        if action not in ("select","approach","attack","stop","orbit","retreat"):
            raise ValueError("Ação de combate inválida.")
        if allowed is not None and not allowed(): return {"action":"cancelled"}
        snap=self.world_feed.navigation_snapshot()
        if action!="stop":
            if not snap.get("fresh") or snap.get("dead"):
                raise ValueError("Dados de combate indisponíveis.")
            if snap["map"]!=target.get("map") or snap.get("respawn_revision")!=target.get("life"):
                return {"action":"changed"}
            npc=next((n for n in snap.get("npc_candidates",[]) if str(n.get("id"))==str(target.get("id"))
                and n.get("respawnRevision")==target.get("revision")),None)
            if npc is None and action!="retreat": return {"action":"gone"}
            if action!="retreat" and (snap.get("hp_percent") is None or snap["hp_percent"]<=target.get("min_hp",40)):
                return {"action":"low_hp"}
        if allowed is not None and not allowed(): return {"action":"cancelled"}
        return page.evaluate(NPC_SCRIPT,target)

    def _travel(self, page, target, allowed):
        snap=self.world_feed.navigation_snapshot()
        destination=target.get("destination","")
        if not isinstance(destination,str) or not re.fullmatch(r"[0-9]{1,2}-[0-9]{1,2}",destination):
            raise ValueError("Informe um mapa normal, por exemplo 4-3.")
        if (not snap.get("fresh") or snap.get("dead") or snap.get("hp_percent") is None
                or snap["hp_percent"]<=25):
            raise ValueError("Viagem pausada: dados indisponíveis, nave destruída ou vida baixa.")
        if snap["map"]==destination: return {"action":"arrived","map":destination}
        if allowed is not None and not allowed(): return {"action":"cancelled"}
        return page.evaluate(TRAVEL_SCRIPT,{"destination":destination,"map":snap["map"],
            "respawn_revision":snap.get("respawn_revision"),"execute":target.get("execute",False)})

    def _respawn(self, page, target, allowed):
        snap=self.world_feed.navigation_snapshot()
        repair=snap.get("repair") or {}
        option=next((o for o in repair.get("options",[]) if o.get("id")==target.get("option")),None)
        if (not snap.get("fresh") or not snap.get("dead") or repair.get("id")!=target.get("death_id")
                or not option or not option.get("available") or not option.get("affordable")
                or not self.world_feed._number(option.get("cost")) or option["cost"]<0
                or option["cost"]>target.get("max_cost",0)):
            return {"action":"blocked"}
        if allowed is not None and not allowed(): return {"action":"cancelled"}
        return page.evaluate(r"""t => {
            const panel=document.getElementById('respawnOverlay');
            if(!panel||panel.hidden||!panel.getClientRects().length||panel.dataset.deathId!==String(t.death_id))
                return {action:'wait'};
            const choice=panel.querySelector('[data-repair-option="'+t.option+'"]');
            if(!choice||choice.disabled||choice.dataset.affordable!=='true') return {action:'blocked'};
            choice.click();
            const button=panel.querySelector('.repair-confirm');
            const price=choice.querySelector('.repair-price')?.textContent||'';
            const match=price.match(/^\s*(\d+(?:\.\d+)?)\s*U\./);
            const amount=price.trim()==='No charge'?0:match?Number(match[1]):NaN;
            if(!button||button.disabled||!Number.isFinite(amount)||amount>t.max_cost) return {action:'blocked'};
            button.click();
            return {action:'respawn'};
        }""",target)

    def _reconnect(self, context, payload, allowed):
        if allowed is not None and not allowed(): return {"action":"cancelled"}
        if self.world_feed.navigation_snapshot().get("fresh"): return {"action":"ready"}
        pages=[p for p in context.pages if urlsplit(p.url).hostname=="interstellar-verse.com"]
        if not pages: return {"action":"closed"}
        page=next((p for p in reversed(pages) if urlsplit(p.url).path.rstrip("/")=="/play"),pages[-1])
        action=page.evaluate("""() => {
            const visible=e=>e&&e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
            if(visible(document.getElementById('authScreen'))) return 'login';
            for(const id of ['flightStart','flightLoadingRetry','startGame']){
                const e=document.getElementById(id);
                if(visible(e)&&!e.disabled) return id;
            }
            return 'wait';
        }""")
        if allowed is not None and not allowed(): return {"action":"cancelled"}
        if action in ("flightStart","flightLoadingRetry","startGame"):
            page.locator("#"+action).click(timeout=2000)
        elif action=="wait" and payload.get("reload") and urlsplit(page.url).path.rstrip("/")=="/play":
            page.reload(wait_until="domcontentloaded",timeout=5000)
            action="reload"
        return {"action":action}

    def _data_target(self, page, target, allowed):
        snapshot=self.world_feed.navigation_snapshot()
        if not snapshot.get("fresh") or snapshot.get("dead"):
            raise ValueError("Leitura indisponivel ou nave destruida. Coleta por dados pausada.")
        if snapshot.get("hp_percent") is None or snapshot["hp_percent"]<=25:
            raise ValueError("Vida baixa ou indisponivel. Coleta por dados pausada.")
        if (target.get("map")!=snapshot["map"] or
                target.get("respawn_revision")!=snapshot.get("respawn_revision")):
            raise ValueError("Mapa ou renascimento mudou. Inicie novamente.")
        box=next((b for b in snapshot["candidates"] if b.get("id")==target.get("id") and
                  b.get("revision")==target.get("revision")),None)
        if box is None: return {"action":"gone"}
        if type(box.get("revision")) is not int or box.get("kind") not in (None,"box","bonus","booty"):
            raise ValueError("Tipo ou revisao da box nao suportado.")
        green=box.get("kind")=="booty"
        if green and (not target.get("allow_green") or (snapshot.get("booty_keys") or 0)<1):
            return {"action":"gone"}
        now=time.monotonic(); key=(snapshot["map"],snapshot.get("respawn_revision"),box["id"],box["revision"])
        previous=self.data_action
        same=previous and previous["key"]==key
        elapsed=now-previous["time"] if same else float("inf")
        collecting=same and previous["action"]=="collect"
        payload={"allow_green":green,"map":snapshot["map"],"id":box["id"],"revision":box["revision"],"x":box["x"],"y":box["y"],
                 "can_collect":not collecting or elapsed>=3,
                 "can_move":not collecting and (not same or elapsed>=2)}
        if allowed is not None and not allowed(): return {"action":"cancelled"}
        result=page.evaluate(DATA_TARGET_SCRIPT,payload)
        if not isinstance(result,dict) or result.get("action") not in ("move","collect","wait"):
            raise ValueError("Resposta do cliente inesperada.")
        if result["action"]!="wait":
            self.data_actions_dispatched+=1
            self.data_action={"key":key,"time":now,"action":result["action"]}
        return result

    def _attach_feed(self, context, page):
        try:
            client = context.new_cdp_session(page)
            def started(event):
                request=event.get("request",{})
                url = urlsplit(request.get("url",""))
                if (url.scheme=="https" and url.hostname=="interstellar-verse.com"
                        and url.path.rstrip("/").endswith("/input")):
                    self.probe.observe(request.get("postData"))
                    self.combat_probe.observe(request.get("postData"))
                if (url.scheme=="https" and url.hostname=="interstellar-verse.com"
                        and url.path.rstrip("/").endswith("/events")):
                    if self.combat_probe.armed:
                        self.combat_probe.stop("Conexão mudou durante o registro. Copie o diagnóstico.")
                    self.world_feed.begin((id(page),event.get("requestId")))
                    self.probe = ManualCollectProbe(self.world_feed)
            def received(event):
                if event.get("eventName") not in (None,"message",""): return
                self.world_feed.ingest((id(page),event.get("requestId")),event.get("data"))
                self.combat_probe.sample()
            def ended(event):
                self.world_feed.end((id(page),event.get("requestId")))
            client.on("Network.requestWillBeSent",started)
            client.on("Network.eventSourceMessageReceived",received)
            client.on("Network.loadingFinished",ended)
            client.on("Network.loadingFailed",ended)
            page.on("close",lambda _closed=None:self.world_feed.end(self.world_feed.stream)
                    if self.world_feed.stream and self.world_feed.stream[0]==id(page) else None)
            client.send("Network.enable")
        except Exception:
            self.world_feed.end(self.world_feed.stream,
                "Leitura ao vivo indisponivel neste navegador. A coleta visual continua disponivel.")

    def get_world_summary(self):
        return self.world_feed.summary()

    def get_world_snapshot(self):
        return self.world_feed.navigation_snapshot()

    def arm_manual_probe(self):
        return self.probe.arm()

    def get_manual_probe_report(self):
        report=self.probe.report()
        report["automatic_actions_dispatched"]=self.data_actions_dispatched
        if self.data_actions_dispatched: report["automatic_commands_sent"]=None
        return report

    def _run(self, executable):
        context = None
        try:
            if self.factory is None:
                from playwright.sync_api import sync_playwright
                factory = sync_playwright
            else:
                factory = self.factory
            self.folder.mkdir(parents=True, exist_ok=True)
            with factory() as driver:
                context = driver.chromium.launch_persistent_context(
                    user_data_dir=str(self.folder), executable_path=executable,
                    headless=False, chromium_sandbox=True, viewport=self.viewport, device_scale_factor=1,
                    accept_downloads=False)
                context.on("page",lambda opened:self._attach_feed(context,opened))
                for existing in context.pages:
                    self._attach_feed(context,existing)
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=45000)
                except Exception:
                    self.warning = "Confira a conexao e abra o jogo na janela dedicada."
                self.ready.set()
                while True:
                    try:
                        operation, payload, allowed, reply, cancelled = self.jobs.get(timeout=.1)
                    except queue.Empty:
                        if not context.pages:
                            break
                        try:
                            context.pages[0].wait_for_timeout(30)
                        except Exception:
                            break
                        continue
                    if cancelled.is_set():
                        reply.put((False, "Comando expirado e cancelado."))
                        continue
                    if operation == "close":
                        context.close()
                        context = None
                        reply.put((True, None))
                        break
                    try:
                        if operation == "reconnect":
                            result=self._reconnect(context,payload or {},allowed)
                            reply.put((True,result))
                            continue
                        page = self._game_page(context)
                        # Recusa cliques enfileirados se F9/F10 ja interrompeu o bot.
                        if allowed is not None and not allowed():
                            reply.put((True, False))
                            continue
                        if operation == "npc_action":
                            result = self._npc_action(page,payload,allowed)
                        elif operation == "travel":
                            result = self._travel(page,payload,allowed)
                        elif operation == "respawn":
                            result = self._respawn(page,payload,allowed)
                        elif operation == "data_target":
                            result = self._data_target(page,payload,allowed)
                        elif operation == "client_sources":
                            result = self._client_sources(page)
                        else:
                            raise ValueError("Comando de navegador desconhecido.")
                        reply.put((True, result))
                    except Exception as exc:
                        reply.put((False, str(exc)))
        except Exception as exc:
            self.error = "Nao foi possivel abrir o Opera GX dedicado: " + str(exc)
        finally:
            self.world_feed.end(self.world_feed.stream,"Sessao encerrada.")
            self.ready.clear()
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            self.closed.set()
