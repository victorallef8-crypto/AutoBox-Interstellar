"""Coleta por dados do jogo."""
from math import hypot, isfinite
import time

def distance(a,b):
    return hypot(a[0]-b[0],a[1]-b[1])

class DataFarmPlanner:
    """Motor por identidade e coordenadas; emite decisoes, nunca envia comandos."""
    def __init__(self, arrival_radius=100., include_green=False):
        self.include_green = include_green
        self.arrival_radius = arrival_radius
        self.reset()

    def reset(self):
        self.target = None
        self.map_id = None
        self.respawn = None
        self.started = None
        self.last_progress = None
        self.best_distance = float("inf")
        self.last_distance = float("inf")
        self.baseline = None

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

    def run(self):
        last_status=None; attempted=None
        disconnected=None; next_retry=0; retries=0
        repair_retry=0; recovering=False
        self.emit("running",True)
        try:
            while not self.stop.is_set():
                snapshot=self.session.get_world_snapshot()
                now=self.clock()
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
                if phase in ("paused","recover","stalled"):
                    if phase=="stalled": self.emit("failed",None)
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
            self.emit("status","Coleta por dados pausada: "+str(exc))
        finally:
            self.stop.set()
            self.emit("running",False)


class SessionEarnings:
    """Conta somente eventos novos de uridium das boxes durante a coleta."""
    def __init__(self):
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
            amount = event.get("amount")
            if (self.primed and active and event.get("type")=="box-collected"
                    and event.get("field")=="uridium" and not event.get("petCollected")
                    and type(amount) in (int,float) and isfinite(amount) and amount>0):
                self.total += amount
        self.primed = True
        while len(self.order)>2000:
            self.seen.discard(self.order.pop(0))

    def hourly(self, seconds):
        return self.total*3600/seconds if seconds>=60 else None


class NpcTestWorker:
    """Uma luta por execução; Ctrl só é repetido após confirmação de estado."""
    def __init__(self,session,stop,emit,kind="mordon",destination="",min_hp=40,clock=None,orbit=False,radius=450,repair_portal=False):
        self.session=session; self.stop=stop; self.emit=emit; self.kind=kind
        self.destination=destination; self.min_hp=min_hp; self.clock=clock or time.monotonic
        self.orbit=orbit; self.radius=max(150,min(500,radius)); self.repair_portal=repair_portal; self.direction=1
        self.target=None; self.context=None; self.pending=None; self.next_move=0
        self.started=None; self.progress=None; self.best_distance=float("inf"); self.lowest=None
        self.damage=False; self.baseline_xp=None; self.last_phase=None
        self.report={"mode":"single_npc_test","kind":kind,"status":"Preparando","actions":[],
                     "damage_observed":False,"kill_confirmed":False,"stop_confirmed":False}

    def publish(self,status):
        self.report["status"]=status
        self.report["damage_observed"]=self.damage
        self.emit("npc_report",dict(self.report,actions=list(self.report["actions"])))
        if status!=self.last_phase:
            self.emit("status",status); self.last_phase=status

    def action(self,name,**options):
        payload=dict(self.context,id=self.target["id"],revision=self.target.get("respawnRevision"),
                     min_hp=self.min_hp,action=name,**options)
        result=self.session.request("npc_action",payload,allowed=lambda:not self.stop.is_set())
        if not isinstance(result,dict): return {"action":"cancelled"}
        self.report["actions"].append({"seconds":round(self.clock()-self.started,2),"action":name,"result":result.get("action")})
        self.report["actions"]=self.report["actions"][-40:]
        return result

    def cease_fire(self):
        if self.target is None or self.context is None: return
        try:
            payload=dict(self.context,id=self.target["id"],revision=self.target.get("respawnRevision"),
                         min_hp=self.min_hp,action="stop")
            before=self.session.get_world_snapshot().get("sequence")
            result=self.session.request("npc_action",payload,allowed=lambda:True)
            if result and result.get("action")=="stopped":
                self.report["stop_confirmed"]=True; return
            # Stop is an explicit right-click selection when visible, so it never starts fire.
            for _ in range(20):
                snap=self.session.get_world_snapshot()
                if (snap.get("fresh") and snap.get("map")==self.context["map"] and
                    snap.get("respawn_revision")==self.context["life"] and
                    snap.get("combat",{}).get("attacking") is False and
                    type(before) is int and type(snap.get("sequence")) is int and snap["sequence"]>before):
                    self.report["stop_confirmed"]=True; return
                time.sleep(.1)
        except Exception:
            pass

    def recover_at_portal(self):
        self.cease_fire()
        if not self.report["stop_confirmed"]:
            raise ValueError("Parada dos tiros não confirmada; recuperação cancelada.")
        started=self.clock(); next_move=0; gate=None; repair_sent=None
        while not self.stop.is_set():
            snap=self.session.get_world_snapshot(); now=self.clock()
            if (not snap.get("fresh") or snap.get("dead") or snap.get("map")!=self.context["map"]
                or snap.get("respawn_revision")!=self.context["life"]):
                raise ValueError("Recuperação interrompida: leitura, mapa ou vida mudou.")
            combat=snap.get("combat",{})
            if combat.get("attacking") or combat.get("secondaryVolley"):
                raise ValueError("Tiros ainda ativos; recuperação interrompida.")
            self.report["hp_percent"]=snap.get("hp_percent")
            self.report["repair_active"]=combat.get("repairActive",False)
            if now-started>180: raise ValueError("Recuperação excedeu 3 minutos; confira o jogo.")
            if repair_sent is not None and not combat.get("repairing") and now-repair_sent>5:
                raise ValueError("CPU de reparo não confirmou ativação; confira equipamento e jogo.")
            if now>=next_move:
                result=self.action("retreat",gate=gate,enable_repair=repair_sent is None)
                next_move=now+1.5
                if result.get("action")!="retreating":
                    raise ValueError("Retorno ao portal não aceito: "+result.get("action","?"))
                gate=result.get("gate"); self.report["recovery_gate"]=gate
                if result.get("repair")=="unavailable": raise ValueError("Equipe uma CPU/robô de reparo no jogo.")
                if result.get("repair") in ("sent","enabled") and repair_sent is None: repair_sent=now
                if result.get("distance",99999)<=80 and (snap.get("hp_percent") or 0)>=90:
                    self.publish("Recuperada no portal. Teste encerrado; ataque não será retomado.")
                    return
            self.publish("Indo ao portal; reparo aguarda as condições de combate do jogo.")
            if self.stop.wait(.2): break

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
                    if hp<80: raise ValueError("Recupere a vida para pelo menos 80% antes do teste.")
                    combat=snap.get("combat",{})
                    if combat.get("attacking"): raise ValueError("Pare o ataque atual antes do teste.")
                    if combat.get("selectedAmmo")!="lcb10": raise ValueError("Selecione LCB-10 no jogo antes do teste.")
                    candidates=[n for n in snap.get("npc_candidates",[]) if
                                (n.get("kind") or n.get("type"))==self.kind and
                                type(n.get("hp")) in (int,float) and n["hp"]>0 and
                                type(n.get("respawnRevision")) is int]
                    if not candidates: raise ValueError("Nenhum NPC desse tipo disponível no mapa.")
                    self.target=dict(min(candidates,key=lambda n:distance(snap["position"],(n["x"],n["y"]))))
                    self.context={"map":snap["map"],"life":snap.get("respawn_revision")}
                    self.baseline_xp=snap.get("account",{}).get("xp")
                    self.progress=now
                    self.report["target_id"]=self.target["id"]
                    self.report["map"]=snap["map"]
                if snap["map"]!=self.context["map"] or snap.get("respawn_revision")!=self.context["life"]:
                    raise ValueError("Mapa ou vida da nave mudou durante o teste.")
                current=next((n for n in snap.get("npc_candidates",[]) if str(n["id"])==str(self.target["id"])
                             and n.get("respawnRevision")==self.target.get("respawnRevision")),None)
                xp=snap.get("account",{}).get("xp")
                if current is None or current.get("hp",0)<=0:
                    confirmed=(self.damage and type(xp) in (int,float) and type(self.baseline_xp) in (int,float)
                               and xp>self.baseline_xp)
                    self.report["kill_confirmed"]=confirmed
                    self.publish("NPC derrotado e recompensa observada. Teste concluído." if confirmed else
                                 "Alvo deixou a leitura sem confirmação de recompensa. Teste encerrado.")
                    break
                self.target=dict(current)
                health=current["hp"]+(current.get("shield") or 0)
                if self.lowest is not None and health<self.lowest:
                    self.damage=True; self.progress=now
                self.lowest=health if self.lowest is None else min(self.lowest,health)
                self.report["target_hp"]=current["hp"]; self.report["target_shield"]=current.get("shield")
                d=distance(snap["position"],(current["x"],current["y"]))
                if d<self.best_distance-10: self.best_distance=d; self.progress=now
                if now-self.started>180: raise ValueError("Teste excedeu 3 minutos.")
                if now-self.progress>15: raise ValueError("Sem aproximação ou dano por 15 segundos.")
                combat=snap.get("combat",{})
                selected=str(combat.get("target_id"))==str(current["id"])
                if self.pending:
                    name,sent=self.pending
                    confirmed=(name=="select" and selected) or (name=="attack" and combat.get("attacking") is True)
                    if confirmed: self.pending=None
                    elif now-sent>5: raise ValueError("Comando "+name+" não foi confirmado pelo jogo.")
                    else:
                        if self.stop.wait(.2): break
                        continue
                if d>520:
                    if now>=self.next_move:
                        result=self.action("approach"); self.next_move=now+1.5
                        if result.get("action") not in ("move_sent","in_range"): raise ValueError("Aproximação não aceita: "+result.get("action","?"))
                    self.publish("Aproximando do NPC selecionado.")
                elif not selected:
                    result=self.action("select")
                    if result.get("action")=="not_visible":
                        if now>=self.next_move:
                            result=self.action("approach",close_approach=True); self.next_move=now+1.5
                            if result.get("action") not in ("move_sent","in_range"):
                                raise ValueError("Aproximação não aceita: "+result.get("action","?"))
                        self.publish("Aproximando mais para selecionar o mesmo NPC na tela.")
                    elif result.get("action")=="select_sent":
                        self.pending=("select",now)
                        self.publish("Aguardando confirmação do alvo NPC.")
                    else:
                        raise ValueError("NPC não selecionado: "+result.get("action","?"))
                elif combat.get("attacking") is not True:
                    result=self.action("attack")
                    if result.get("action") not in ("attack_sent","attacking"): raise ValueError("Ataque não aceito: "+result.get("action","?"))
                    self.pending=("attack",now)
                    self.publish("Aguardando confirmação do ataque.")
                else:
                    if self.orbit and now>=self.next_move:
                        result=self.action("orbit",radius=self.radius,direction=self.direction); self.next_move=now+.8
                        if result.get("action")!="orbiting":
                            raise ValueError("Movimento circular não aceito: "+result.get("action","?"))
                        self.direction=result.get("direction",self.direction)
                    self.publish(("Circulando e atacando " if self.orbit else "Atacando ")+self.kind+" com LCB-10. F9 interrompe o teste.")
                if self.stop.wait(.2): break
        except Exception as exc:
            self.publish(str(exc))
        finally:
            if self.stop.is_set(): self.publish("Teste cancelado.")
            self.cease_fire()
            self.stop.set()
            if self.target is not None and not self.report["stop_confirmed"]:
                self.report["status"]+=" Não foi possível confirmar a parada; confira o jogo."
                self.emit("status",self.report["status"])
            self.emit("npc_report",dict(self.report))
            self.emit("running",False)
