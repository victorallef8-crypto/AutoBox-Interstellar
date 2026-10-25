"""Coleta exclusiva pela pagina. Um unico alvo por vez, com diagnostico visual."""
import time
from controller import CollectionState, track, center, detection_area, visible_box
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
        self.search_started = None
        self.patrol_step = 0
        self.last_escape = -100
        self.radiation_started = None
        self.failed_targets = 0
        self.search_area = detection_area(config, session.viewport)
        self.empty_frames = 0

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
        crop(frame, self.config["map"])
        return frame

    def boxes(self, frame, area=None):
        area = area or self.search_area
        matches = locate_boxes(crop(frame, area), self.sample,
                               threshold=self.config.get("threshold", .9))
        return [(x + area["left"], y + area["top"], score) for x, y, score in matches
                if visible_box((x + area["left"], y + area["top"]), self.config)]

    def aim(self, expected, frame=None):
        frame = self.capture() if frame is None else frame
        map_area = self.search_area
        left = max(map_area["left"], round(expected[0]) - 110)
        top = max(map_area["top"], round(expected[1]) - 110)
        right = min(map_area["left"] + map_area["width"], round(expected[0]) + 111)
        bottom = min(map_area["top"] + map_area["height"], round(expected[1]) + 111)
        area = {"left": left, "top": top, "width": right-left, "height": bottom-top}
        point = track(self.boxes(frame, area), expected, radius=80)
        if point is None or not self.state.allowed(point) or not self.ready():
            return False
        if self.baseline is None and self.config.get("notice"):
            self.baseline = crop(frame, self.config["notice"]).copy()
        if not self.session.request("click", point, allowed=self.ready):
            return False
        self.state.clicked(point, time.monotonic())
        self.emit("preview", (frame.copy(), point, getattr(self.session, "last_click", None)))
        self.status("Aproximando do mesmo box — clique %s/6" % self.state.target.clicks)
        return True


    def return_to_safe_zone(self, now):
        safe = self.config.get("minimap")
        if not safe:
            self.status("Sem zona segura marcada. Coleta pausada; confira a nave.")
            return False
        # Valida o retangulo antes de usar coordenadas de navegacao.
        crop(self.capture(), safe)
        if self.ready() and self.session.request("click", center(safe), allowed=self.ready):
            self.last_escape = now
            return True
        return False

    def run(self):
        self.emit("running", True)
        try:
            while self.ready():
                frame = self.capture()
                now = time.monotonic()
                if find_death_panel(frame) is not None:
                    self.status("Tela de morte detectada. Coleta pausada.")
                    return
                if radiation_visible(frame):
                    if self.radiation_started is None:
                        self.radiation_started = now
                    self.state.finish(now, failed=True)
                    self.baseline = None
                    if now - self.last_escape >= 2:
                        if not self.return_to_safe_zone(now):
                            return
                        self.status("Radiacao: retornando ao centro da zona segura marcada.")
                    if now - self.radiation_started >= 12:
                        self.status("Radiacao persiste apos retorno. Pausado; confira a zona segura.")
                        return
                    self.stop.wait(.2)
                    continue
                self.radiation_started = None
                if self.state.target is not None:
                    # Rastreamento local rapido; varredura completa so entre coletas.
                    expected = self.state.predicted(now)
                    bounds = self.search_area
                    left=max(bounds["left"],round(expected[0])-140)
                    top=max(bounds["top"],round(expected[1])-140)
                    right=min(bounds["left"]+bounds["width"],round(expected[0])+141)
                    bottom=min(bounds["top"]+bounds["height"],round(expected[1])+141)
                    matches = self.boxes(frame, {"left":left,"top":top,"width":right-left,"height":bottom-top}) if right>left and bottom>top else []
                else:
                    matches = self.boxes(frame)
                if matches:
                    self.search_started = None
                    self.empty_frames = 0
                elif self.search_started is None:
                    self.search_started = now
                    self.empty_frames = 0
                elif now - self.search_started >= 24:
                    returned = self.return_to_safe_zone(now)
                    self.status("Nenhuma box reconhecida por 24 s. " +
                                ("Retorno enviado a zona marcada. " if returned else "") +
                                "Pausado: use Testar deteccao para conferir a imagem.")
                    return
                if not matches:
                    self.empty_frames += 1
                if self.state.target is None:
                    point = self.state.choose(matches, now)
                    if point is not None:
                        self.state.acquire(point, now)
                        self.baseline = None
                        self.notice_streak = 0
                        # A varredura completa pode envelhecer o quadro; recaptura antes do primeiro clique.
                        if self.aim(point):
                            self.emit("attempt", None)
                        else:
                            self.state.finish(now, failed=True)
                        self.stop.wait(.12)
                        continue
                    # Candidatos apenas temporariamente filtrados nao causam outra ordem de voo.
                    safe = self.config.get("minimap")
                    if not matches and self.empty_frames >= 3 and safe and now - self.last_patrol >= 6:
                        # Alterna quatro regioes internas; nao insiste num destino unico.
                        fx, fy = ((.3,.3),(.7,.7),(.7,.3),(.3,.7))[self.patrol_step % 4]
                        point = (safe["left"] + safe["width"]*fx, safe["top"] + safe["height"]*fy)
                        if self.ready() and self.session.request("click", point, allowed=self.ready):
                            self.last_patrol = now
                            self.patrol_step += 1
                            self.status("0 boxes reconhecidas. Busca %s/4 na zona do minimapa." % self.patrol_step)
                    else:
                        self.status("Reverificando o box mais proximo..." if matches else ("Procurando boxes..." if safe else "Procurando boxes — sem ronda configurada."))
                    self.stop.wait(.2)
                    continue
                reward = False
                if self.baseline is not None:
                    current = crop(frame, self.config["notice"])
                    self.notice_streak = self.notice_streak + 1 if new_reward_message(self.baseline, current) else 0
                    reward = self.notice_streak >= 2
                point = track(matches, self.state.predicted(now), radius=80)
                action = self.state.observe(point, now, reward)
                if action == "aim":
                    self.aim(point, frame)
                elif action in ("confirmed", "departed", "failed"):
                    self.emit(action, None)
                    self.status({"confirmed": "Recompensa confirmada. Proximo box.",
                                 "departed": "Alvo desapareceu junto da nave. Selecionando o mais proximo.",
                                 "failed": "Tentativa sem progresso. Buscando outro alvo."}[action])
                    self.state.finish(now, failed=action == "failed")
                    self.failed_targets = self.failed_targets + 1 if action == "failed" else 0
                    if self.failed_targets >= 3:
                        self.return_to_safe_zone(now)
                        self.status("Tres alvos sem progresso. Pausado para conferir a deteccao.")
                        return
                    self.baseline = None
                self.stop.wait(.18)
        except Exception as exc:
            self.status("Pausado: " + str(exc))
        finally:
            self.stop.set()
            self.emit("running", False)
