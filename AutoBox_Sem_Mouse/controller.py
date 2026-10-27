"""Coleta por dados do jogo."""
from math import hypot, isfinite
import time

def distance(a,b):
    return hypot(a[0]-b[0],a[1]-b[1])


def normalize_npc_profiles(profiles):
    if not isinstance(profiles,dict):return {}
    valid={}
    for name,p in profiles.items():
        if not isinstance(name,str) or not isinstance(p,dict):continue
        if (type(p.get("priority")) is int and -100<=p["priority"]<=100
                and type(p.get("radius")) is int and 150<=p["radius"]<=800
                and p.get("ammo") in ("lcb10","mcb25","mcb50","ucb100","sab50","rsb75")
                and type(p.get("orbit")) is bool):
            valid[name]={k:p[k] for k in ("priority","radius","ammo","orbit")}
    return valid

class DataFarmPlanner:
    """Motor por identidade e coordenadas; emite decisoes, nunca envia comandos."""
    def __init__(self, arrival_radius=100., include_green=False):
        self.include_green = include_green
        self.arrival_radius = arrival_radius
        self.reset()

    def reset(self):
        self.deferred = {}
        self.target = None
        self.map_id = None
        self.respawn = None
        self.started = None
        self.last_progress = None
        self.best_distance = float("inf")
        self.last_distance = float("inf")
        self.baseline = None

    def defer_target(self, now):
        if self.target is not None:
            self.deferred[self.key(self.target)]=now+30
        self.target=None

    @staticmethod
    def key(box):
        return box["id"], box.get("revision")

    def step(self, snapshot, now):
        if not snapshot.get("fresh"):
            self.reset()
            return {"phase":"paused","reason":snapshot.get("status","Aguardando dados atuais.")}
        map_id, respawn = snapshot["map"], snapshot.get("respawn_revision")
        if self.map_id is not None and (map_id!=self.map_id or respawn!=self.respawn):
            self.reset()
            return {"phase":"paused","reason":"Mapa ou renascimento mudou. Plano anterior descartado."}
        self.map_id, self.respawn = map_id, respawn
        if snapshot.get("dead"):
            self.reset()
            return {"phase":"paused","reason":"Nave destruida. Inicie novamente apos recuperar."}
        if snapshot.get("hp_percent") is not None and snapshot["hp_percent"]<=25:
            self.target=None
            return {"phase":"recover","reason":"Vida baixa. Recuperacao automatica ainda nao configurada."}
        position=snapshot["position"]
        boxes=[b for b in snapshot.get("candidates",[]) if b.get("kind") in (None,"box","bonus") or
               (self.include_green and b.get("kind")=="booty" and (snapshot.get("booty_keys") or 0)>0)]
        self.deferred={key:until for key,until in self.deferred.items() if until>now}
        boxes=[b for b in boxes if self.key(b) not in self.deferred]
        if self.target is None:
            if not boxes:
                return {"phase":"search","reason":"Nenhuma box disponivel nos dados."}
            self.target=dict(min(boxes,key=lambda b:distance(position,(b["x"],b["y"]))))
            self.started=self.last_progress=now
            self.best_distance=float("inf")
            self.baseline=snapshot.get("box_counter")
            self.baseline_keys=snapshot.get("booty_keys")
            self.last_distance=float("inf")
        current=next((b for b in snapshot.get("candidates",[]) if self.key(b)==self.key(self.target)),None)
        if current is None:
            counter=snapshot.get("box_counter")
            confirmed=(self.baseline is not None and counter is not None and counter>self.baseline
                       and self.last_distance<=self.arrival_radius)
            if self.target.get("kind")=="booty":
                confirmed=(self.baseline_keys is not None and snapshot.get("booty_keys") is not None
                           and snapshot["booty_keys"]<self.baseline_keys and self.last_distance<=self.arrival_radius)
            previous=self.target["id"]
            self.target=None
            return {"phase":"confirmed" if confirmed else "unconfirmed",
                    "reason":"Recompensa e desaparecimento observados." if confirmed else
                             "Alvo desapareceu ou mudou sem prova de coleta.",
                    "target_id":previous}
        self.target=dict(current)
        current_distance=distance(position,(current["x"],current["y"]))
        self.last_distance=current_distance
        if current_distance<self.best_distance-5:
            self.best_distance=current_distance
            self.last_progress=now
        speed=snapshot.get("speed")
        eta=current_distance/speed if type(speed) in (int,float) and isfinite(speed) and speed>0 else None
        result={"target_id":current["id"],"revision":current.get("revision"),
                "destination":(current["x"],current["y"]),"distance":current_distance,"eta":eta}
        if now-self.last_progress>=8:
            return dict(result,phase="stalled",reason="Sem aproximacao observada; nao trocar de box.")
        if current_distance<=self.arrival_radius:
            return dict(result,phase="collect",reason="Perto do alvo; aguardar coleta e confirmacao.")
        return dict(result,phase="approach",reason="Aproximar da box selecionada; manter o mesmo ID.")


class MapTravel:
    """Usa a rota calculada pelo cliente; não mantém um grafo inventado."""
    def __init__(self, session, stop, emit, destination, clock=None):
        self.session=session; self.stop=stop; self.emit=emit; self.destination=destination
        self.clock=clock or time.monotonic
        self.key=None; self.best=float("inf"); self.progress=0
        self.started=None; self.next_action=0; self.last_status=None

    def step(self, snapshot):
        if self.stop.is_set(): return False
        if not snapshot.get("fresh"): raise ValueError("Aguardando dados atuais para viajar.")
        if snapshot.get("dead") or snapshot.get("hp_percent") is None or snapshot["hp_percent"]<=25:
            raise ValueError("Recupere a nave antes de viajar.")
        if not self.destination or snapshot["map"]==self.destination: return True
        now=self.clock()
        if self.started is None: self.started=now
        if now-self.started>600: raise ValueError("Viagem excedeu 10 minutos. Confira a rota no jogo.")
        route=self.session.request("travel",{"destination":self.destination,"execute":False},
                                   allowed=lambda:not self.stop.is_set())
        if self.stop.is_set() or not route: return False
        action=route.get("action")
        if action=="arrived": return True
        if action=="blocked": raise ValueError(route.get("reason","Rota indisponível."))
        if action in ("wait","cancelled"): return False
        if action!="route": raise ValueError("Resposta de navegação inesperada.")
        key=(route.get("map"),route.get("gate"))
        distance=route.get("distance")
        if type(distance) not in (int,float) or not isfinite(distance): raise ValueError("Distância do portal indisponível.")
        if key!=self.key:
            self.key=key; self.best=float("inf"); self.progress=now; self.next_action=0
        if distance<self.best-10: self.best=distance; self.progress=now
        if now-self.progress>30: raise ValueError("Sem progresso até o portal. Viagem pausada.")
        status=(key,route.get("next_map"))
        if status!=self.last_status:
            self.emit("status","Viajando para "+self.destination+" — próximo portal: "+str(route.get("next_map")))
            self.last_status=status
        if now>=self.next_action and not self.stop.is_set():
            result=self.session.request("travel",{"destination":self.destination,"execute":True},
                                        allowed=lambda:not self.stop.is_set())
            self.next_action=now+8
            if result and result.get("action")=="blocked":
                raise ValueError(result.get("reason","Viagem bloqueada."))
        return False


class TravelWorker:
    def __init__(self,session,stop,emit,destination):
        self.session=session; self.stop=stop; self.emit=emit
        self.travel=MapTravel(session,stop,emit,destination)

    def run(self):
        self.emit("status","Iniciando viagem. F9/F10 cancelam os próximos comandos.")
        try:
            while not self.stop.is_set():
                if self.travel.step(self.session.get_world_snapshot()):
                    self.emit("status","Chegou ao mapa "+self.travel.destination+".")
                    return
                if self.stop.wait(.5): break
        except Exception as exc:
            self.emit("status","Viagem pausada: "+str(exc))
        finally:
            self.stop.set()
            self.emit("running",False)



class CloakKeeper:
    """Collection-only use of equipped cloak charges, with bounded acknowledgement."""
    def __init__(self,session,stop,emit,clock=None):
        self.session=session;self.stop=stop;self.emit=emit
        self.clock=clock or time.monotonic
        self.pending=None;self.next_check=0;self.last_status=None
    def status(self,message):
        if message!=self.last_status:
            self.last_status=message;self.emit("cloak_status",message)
    def step(self):
        now=self.clock()
        if self.stop.is_set() or now<self.next_check:return
        self.next_check=now+1
        payload={"action":"inspect" if self.pending else "ensure"}
        if self.pending:payload.update(owner=self.pending["owner"],life=self.pending["life"])
        result=self.session.request("cloak",payload,allowed=lambda:not self.stop.is_set())
        if self.stop.is_set():return
        if not isinstance(result,dict):raise ValueError("Camuflagem: leitura indisponível.")
        action=result.get("action")
        if self.pending:
            if action=="active":
                self.pending=None;self.next_check=now+5
                self.status("Camuflagem ativa e confirmada.")
            elif action=="dead":
                self.pending=None;self.status("Camuflagem aguardando renascimento.")
            elif now-self.pending["sent_at"]>=20:
                raise ValueError("Camuflagem sem confirmação. Coleta parada para evitar repetir cargas; confira o jogo.")
            return
        if action=="sent":
            if result.get("owner") is None or result.get("life") is None:
                raise ValueError("Camuflagem enviada sem identificação; confira o jogo.")
            self.pending=dict(result,sent_at=now)
            self.status("Ativando CPU de camuflagem; aguardando confirmação.")
        else:
            messages={"active":"Camuflagem ativa.","combat":"Camuflagem aguarda o fim dos tiros.",
                "jump":"Camuflagem aguarda o salto.","unequipped":"Equipe uma CPU de camuflagem; coleta continua sem camuflagem.",
                "empty":"CPU sem cargas; coleta continua sem camuflagem.",
                "wait":"Camuflagem aguarda disponibilidade/recarga.",
                "dead":"Camuflagem aguardando renascimento."}
            if action not in messages:raise ValueError("Resposta de camuflagem desconhecida.")
            self.status(messages[action])
            if action in ("unequipped","empty","wait"):self.next_check=now+5

class DataCollector:
    """Executa um alvo por vez pela interface do cliente; nao monta pacotes HTTP."""
    def __init__(self, session, stop_event, emit, clock=None, settings=None):
        self.settings=settings or {}
        self.deaths=self.settings.get("death_state",{"ids":set(),"count":0})
        self.session=session; self.stop=stop_event; self.emit=emit
        self.clock=clock or time.monotonic
        self.planner=DataFarmPlanner(arrival_radius=180, include_green=self.settings.get("green",False))
        self.travel=MapTravel(session,stop_event,emit,self.settings.get("farm_map",""),self.clock)
        self.travelling=False
        self.cloak=CloakKeeper(session,stop_event,emit,self.clock) if self.settings.get("cloak") else None

    def run(self):
        last_status=None; attempted=None
        disconnected=None; next_retry=0; retries=0
        repair_retry=0; recovering=False
        self.emit("running",True)
        try:
            while not self.stop.is_set():
                snapshot=self.session.get_world_snapshot()
                now=self.clock()
                if (self.settings.get("min_hp") is not None and snapshot.get("fresh")
                        and (snapshot.get("hp_percent") is None or snapshot["hp_percent"]<=self.settings["min_hp"])):
                    self.emit("status","Coleta entre combates interrompida para avaliar reparo.")
                    break
                if not snapshot.get("fresh") and self.settings.get("reconnect"):
                    if disconnected is None:
                        disconnected=now
                        self.emit("running",False)
                        self.emit("status","Conexão interrompida. Aguardando reconexão; F9 cancela.")
                    if now>=next_retry:
                        if not self.session.ready.is_set(): break
                        try:
                            result=self.session.request("reconnect",{"reload":now-disconnected>=30},
                                allowed=lambda:not self.stop.is_set())
                            if result and result.get("action") in ("login","closed"):
                                self.emit("status","Abra o jogo e faça login novamente para continuar.")
                                break
                        except Exception:
                            pass
                        retries+=1
                        next_retry=now+min(60,5*2**min(retries,4))
                    if self.stop.wait(.5): break
                    continue
                if disconnected is not None:
                    self.planner.reset()
                    disconnected=None; retries=0; attempted=None
                    self.emit("running",True)
                    self.emit("status","Leitura recuperada. Retomando coleta.")
                if snapshot.get("dead"):
                    repair=snapshot.get("repair") or {}
                    death_id=repair.get("id")
                    if death_id is not None and death_id not in self.deaths["ids"]:
                        self.deaths["ids"].add(death_id)
                        self.deaths["count"]+=1
                        self.emit("status","Nave destruída. Mortes na sessão: "+str(self.deaths["count"]))
                    limit=self.settings.get("max_deaths",3)
                    if limit>0 and self.deaths["count"]>=limit:
                        self.emit("status","Limite de mortes atingido. Coleta encerrada.")
                        break
                    option=self.settings.get("respawn","Desativado")
                    if option not in ("base","portal","spot"): break
                    if not recovering:
                        self.emit("running",False)
                        recovering=True
                    if death_id and now>=repair_retry:
                        result=self.session.request("respawn",{"death_id":death_id,"option":option,
                            "max_cost":self.settings.get("max_cost",0)},allowed=lambda:not self.stop.is_set())
                        repair_retry=now+10
                        if result and result.get("action")=="blocked":
                            self.emit("status","Renascimento indisponível ou acima do custo permitido. Confira no jogo.")
                            break
                    if self.stop.wait(.5): break
                    continue
                if recovering:
                    self.planner.reset()
                    recovering=False
                    if snapshot.get("hp_percent") is not None and snapshot["hp_percent"]<=25:
                        self.emit("status","Renascimento concluído. Recupere a vida antes de iniciar novamente.")
                        break
                    self.emit("running",True)
                if self.cloak and snapshot.get("fresh") and (snapshot.get("hp_percent") or 0)>25:
                    self.cloak.step()
                destination=self.settings.get("farm_map","")
                if destination and snapshot.get("fresh") and snapshot.get("map")!=destination:
                    if not self.travelling:
                        self.travel=MapTravel(self.session,self.stop,self.emit,destination,self.clock)
                        self.emit("running",False)
                        self.travelling=True
                    self.planner.reset()
                    self.travel.step(snapshot)
                    if self.stop.wait(.5): break
                    continue
                if self.travelling:
                    self.planner.reset()
                    self.travelling=False
                    attempted=None
                    self.emit("running",True)
                    self.emit("status","Mapa de coleta alcançado. Procurando boxes.")
                decision=self.planner.step(snapshot,now)
                phase=decision["phase"]
                status=(phase,decision.get("target_id"))
                if status!=last_status:
                    self.emit("status",decision["reason"]+(" Alvo: "+decision["target_id"] if decision.get("target_id") else ""))
                    last_status=status
                if phase=="stalled":
                    self.emit("failed",None)
                    self.emit("status","Recurso sem progresso; ignorado por 30 s. Procurando outro alvo.")
                    self.planner.defer_target(now)
                    attempted=None
                    if self.stop.wait(.5):break
                    continue
                if phase in ("paused","recover"):
                    break
                if phase=="confirmed": self.emit("confirmed",None)
                elif phase=="unconfirmed": self.emit("failed",None)
                elif phase in ("approach","collect"):
                    key=(decision["target_id"],decision.get("revision"))
                    if key!=attempted:
                        self.emit("attempt",None); attempted=key
                    if self.stop.is_set(): break
                    self.session.request("data_target",{
                        "map":snapshot["map"],"respawn_revision":snapshot.get("respawn_revision"),
                        "id":decision["target_id"],"revision":decision.get("revision"),
                        "allow_green":self.settings.get("green",False)},
                        allowed=lambda:not self.stop.is_set())
                if self.stop.wait(.15): break
        except Exception as exc:
            if self.cloak:self.emit("cloak_status","Camuflagem automática interrompida: "+str(exc))
            self.emit("status","Coleta por dados pausada: "+str(exc))
        finally:
            self.stop.set()
            self.emit("running",False)


class SessionEarnings:
    """Conta recompensas novas de boxes e combate durante o farm ativo."""
    def __init__(self, clock=None):
        self.clock=clock or time.monotonic
        self.recent=[]
        self.seen = set()
        self.order = []
        self.total = 0
        self.primed = False

    def observe(self, snapshot, active=False):
        if not snapshot.get("fresh"):
            return
        for event in snapshot.get("rewards", []):
            key = (event.get("id"), event.get("time"))
            if key[0] is None or key in self.seen:
                continue
            self.seen.add(key)
            self.order.append(key)
            amount = event.get("uridium") if event.get("type")=="kill" else event.get("amount")
            if (self.primed and active and (event.get("type")=="kill" or (event.get("type")=="box-collected" and event.get("field")=="uridium"))
                    and not event.get("petCollected") and not event.get("pet")
                    and type(amount) in (int,float) and isfinite(amount) and amount>0):
                self.total += amount
                stamp=self.clock()
                server,event_time=snapshot.get("server_time"),event.get("time")
                if type(server) in (int,float) and type(event_time) in (int,float) and isfinite(server) and isfinite(event_time):
                    stamp-=max(0,server-event_time)
                self.recent.append((stamp,amount))
        self.primed = True
        while len(self.order)>2000:
            self.seen.discard(self.order.pop(0))

    def last_hour(self):
        cutoff=self.clock()-3600
        self.recent=[(stamp,amount) for stamp,amount in self.recent if stamp>cutoff]
        return sum(amount for _,amount in self.recent)

    def hourly(self, seconds):
        return self.total*3600/seconds if seconds>=30 else None



class FinishPursuit:
    """Bounded pursuit of one wounded target; navigation stays in the existing bridge."""
    def __init__(self,enabled=False,hp=20,radius=150,max_distance=3000,seconds=60):
        if not (5<=hp<=50 and 150<=radius<=600 and 1000<=max_distance<=8000 and 10<=seconds<=180):
            raise ValueError("Configuração de perseguição inválida.")
        self.enabled=enabled;self.hp=hp;self.radius=radius
        self.max_distance=max_distance;self.seconds=seconds
        self.active=False;self.started=None;self.previous=None;self.velocity=(0.,0.)
    def step(self,npc,ship,now,engaged):
        if not self.enabled:return False
        x,y=npc["x"],npc["y"];d=distance(ship,(x,y))
        fleeing=False
        if self.previous:
            then,px,py=self.previous;dt=now-then
            if dt>0:
                vx,vy=(x-px)/dt,(y-py)/dt
                speed=distance((0,0),(vx,vy))
                if speed>1000:vx*=1000/speed;vy*=1000/speed
                self.velocity=(self.velocity[0]*.65+vx*.35,self.velocity[1]*.65+vy*.35)
                fleeing=d>self.radius+20 and ((x-px)*(x-ship[0])+(y-py)*(y-ship[1]))/max(d,1)>2
        self.previous=(now,x,y)
        hp,maximum=npc.get("hp"),npc.get("maxHp")
        known=type(hp) in (int,float) and type(maximum) in (int,float) and isfinite(hp) and isfinite(maximum) and maximum>0 and hp>0
        if not engaged or not known or hp/maximum*100>self.hp+5:
            self.active=False
            return False
        if not self.active and hp/maximum*100<=self.hp and fleeing:
            self.active=True;self.started=now
        if self.active:
            if d>self.max_distance: raise ValueError("Finalização cancelada: distância máxima de perseguição.")
            if now-self.started>=self.seconds: raise ValueError("Finalização cancelada: tempo máximo de perseguição.")
        return self.active

class CombatTargetGone(Exception):
    """Alvo saiu da leitura durante o envio do comando."""


class CombatLowHealth(Exception):
    """O cliente detectou vida baixa após a última leitura do controlador."""


class NpcTestWorker:
    """Uma luta por execução; Ctrl só é repetido após confirmação de estado."""
    def __init__(self,session,stop,emit,kind="mordon",destination="",min_hp=40,clock=None,orbit=False,radius=450,repair_portal=False,portal_fight=False,ammo="lcb10",rocket="none",restock=None,pursuit_enabled=False,pursuit_hp=20,pursuit_radius=150,pursuit_max_distance=3000,pursuit_seconds=60,npc_profiles=None):
        self.session=session; self.stop=stop; self.emit=emit
        self.kinds=set(kind if isinstance(kind,(list,tuple,set)) else [kind])
        self.kind=", ".join(sorted(self.kinds))
        self.destination=destination; self.min_hp=min_hp; self.clock=clock or time.monotonic
        self.orbit=orbit; self.radius=max(150,min(800,radius)); self.repair_portal=repair_portal; self.direction=1
        self.ammo=ammo; self.rocket=rocket; self.next_rocket=0
        self.restock=restock or {}; self.next_restock=0
        self.pursuit=FinishPursuit(pursuit_enabled,pursuit_hp,pursuit_radius,pursuit_max_distance,pursuit_seconds)
        self.finish_stop=True; self.minimum_start_hp=80; self.max_fight_seconds=180
        self.portal_fight=portal_fight; self.fight_gate=None; self.gate_best=float("inf")
        self.target=None; self.context=None; self.pending=None; self.next_move=0
        self.started=None; self.progress=None; self.best_distance=float("inf"); self.lowest=None
        self.damage=False; self.baseline_xp=None; self.last_phase=None; self.previous_distance=None
        self.attack_sent=False
        self.baseline_kills=set()
        self.npc_profiles=normalize_npc_profiles(npc_profiles)
        self.lock_retries=0
        self.report={"mode":"single_npc_test","kind":self.kind,"allowed_kinds":sorted(self.kinds),"laser":ammo,"missile":rocket,"status":"Preparando","actions":[],
                     "damage_observed":False,"kill_confirmed":False,"stop_confirmed":False}

    def publish(self,status):
        self.report["status"]=status
        self.report["damage_observed"]=self.damage
        self.emit("npc_report",dict(self.report,actions=list(self.report["actions"])))
        if status!=self.last_phase:
            self.emit("status",status); self.last_phase=status

    def action(self,name,**options):
        payload=dict(self.context,id=self.target["id"],revision=self.target.get("respawnRevision"),
                     min_hp=self.min_hp,action=name,ammo=self.ammo,rocket=self.rocket,**options)
        result=self.session.request("npc_action",payload,allowed=lambda:not self.stop.is_set())
        if not isinstance(result,dict): return {"action":"cancelled"}
        if name=="attack" and result.get("action") in ("attack_sent","attacking"):
            self.attack_sent=True
        self.report["actions"].append({"seconds":round(self.clock()-self.started,2),"action":name,"result":result.get("action"),"distance":self.report.get("target_distance")})
        self.report["actions"]=self.report["actions"][-40:]
        if result.get("action")=="gone":
            raise CombatTargetGone()
        if result.get("action")=="low_hp":
            raise CombatLowHealth("Vida no limite detectada pelo cliente.")
        return result

    def cease_fire(self):
        self.report["stop_confirmed"]=False
        if self.target is None or self.context is None: return
        try:
            payload=dict(self.context,id=self.target["id"],revision=self.target.get("respawnRevision"),
                         min_hp=self.min_hp,action="stop",allow_ctrl_stop=not getattr(self,"stop_toggle_sent",False))
            before=self.session.get_world_snapshot().get("sequence")
            result=self.session.request("npc_action",payload,allowed=lambda:True)
            self.report["last_stop_result"]=(result or {}).get("action")
            if self.report["last_stop_result"] in ("stop_sent","stop_ctrl_sent"): self.stop_toggle_sent=True
            self.report["actions"].append({"seconds":round(self.clock()-self.started,2),"action":"stop","result":(result or {}).get("action")})
            self.report["actions"]=self.report["actions"][-40:]
            if result and result.get("action")=="stopped":
                self.report["stop_confirmed"]=True; return
            # Prefer explicit deselection; allow one guarded Ctrl fallback per fight, then wait for echo.
            for _ in range(20):
                snap=self.session.get_world_snapshot()
                if (snap.get("fresh") and snap.get("map")==self.context["map"] and
                    snap.get("respawn_revision")==self.context["life"] and
                    snap.get("combat",{}).get("attacking") is False and not snap.get("combat",{}).get("secondaryVolley") and
                    type(before) is int and type(snap.get("sequence")) is int and snap["sequence"]>before):
                    self.report["stop_confirmed"]=True; return
                time.sleep(.1)
        except Exception:
            pass

    def confirm_target_end(self):
        confirmed=False
        self.publish("Aguardando confirmação da derrota e da recompensa do NPC.")
        for _ in range(50):
            if self.stop.is_set(): break
            snap=self.session.get_world_snapshot()
            if (self.stop.is_set() or not snap.get("fresh") or snap.get("dead") or snap.get("map")!=self.context["map"]
                or snap.get("respawn_revision")!=self.context["life"]): break
            target=next((n for n in snap.get("npc_candidates",[]) if str(n.get("id"))==str(self.target["id"])
                         and n.get("respawnRevision")==self.target.get("respawnRevision")),None)
            xp=snap.get("account",{}).get("xp")
            self.report["attacking"]=snap.get("combat",{}).get("attacking")
            self.report["hp_percent"]=snap.get("hp_percent")
            absent=target is None or target.get("hp",0)<=0
            xp_gained=(type(xp) in (int,float) and type(self.baseline_xp) in (int,float)
                       and xp>self.baseline_xp)
            new_kill=any(e.get("type")=="kill" and e.get("id") is not None
                         and (e.get("id"),e.get("time")) not in self.baseline_kills
                         and not e.get("petCollected") and not e.get("pet")
                         for e in snap.get("rewards",[]))
            # A fast kill can disappear before a lower HP sample or attack echo arrives.
            # Require a dispatched attack and fresh reward evidence, never disappearance alone.
            confirmed=absent and ((self.damage and xp_gained) or
                                  (self.attack_sent and (xp_gained or new_kill)))
            if confirmed: break
            if self.stop.wait(.1): break
        self.report["kill_confirmed"]=confirmed
        self.publish("NPC derrotado e recompensa observada. Teste concluído." if confirmed else
                     "Alvo saiu da leitura; derrota sem confirmação de recompensa. Teste encerrado.")

    def recover_at_portal(self):
        started=self.clock(); next_move=0; gate=None; repair_sent=None
        stop_attempts=0
        while not self.stop.is_set():
            snap=self.session.get_world_snapshot(); now=self.clock()
            if (not snap.get("fresh") or snap.get("dead") or snap.get("map")!=self.context["map"]
                or snap.get("respawn_revision")!=self.context["life"]):
                raise ValueError("Recuperação interrompida: leitura, mapa ou vida mudou.")
            combat=snap.get("combat",{})
            firing=bool(combat.get("attacking") or combat.get("secondaryVolley"))
            self.report["attacking"]=combat.get("attacking")
            self.report["hp_percent"]=snap.get("hp_percent")
            self.report["repair_active"]=combat.get("repairActive",False)
            if now-started>180: raise ValueError("Recuperação excedeu 3 minutos; confira o jogo.")
            if repair_sent is not None and not combat.get("repairing") and now-repair_sent>5:
                raise ValueError("CPU de reparo não confirmou ativação; confira equipamento e jogo.")
            if now>=next_move:
                result=self.action("retreat",gate=gate,enable_repair=not firing and repair_sent is None)
                next_move=now+1.5
                if result.get("action")!="retreating":
                    raise ValueError("Retorno ao portal não aceito: "+result.get("action","?"))
                gate=result.get("gate"); self.report["recovery_gate"]=gate
                self.report["portal_distance"]=result.get("distance")
                if result.get("repair")=="unavailable": raise ValueError("Equipe uma CPU/robô de reparo no jogo.")
                if result.get("repair") in ("sent","enabled") and repair_sent is None: repair_sent=now
                if not firing and result.get("distance",99999)<=80 and (snap.get("hp_percent") or 0)>=90:
                    self.report["recovered"]=True
                    self.publish("Recuperada no portal com pelo menos 90% de vida.")
                    return
            if firing and stop_attempts>=3 and now-started>=15:
                raise ValueError("Ataque não parou após 3 tentativas. Farm interrompido; pressione Ctrl no jogo e confira o reparo.")
            if firing and stop_attempts<3:
                self.cease_fire(); stop_attempts+=1
                self.report["stop_attempts"]=stop_attempts
            elif not firing:
                self.report["stop_confirmed"]=True
            self.publish("Indo ao portal; aguardando parada dos tiros." if firing else "Indo ao portal; reparo aguarda as condições de combate do jogo.")
            if self.stop.wait(.1): break

    def run(self):
        travel=MapTravel(self.session,self.stop,self.emit,self.destination,self.clock)
        self.started=self.clock()
        try:
            while not self.stop.is_set():
                snap=self.session.get_world_snapshot(); now=self.clock()
                if not snap.get("fresh"): raise ValueError("Leitura interrompida. Teste encerrado.")
                if snap.get("dead"): raise ValueError("Nave destruída. Teste encerrado.")
                hp=snap.get("hp_percent")
                self.report["hp_percent"]=hp
                if hp is not None and hp<=self.min_hp and self.repair_portal and self.target is not None:
                    self.recover_at_portal()
                    break
                if hp is None or hp<=self.min_hp:
                    raise ValueError("Vida no limite. Interrompendo tiros; recupere a nave manualmente.")
                if self.destination and snap["map"]!=self.destination:
                    if self.target is not None: raise ValueError("Mapa mudou durante a luta.")
                    if not travel.step(snap):
                        if self.stop.wait(.5): break
                        continue
                if self.target is None:
                    if hp<self.minimum_start_hp: raise ValueError("Recupere a vida antes de iniciar outra luta.")
                    combat=snap.get("combat",{})
                    if combat.get("attacking"): raise ValueError("Pare o ataque atual antes do teste.")

                    candidates=[n for n in snap.get("npc_candidates",[]) if
                                (n.get("kind") or n.get("type")) in self.kinds and
                                type(n.get("hp")) in (int,float) and n["hp"]>0 and
                                type(n.get("respawnRevision")) is int]
                    if not candidates: raise ValueError("Nenhum NPC desse tipo disponível no mapa.")
                    self.target=dict(min(candidates,key=lambda n:(
                        self.npc_profiles.get(n.get("kind") or n.get("type"),{}).get("priority",0),
                        distance(snap["position"],(n["x"],n["y"])))))
                    self.kind=self.target.get("kind") or self.target.get("type")
                    profile=self.npc_profiles.get(self.kind,{})
                    self.ammo=profile.get("ammo",self.ammo)
                    self.radius=max(150,min(800,profile.get("radius",self.radius)))
                    self.orbit=profile.get("orbit",self.orbit)
                    self.report.update(kind=self.kind,laser=self.ammo,radius=self.radius)
                    self.context={"map":snap["map"],"life":snap.get("respawn_revision")}
                    self.baseline_xp=snap.get("account",{}).get("xp")
                    self.progress=now
                    self.report["target_id"]=self.target["id"]
                    self.report["map"]=snap["map"]
                if self.restock and now>=self.next_restock:
                    for kind,item in (("laser",self.ammo),("missile",self.rocket)):
                        if not self.restock.get(kind) or item=="none": continue
                        result=self.session.request("restock",dict(self.restock,item=item,kind=kind,
                            quantity=self.restock[kind+"_quantity"],threshold=self.restock[kind+"_threshold"]),
                            allowed=lambda:not self.stop.is_set())
                        if result.get("action")=="bought":
                            self.emit("status","Compra confirmada: "+item+" x "+str(result["quantity"]))
                        elif result.get("action")=="funds":
                            self.emit("status","Compra não realizada: saldo/reserva insuficiente para "+item)
                    self.next_restock=now+5
                if snap["map"]!=self.context["map"] or snap.get("respawn_revision")!=self.context["life"]:
                    raise ValueError("Mapa ou vida da nave mudou durante o teste.")
                current=next((n for n in snap.get("npc_candidates",[]) if str(n["id"])==str(self.target["id"])
                             and n.get("respawnRevision")==self.target.get("respawnRevision")),None)
                xp=snap.get("account",{}).get("xp")
                if current is None or current.get("hp",0)<=0:
                    self.confirm_target_end()
                    break
                self.target=dict(current)
                health=current["hp"]+(current.get("shield") or 0)
                if self.lowest is not None and health<self.lowest:
                    self.damage=True; self.progress=now
                self.lowest=health if self.lowest is None else min(self.lowest,health)
                self.report["target_hp"]=current["hp"]; self.report["target_shield"]=current.get("shield")
                d=distance(snap["position"],(current["x"],current["y"]))
                self.report["target_distance"]=round(d,1)
                self.report["attacking"]=snap.get("combat",{}).get("attacking")
                if self.previous_distance is not None and d<self.previous_distance-2: self.progress=now
                self.previous_distance=d
                self.best_distance=min(self.best_distance,d)
                if now-self.started>self.max_fight_seconds: raise ValueError("Luta excedeu o limite de "+str(self.max_fight_seconds//60)+" minutos.")
                if now-self.progress>15: raise ValueError("Sem aproximação ou dano por 15 segundos.")
                combat=snap.get("combat",{})
                selected=str(combat.get("target_id"))==str(current["id"])
                was_pursuing=self.pursuit.active
                pursuing=self.pursuit.step(current,snap["position"],now,selected and combat.get("attacking") is True and not self.portal_fight)
                self.report["pursuit_active"]=pursuing
                if pursuing and not was_pursuing: self.emit("status","Perseguição para finalização iniciada: "+str(current["id"]))
                elif was_pursuing and not pursuing: self.emit("status","Finalização encerrada; retomando comportamento normal.")
                if self.pending:
                    name,sent=self.pending
                    confirmed=(name=="select" and selected) or (name=="attack" and combat.get("attacking") is True) or (name=="ammo" and combat.get("selectedAmmo")==self.ammo)
                    if confirmed:
                        self.pending=None
                        self.progress=now
                    elif now-sent>5:
                        if name=="select" and self.lock_retries<2 and combat.get("attacking") is False:
                            self.lock_retries+=1;self.pending=None
                            self.publish("Mira não confirmada; recuperando seleção (%s/2)." % self.lock_retries)
                            continue
                        raise ValueError("Comando "+name+" não foi confirmado pelo jogo.")
                    else:
                        if self.stop.wait(.1): break
                        continue
                if selected and combat.get("attacking") is True and combat.get("selectedAmmo")!=self.ammo:
                    raise ValueError("O jogo trocou a munição escolhida. Teste encerrado.")
                if selected and combat.get("attacking") is True and self.rocket!="none" and now>=self.next_rocket:
                    missile=self.action("rocket")
                    self.report["rocket_status"]=missile.get("action")
                    self.next_rocket=now+(3.2 if missile.get("action")=="rocket_sent" else 1)
                if selected and combat.get("attacking") is not True:
                    if not self.attack_sent:
                        self.baseline_xp=xp
                        self.baseline_kills={(e.get("id"),e.get("time")) for e in snap.get("rewards",[])
                                             if e.get("type")=="kill"}
                    result=self.action("attack")
                    if result.get("action") not in ("attack_sent","attacking","ammo_sent"):
                        raise ValueError("Ataque não aceito: "+result.get("action","?"))
                    self.pending=("ammo" if result.get("action")=="ammo_sent" else "attack",now)
                    self.publish("Aguardando confirmação do ataque; mantendo o mesmo NPC.")
                elif pursuing:
                    if now>=self.next_move:
                        vx,vy=self.pursuit.velocity
                        result=self.action("approach",close_approach=False,radius=self.pursuit.radius,
                            pursuit=True,lead_x=max(-150,min(150,vx*.4)),lead_y=max(-150,min(150,vy*.4)))
                        self.next_move=now+.2
                        if result.get("action") not in ("move_sent","in_range"):
                            raise ValueError("Finalização cancelada: rota indisponível.")
                    self.publish("Perseguindo NPC para finalização")
                elif selected and self.portal_fight:
                    if now>=self.next_move:
                        result=self.action("portal_lure",gate=self.fight_gate); self.next_move=now+.15
                        if result.get("action")!="luring": raise ValueError("Condução ao portal não aceita: "+result.get("action","?"))
                        self.fight_gate=result.get("gate"); self.report["combat_gate"]=self.fight_gate
                        gate_distance=result.get("distance")
                        if type(gate_distance) in (int,float) and gate_distance<self.gate_best-10:
                            self.gate_best=gate_distance; self.progress=now
                    self.publish("Conduzindo o NPC e mantendo a luta perto do portal.")
                elif selected and d>self.radius+40:
                    if now>=self.next_move:
                        result=self.action("approach",close_approach=False,radius=self.radius); self.next_move=now+.35
                        if result.get("action") not in ("move_sent","in_range"): raise ValueError("Aproximação não aceita: "+result.get("action","?"))
                    self.publish("Perseguindo o mesmo NPC na distância de ataque.")
                elif not selected:
                    result=self.action("select")
                    if result.get("action")=="not_visible":
                        if now>=self.next_move:
                            result=self.action("approach",close_approach=False,radius=self.radius); self.next_move=now+.5
                            if result.get("action") not in ("move_sent","in_range"):
                                raise ValueError("Aproximação não aceita: "+result.get("action","?"))
                        self.publish("NPC não clicável; aproximando com distância de segurança para selecionar.")
                    elif result.get("action")=="select_sent":
                        self.pending=("select",now)
                        self.publish("Aguardando confirmação do alvo NPC.")
                    else:
                        raise ValueError("NPC não selecionado: "+result.get("action","?"))
                else:
                    if (self.orbit or d<self.radius-40) and now>=self.next_move:
                        result=self.action("orbit",radius=self.radius,direction=self.direction,rotate=self.orbit); self.next_move=now+.15
                        if result.get("action")!="orbiting":
                            raise ValueError("Movimento circular não aceito: "+result.get("action","?"))
                        self.direction=result.get("direction",self.direction)
                    self.publish(("Circulando e atacando " if self.orbit else "Atacando ")+self.kind+" com "+self.ammo.upper()+". Use Pausar NPC para interromper.")
                if self.stop.wait(.1): break
        except CombatTargetGone:
            self.confirm_target_end()
        except CombatLowHealth:
            if self.repair_portal and self.target is not None and not self.stop.is_set():
                try:
                    self.publish("Vida no limite detectada pelo jogo; iniciando retorno ao portal.")
                    self.recover_at_portal()
                except Exception as exc:
                    self.publish(str(exc))
            else:
                self.publish("Vida no limite. Interrompendo tiros; recuperação automática desativada.")
        except Exception as exc:
            self.publish(str(exc))
        finally:
            if self.pursuit.active:
                self.emit("status","Finalização encerrada: "+("cancelamento manual." if self.stop.is_set() else self.report["status"]))
            self.pursuit.active=False
            self.report["pursuit_active"]=False
            if self.stop.is_set(): self.publish("Farm cancelado.")
            self.cease_fire()
            if self.finish_stop: self.stop.set()
            if self.target is not None and not self.report["stop_confirmed"]:
                self.report["status"]+=" Não foi possível confirmar a parada; confira o jogo."
                self.emit("status",self.report["status"])
            self.emit("npc_report",dict(self.report))
            self.emit("running",False)


class BudgetStop:
    """A collection slice shares global cancellation but cannot stop its parent farm."""
    def __init__(self,parent,seconds,clock=None):
        self.parent=parent;self.clock=clock or time.monotonic
        self.deadline=self.clock()+seconds;self.done=False
    def is_set(self):return self.done or self.parent.is_set() or self.clock()>=self.deadline
    def set(self):self.done=True
    def wait(self,seconds):
        if self.is_set():return True
        self.parent.wait(min(seconds,max(0,self.deadline-self.clock())))
        return self.is_set()


class NpcFarmWorker:
    """Encadeia lutas confirmadas; falhas e F9 encerram o ciclo."""
    def __init__(self,session,stop,emit,**settings):
        self.session=session; self.stop=stop; self.emit=emit; self.settings=settings
        self.kills=0; self.last=None
        self.hybrid=self.settings.pop("hybrid",False)
        self.collect_settings=self.settings.pop("collect_settings",{})
        self.settings["npc_profiles"]=normalize_npc_profiles(self.settings.get("npc_profiles"))

    def collect_interval(self):
        budget=BudgetStop(self.stop,10,self.settings.get("clock"))
        def relay(event,data):
            if event=="running":return
            if event in ("confirmed","failed"):budget.set()
            self.emit(event,data)
        settings=dict(self.collect_settings,reconnect=False,respawn="Desativado",min_hp=self.settings.get("min_hp",40))
        DataCollector(self.session,budget,relay,clock=self.settings.get("clock"),settings=settings).run()

    def relay(self,event,data):
        if event=="running": return
        if event=="npc_report":
            data=dict(data,mode="continuous_npc_farm",kills=self.kills)
        self.emit(event,data)

    def run(self):
        kinds=self.settings.get("kind","mordon")
        kinds=set(kinds if isinstance(kinds,(list,tuple,set)) else [kinds])
        limit=self.settings.get("min_hp",40)
        try:
            while not self.stop.is_set():
                snap=self.session.get_world_snapshot()
                if not snap.get("fresh") or snap.get("dead"):
                    raise ValueError("Farm interrompido: dados indisponíveis ou nave destruída.")
                hp=snap.get("hp_percent")
                if hp is None: raise ValueError("Vida indisponível; farm interrompido.")
                initial_repair=self.last is None and hp<80
                if initial_repair:
                    engine=NpcTestWorker(self.session,self.stop,self.relay,**self.settings)
                    engine.context={"map":snap["map"],"life":snap.get("respawn_revision")}
                    target_id=snap.get("combat",{}).get("target_id")
                    engine.target=next((dict(n) for n in snap.get("npc_candidates",[]) if str(n.get("id"))==str(target_id)),
                                       {"id":"__startup_repair__","respawnRevision":None})
                    engine.started=engine.clock()
                    self.last=engine
                    self.emit("status","Vida baixa ao iniciar: indo ao portal e ativando reparador antes do farm.")
                if hp<=limit or initial_repair:
                    if not initial_repair and (not self.settings.get("repair_portal") or self.last is None):
                        raise ValueError("Vida no limite; habilite recuperação ou repare manualmente.")
                    self.last.report["recovered"]=False
                    self.last.recover_at_portal()
                    if self.stop.is_set(): break
                    if not self.last.report.get("recovered"):
                        raise ValueError("Recuperação não concluída; farm interrompido.")
                    continue
                destination=self.settings.get("destination","")
                present=any((n.get("kind") or n.get("type")) in kinds and (n.get("hp") or 0)>0
                            for n in snap.get("npc_candidates",[]))
                if not present and (not destination or snap.get("map")==destination):
                    self.emit("status","Aguardando NPC dos tipos marcados. Derrotados: "+str(self.kills))
                    if self.hybrid:self.collect_interval()
                    if self.stop.wait(1): break
                    continue
                engine=NpcTestWorker(self.session,self.stop,self.relay,**self.settings)
                engine.finish_stop=False
                engine.max_fight_seconds=900
                engine.minimum_start_hp=80 if self.last is None else limit+.01
                self.last=engine
                engine.run()
                if self.stop.is_set(): break
                if not engine.report.get("stop_confirmed"): break
                if engine.report.get("kill_confirmed"):
                    self.kills+=1
                    self.relay("npc_report",engine.report)
                    if self.hybrid and not self.stop.is_set():self.collect_interval()
                elif not engine.report.get("recovered"):
                    break
                if self.stop.wait(.2): break
        except Exception as exc:
            self.emit("status",str(exc))
        finally:
            self.stop.set()
            self.emit("running",False)


class GalaxyWorker:
    """Um lote por confirmação; nunca repete um giro de resultado desconhecido."""
    def __init__(self,session,stop,emit,settings,clock=None):
        self.session=session;self.stop=stop;self.emit=emit;self.settings=settings
        self.clock=clock or time.monotonic
        self.used=0;self.pending=None
    def run(self):
        try:
            while not self.stop.is_set():
                now=self.clock()
                if self.pending:
                    result=self.session.request("galaxy",{"action":"inspect"},allowed=lambda:not self.stop.is_set())
                    if result.get("revision",0)>self.pending["revision"]:
                        self.used+=self.pending["count"];self.pending=None
                        self.emit("status","Galaxy Gate: "+str(self.used)+" energias confirmadas.")
                    elif now-self.pending["time"]>20:
                        raise ValueError("Giro sem confirmação. Automação parada para evitar gasto duplicado; confira o jogo.")
                elif self.used>=self.settings["limit"]:
                    self.emit("status","Galaxy Gate: limite de energias atingido.");break
                else:
                    result=self.session.request("galaxy",dict(self.settings,action="spin",remaining=self.settings["limit"]-self.used),
                        allowed=lambda:not self.stop.is_set())
                    if result.get("action")=="sent": self.pending=dict(result,time=now)
                    elif result.get("action")=="limit":
                        self.emit("status","Galaxy Gate: energias insuficientes para os lotes marcados ou reserva de uridium atingida.");break
                    elif result.get("action") not in ("wait","cancelled"):
                        raise ValueError("Resposta do Galaxy Gate não reconhecida.")
                if self.stop.wait(.5):break
        except Exception as exc:
            self.emit("status",str(exc))
        finally:
            self.stop.set()


class SkylabWorker:
    """One normal upgrade at a time; unknown outcomes stop instead of retrying."""
    def __init__(self,session,stop,emit,target=20,reserve=0,clock=None):
        if type(target) is not int or not 1<=target<=20 or type(reserve) is not int or not 0<=reserve<=1000000000:
            raise ValueError("Limites do Skylab inválidos.")
        self.session=session;self.stop=stop;self.emit=emit
        self.settings=dict(target=target,reserve=reserve)
        self.clock=clock or time.monotonic
        self.pending=None;self.context=None;self.last_status=None
    def status(self,text):
        if text!=self.last_status:
            self.last_status=text;self.emit("skylab_status",text)
    def request(self,action,**extra):
        return self.session.request("skylab",dict(self.settings,action=action,**extra),allowed=lambda:not self.stop.is_set())
    def run(self):
        try:
            while not self.stop.is_set():
                snap=self.request("inspect")
                if self.stop.is_set():break
                if not isinstance(snap,dict) or snap.get("action")!="snapshot" or not snap.get("rows"):
                    raise ValueError("Leitura do Skylab indisponível.")
                context=(snap.get("owner"),snap.get("life"))
                if None in context:raise ValueError("Identificação da sessão ausente.")
                if self.context is None:self.context=context
                elif self.context!=context:raise ValueError("Conta ou vida mudou; reinicie o Skylab após conferir o jogo.")
                self.emit("skylab_rows",snap["rows"])
                rows=snap["rows"];now=self.clock()
                if self.pending:
                    p=self.pending;row=next((r for r in rows if r["id"]==p["module"]),None)
                    if not row:raise ValueError("Módulo perdido durante confirmação.")
                    if snap["revision"]>p["revision"] and (row["level"]>=p["next_level"] or
                        (row.get("job") or {}).get("level")==p["next_level"]):
                        self.status("Construção confirmada: "+row["name"]+" → nível "+str(p["next_level"]))
                        self.pending=None
                    elif now-p["sent_at"]>=30:
                        raise ValueError("Construção sem confirmação. Skylab parado; confira o jogo antes de reiniciar.")
                    if self.stop.wait(2):break
                    continue
                jobs=[r for r in rows if r.get("job")]
                if jobs:
                    self.status("Aguardando construção: "+", ".join(r["name"] for r in jobs))
                elif all(r["level"]>=r["max"] for r in rows):
                    self.status("Skylab: todos os módulos atingiram o nível solicitado.");return
                else:
                    order=("basic","solar","storage","prometium","endurium","terbium","transport","xeno","prometid","duranium","promerium","seprom")
                    eligible=[r for r in rows if r["reason"]=="pronto"]
                    eligible.sort(key=lambda r:(r["level"],order.index(r["id"]) if r["id"] in order else 99))
                    if eligible:
                        row=eligible[0]
                        if self.stop.is_set():break
                        result=self.request("upgrade",owner=context[0],life=context[1],revision=snap["revision"],module=row["id"],level=row["level"])
                        if self.stop.is_set():break
                        if not isinstance(result,dict):raise ValueError("Resposta de construção indisponível.")
                        if result.get("action")=="sent":
                            self.pending=dict(module=row["id"],next_level=row["level"]+1,revision=snap["revision"],sent_at=now)
                            self.status("Aguardando confirmação: "+row["name"])
                        elif result.get("action") not in ("changed","wait","cancelled"):
                            raise ValueError("Construção não reconhecida; confira o Skylab.")
                    else:
                        self.status("Aguardando recursos, créditos, energia ou pré-requisitos. Confira os módulos abaixo.")
                if self.stop.wait(2 if self.pending else 10):break
            self.status("Skylab parado. Construções já iniciadas continuam no jogo.")
        except Exception as exc:
            self.status("Skylab interrompido: "+str(exc))
        finally:
            self.stop.set()
