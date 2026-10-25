from pathlib import Path
import os
import queue
import threading
import struct
import math
import json
import re
import time
from urllib.parse import urlsplit

HOME_URL = "https://interstellar-verse.com/"
GAME_URL = "https://interstellar-verse.com/play/#play"

DATA_TARGET_SCRIPT = "(target) => {\n const r=window.PeriodWindows?.renderer, groups=window.DarkOrbitGroups;\n const canvas=document.getElementById('space');\n if(!r || !canvas || typeof r.worldAt!=='function' || typeof r.hitBonusBox!=='function' || typeof groups?.onFollow!=='function')\n   throw Error('Integração do cliente indisponível. Entre no mapa novamente.');\n if(groups.isPingArmed?.()) throw Error('Desative a marcação de grupo antes de coletar.');\n const rect=canvas.getBoundingClientRect(), cx=rect.left+rect.width/2, cy=rect.top+rect.height/2;\n if(rect.width<=0||rect.height<=0) throw Error('Canvas do jogo indisponível.');\n const a=r.worldAt(cx,cy), b=r.worldAt(cx+10,cy), c=r.worldAt(cx,cy+10);\n const xx=(b.x-a.x)/10, xy=(c.x-a.x)/10, yx=(b.y-a.y)/10, yy=(c.y-a.y)/10;\n const det=xx*yy-xy*yx;\n if(![a.x,a.y,xx,xy,yx,yy,det].every(Number.isFinite)||Math.abs(det)<1e-8) throw Error('Projeção do mapa indisponível.');\n const dx=target.x-a.x, dy=target.y-a.y;\n const px=cx+(dx*yy-dy*xy)/det, py=cy+(dy*xx-dx*yx)/det;\n if(!Number.isFinite(px)||!Number.isFinite(py)) throw Error('Projeção inválida.');\n const projected=r.worldAt(px,py);\n if(!projected||!Number.isFinite(projected.x)||!Number.isFinite(projected.y)||Math.hypot(projected.x-target.x,projected.y-target.y)>.5) throw Error('Projeção do cliente mudou. Coleta pausada.');\n for(const [ox,oy] of [[0,0],[0,-4],[0,4],[-4,0],[4,0]]) {\n   const x=px+ox,y=py+oy;\n   if(x<rect.left+2||x>=rect.right-2||y<rect.top+2||y>=rect.bottom-2) continue;\n   const hit=r.hitBonusBox(x,y);\n   if(!hit||hit.id!==target.id||hit.revision!==target.revision||hit.kind==='booty') continue;\n   if(r.hitTarget?.(x,y)||r.hitWorldButton?.(x,y)) continue;\n   if(!target.can_collect) return {action:'wait'};\n   canvas.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,buttons:1,\n       pointerId:9381,pointerType:'mouse',clientX:x,clientY:y}));\n   return {action:'collect',id:hit.id,revision:hit.revision};\n }\n if(!target.can_move) return {action:'wait'};\n groups.onFollow({x:target.x,y:Math.max(0,target.y-120),mapId:target.map});\n return {action:'move',id:target.id,revision:target.revision};\n}"


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
    ROOT = {"map", "world", "me", "boxes", "npcs"}
    ME = {"x","y","speed","hp","maxHp","shield","maxShield","moving","destination",
          "mapId","deadUntil","respawnRevision","targetId","attacking","repairing","inputSeq","achievements"}
    MAP = {"id","width","height","gates"}
    ENTITY = {"id","revision","x","y","type","kind","hp","maxHp"}
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
            if value is None and path == ("me","destination"): return None
            if not isinstance(value, dict): raise ValueError("objeto esperado")
            return {k:cls._project(v,path+(k,)) for k,v in value.items() if k in keys}
        if path in (("boxes",),("npcs",),("map","gates")):
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
        if op == "a" and path in (("boxes",),("npcs",),("map","gates")):
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
            result["gates"]=[dict(g) for g in self.state["map"].get("gates",[])]
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

class BrowserSession:
    """Dono unico do navegador. Captura e cliques nao passam pelo mouse do Windows."""
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
        self.capture_geometry = None
        self.capture_page = None
        self.last_click = None
        self.world_feed = WorldFeed()
        self.probe = ManualCollectProbe(self.world_feed)
        self.data_action = None
        self.data_actions_dispatched = 0

    def start(self, executable):
        if self.thread is not None and self.thread.is_alive():
            return
        self.error = None
        self.warning = None
        self.capture_geometry = None
        self.capture_page = None
        self.last_click = None
        self.data_action = None
        self.world_feed.begin(None)
        self.probe = ManualCollectProbe(self.world_feed)
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
    def _measure(page):
        # Somente medidas do navegador; nao le estado interno do jogo.
        value = page.evaluate("""() => ({
            width: window.innerWidth, height: window.innerHeight,
            dpr: window.devicePixelRatio,
            offset_x: window.visualViewport ? window.visualViewport.offsetLeft : 0,
            offset_y: window.visualViewport ? window.visualViewport.offsetTop : 0,
            scale: window.visualViewport ? window.visualViewport.scale : 1
        })""")
        keys = ("width", "height", "dpr", "offset_x", "offset_y", "scale")
        if not isinstance(value, dict) or any(
            not isinstance(value.get(k), (float, int)) or not math.isfinite(value[k]) for k in keys
        ) or min(value["width"], value["height"], value["dpr"]) <= 0:
            raise ValueError("Medidas da pagina indisponiveis. Coleta interrompida.")
        if abs(value["scale"] - 1) > .001 or abs(value["offset_x"]) > .01 or abs(value["offset_y"]) > .01:
            raise ValueError("Zoom por gesto nao suportado. Use o zoom normal do Opera e calibre novamente.")
        return value

    def _capture(self, page):
        self.capture_geometry = None
        self.capture_page = None
        before = self._measure(page)
        data = page.screenshot(type="png", timeout=5000)
        after = self._measure(page)
        if before != after:
            raise ValueError("Zoom ou tamanho mudou durante a captura. Calibre novamente.")
        if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
            raise ValueError("Captura PNG invalida.")
        width, height = struct.unpack(">II", data[16:24])
        if width <= 0 or height <= 0:
            raise ValueError("Captura sem tamanho valido.")
        self.capture_geometry = dict(after, image_width=width, image_height=height)
        self.capture_page = page
        return data

    def _click(self, page, point, allowed):
        geometry = self.capture_geometry
        if geometry is None or self.capture_page is not page:
            raise ValueError("Capture a imagem dessa pagina antes de clicar.")
        current = self._measure(page)
        if any(current[k] != geometry[k] for k in current):
            self.capture_geometry = None
            raise ValueError("Zoom ou tamanho mudou apos a captura. Pause e calibre novamente.")
        x, y = point
        if (not math.isfinite(x) or not math.isfinite(y) or
                not (0 <= x < geometry["image_width"] and 0 <= y < geometry["image_height"])):
            raise ValueError("Clique fora da imagem do jogo.")
        # Captura em pixels da imagem; Playwright recebe pixels CSS do viewport.
        # No zoom 33%, uma imagem de 1280 pode representar cerca de 3840 pixels CSS.
        css_x = x * geometry["width"] / geometry["image_width"]
        css_y = y * geometry["height"] / geometry["image_height"]
        if allowed is not None and not allowed():
            return False
        page.mouse.click(css_x, css_y, button="left", delay=40)
        self.last_click = {"image": (x,y), "css": (css_x,css_y),
                           "image_size": (geometry["image_width"],geometry["image_height"]),
                           "css_size": (geometry["width"],geometry["height"])}
        return True


    @staticmethod
    def _client_sources(page):
        raw=page.evaluate(r"""async () => {
            const candidates=[...Array.from(document.scripts,s=>s.src).reverse(),
                ...performance.getEntriesByType('resource').filter(r=>r.initiatorType==='script').map(r=>r.name)];
            const urls=[...new Set(candidates)].filter(value=>{
                try { const u=new URL(value,location.href);
                    return u.origin===location.origin && u.protocol==='https:' && u.pathname.endsWith('.js');
                } catch { return false; }
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
        if type(box.get("revision")) is not int or box.get("kind") not in (None,"box","bonus"):
            raise ValueError("Tipo ou revisao da box nao suportado.")
        now=time.monotonic(); key=(snapshot["map"],snapshot.get("respawn_revision"),box["id"],box["revision"])
        previous=self.data_action
        same=previous and previous["key"]==key
        elapsed=now-previous["time"] if same else float("inf")
        collecting=same and previous["action"]=="collect"
        payload={"map":snapshot["map"],"id":box["id"],"revision":box["revision"],"x":box["x"],"y":box["y"],
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
                if (url.scheme=="https" and url.hostname=="interstellar-verse.com"
                        and url.path.rstrip("/").endswith("/events")):
                    self.world_feed.begin((id(page),event.get("requestId")))
                    self.probe = ManualCollectProbe(self.world_feed)
            def received(event):
                if event.get("eventName") not in (None,"message",""): return
                self.world_feed.ingest((id(page),event.get("requestId")),event.get("data"))
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
                        page = self._game_page(context)
                        # Recusa cliques enfileirados se F9/F10 ja interrompeu o bot.
                        if allowed is not None and not allowed():
                            reply.put((True, False))
                            continue
                        if operation == "screenshot":
                            result = self._capture(page)
                        elif operation == "data_target":
                            result = self._data_target(page,payload,allowed)
                        elif operation == "client_sources":
                            result = self._client_sources(page)
                        elif operation == "click":
                            result = self._click(page, payload, allowed)
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
