"""Coleta exclusiva pela pagina. Um unico alvo por vez, com diagnostico visual."""
import random
import time
from controller import CollectionState, inside, track
from vision import locate_boxes, new_reward_message, radiation_visible, find_death_panel

def crop(frame, area):
    if area is None:
        return None
    x, y, w, h = (int(area[key]) for key in ("left", "top", "width", "height"))
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > frame.shape[1] or y + h > frame.shape[0]:
        raise ValueError("Uma area calibrada ficou fora da imagem. Calibre novamente.")
    return frame[y:y+h, x:x+w]

class Collector:
    def __init__(self, session, config, sample, stop, emit, decode):
        self.session, self.config, self.sample = session, dict(config), sample
        self.stop, self.emit, self.decode = stop, emit, decode
        self.state = CollectionState(config["ship"])
        self.baseline = None
        self.notice_streak = 0
        self.last_patrol = -100
        self.last_status = None

    def ready(self):
        return not self.stop.is_set() and self.session.ready.is_set()

    def status(self, text):
        if text != self.last_status:
            self.emit("status", text)
            self.last_status = text

    def capture(self):
        frame = self.decode(self.session.request("screenshot"))
        if frame is None:
            raise RuntimeError("Imagem da sessao indisponivel.")
        viewport = self.session.viewport
        if frame.shape[:2] != (viewport["height"], viewport["width"]):
            raise RuntimeError("Tamanho da pagina mudou. Reabra a sessao e calibre novamente.")
        return frame

    def boxes(self, frame, area=None):
        area = area or self.config["map"]
        matches = locate_boxes(crop(frame, area), self.sample,
                               threshold=self.config.get("threshold", .9))
        return [(x + area["left"], y + area["top"], score) for x, y, score in matches
                if self.state.allowed((x + area["left"], y + area["top"]))]

    def aim(self, expected):
        frame = self.capture()
        map_area = self.config["map"]
        left = max(map_area["left"], round(expected[0]) - 70)
        top = max(map_area["top"], round(expected[1]) - 70)
        right = min(map_area["left"] + map_area["width"], round(expected[0]) + 71)
        bottom = min(map_area["top"] + map_area["height"], round(expected[1]) + 71)
        area = {"left": left, "top": top, "width": right-left, "height": bottom-top}
        point = track(self.boxes(frame, area), expected, radius=45)
        if point is None or not self.state.allowed(point) or not self.ready():
            return False
        if self.baseline is None and self.config.get("notice"):
            self.baseline = crop(frame, self.config["notice"]).copy()
        if not self.session.request("click", point, allowed=self.ready):
            return False
        self.state.clicked(point, time.monotonic())
        self.emit("preview", (frame.copy(), point))
        self.status("Aproximando do mesmo box — clique %s/6" % self.state.target.clicks)
        return True

    def run(self):
        self.emit("running", True)
        try:
            while self.ready():
                frame = self.capture()
                if radiation_visible(frame) or find_death_panel(frame) is not None:
                    self.status("Aviso de perigo ou morte. Coleta pausada para verificacao.")
                    return
                now = time.monotonic()
                matches = self.boxes(frame)
                if self.state.target is None:
                    point = self.state.choose(matches, now)
                    if point is not None:
                        self.state.acquire(point, now)
                        self.baseline = None
                        self.notice_streak = 0
                        if self.aim(point):
                            self.emit("attempt", None)
                        else:
                            self.state.finish(now, failed=True)
                        self.stop.wait(.12)
                        continue
                    # Candidatos apenas temporariamente filtrados nao causam outra ordem de voo.
                    safe = self.config.get("minimap")
                    if not matches and safe and now - self.last_patrol >= 6:
                        mx, my = min(12, safe["width"]/4), min(10, safe["height"]/4)
                        point = (random.uniform(safe["left"]+mx, safe["left"]+safe["width"]-mx),
                                 random.uniform(safe["top"]+my, safe["top"]+safe["height"]-my))
                        if self.ready() and self.session.request("click", point, allowed=self.ready):
                            self.last_patrol = now
                            self.status("Procurando boxes na zona marcada do minimapa...")
                    else:
                        self.status("Procurando boxes..." if safe else "Procurando boxes — sem ronda configurada.")
                    self.stop.wait(.2)
                    continue
                reward = False
                if self.baseline is not None:
                    current = crop(frame, self.config["notice"])
                    self.notice_streak = self.notice_streak + 1 if new_reward_message(self.baseline, current) else 0
                    reward = self.notice_streak >= 2
                point = track(matches, self.state.target.point)
                action = self.state.observe(point, now, reward)
                if action == "aim":
                    self.aim(point)
                elif action in ("confirmed", "departed", "failed"):
                    self.emit(action, None)
                    self.status({"confirmed": "Recompensa confirmada. Proximo box.",
                                 "departed": "Alvo saiu de vista junto da nave. Buscando o proximo.",
                                 "failed": "Tentativa sem progresso. Buscando outro alvo."}[action])
                    self.state.finish(now, failed=action == "failed")
                    self.baseline = None
                self.stop.wait(.18)
        except Exception as exc:
            self.status("Pausado: " + str(exc))
        finally:
            self.stop.set()
            self.emit("running", False)
