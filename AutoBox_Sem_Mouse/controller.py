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


class DataCollector:
    """Executa um alvo por vez pela interface do cliente; nao monta pacotes HTTP."""
    def __init__(self, session, stop_event, emit, clock=None, settings=None):
        self.settings=settings or {}
        self.deaths=self.settings.get("death_state",{"ids":set(),"count":0})
        self.session=session; self.stop=stop_event; self.emit=emit
        self.clock=clock or time.monotonic
        self.planner=DataFarmPlanner(arrival_radius=180, include_green=self.settings.get("green",False))

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
