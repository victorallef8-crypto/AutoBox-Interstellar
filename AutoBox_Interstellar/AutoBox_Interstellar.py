"""AutoBox Interstellar Verse - automacao visual local, experimental.

Funciona exclusivamente por captura de tela e cliques do mouse.
Nao inspeciona trafego, memoria, contas ou arquivos do jogo.
"""

from __future__ import annotations

import ctypes
import json
import os
import queue
import random
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
import mss
import numpy as np
import pyautogui
from PIL import Image, ImageTk
from pynput import keyboard
import updater


APP_NAME = "AutoBox Interstellar Verse"
APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "AutoBoxInterstellar"
SETTINGS_PATH = APP_DIR / "config.json"
TEMPLATE_PATH = APP_DIR / "box_modelo.png"
MAX_COLLECTION_TIMEOUTS = 3

REPAIR_COSTS = {"base": 0, "portal": 250, "same_place": 500}
REPAIR_LABELS = {"base": "base", "portal": "portal", "same_place": "mesmo lugar"}

# Coordenadas de tela do Windows sao pixels fisicos, inclusive com zoom do Opera.
if os.name == "nt":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

pyautogui.FAILSAFE = True  # Canto superior esquerdo aborta os cliques.
pyautogui.PAUSE = 0.05


def active_window_title() -> str:
    if os.name != "nt":
        return ""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    buffer = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def locate_boxes(frame_bgr: np.ndarray, sample_bgr: np.ndarray,
                 threshold: float = 0.90) -> list[tuple[int, int, float]]:
    """Retorna candidatos (x,y,confianca) em pixels relativos a frame_bgr.

    Busca em algumas escalas para tolerar pequenas variacoes de renderizacao.
    Nao faz cliques nem depende da interface grafica.
    """
    if frame_bgr is None or sample_bgr is None:
        return []
    frame_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    sample_gray = cv2.cvtColor(sample_bgr, cv2.COLOR_BGR2GRAY)
    height, width = frame_gray.shape
    proposals: list[tuple[int, int, float]] = []

    for scale in (0.85, 1.0, 1.15):
        sw = max(9, round(sample_gray.shape[1] * scale))
        sh = max(9, round(sample_gray.shape[0] * scale))
        if sw >= width or sh >= height:
            continue
        resized = cv2.resize(sample_gray, (sw, sh), interpolation=cv2.INTER_LINEAR)
        if float(resized.std()) < 8.0:
            continue
        scores = cv2.matchTemplate(frame_gray, resized, cv2.TM_CCOEFF_NORMED)
        # Picos locais para evitar centenas de candidatos por um unico objeto.
        neighborhood = max(11, min(sw, sh) // 2)
        maxima = cv2.dilate(scores, np.ones((neighborhood, neighborhood), np.uint8))
        ys, xs = np.where((scores >= threshold) & (scores >= maxima - 1e-6))
        for y, x in zip(ys.tolist(), xs.tolist()):
            cx, cy = x + sw // 2, y + sh // 2
            # Exige que haja um centro luminoso, nao so a mesma textura de fundo.
            patch = frame_bgr[max(0, cy - 4): min(height, cy + 5),
                              max(0, cx - 4): min(width, cx + 5)]
            if patch.size and int(np.max(np.min(patch, axis=2))) >= 175:
                proposals.append((cx, cy, float(scores[y, x])))

    proposals.sort(key=lambda p: p[2], reverse=True)
    output: list[tuple[int, int, float]] = []
    for x, y, confidence in proposals:
        if all((x - ox) ** 2 + (y - oy) ** 2 >= 24 ** 2 for ox, oy, _ in output):
            output.append((x, y, confidence))
        if len(output) >= 40:
            break
    return output


def radiation_visible(frame_bgr: np.ndarray) -> bool:
    """Aviso vermelho da faixa superior, sem OCR ou templates externos."""
    height, width = frame_bgr.shape[:2]
    top = frame_bgr[0:max(1, int(height * .18)),
                    int(width * .32):int(width * .68)]
    if top.size == 0:
        return False
    b, g, r = cv2.split(top)
    red = (r > 90) & (r.astype(np.int16) > 2 * g.astype(np.int16)) & (
        r.astype(np.int16) > 1.5 * b.astype(np.int16))
    return int(np.count_nonzero(red)) > 950


def find_death_panel(frame_bgr: np.ndarray) -> tuple[int, int, int, int] | None:
    """Procura a caixa de morte ao centro: texto vermelho + painel retangular."""
    height, width = frame_bgr.shape[:2]
    crop_x, crop_y = int(width * .23), int(height * .24)
    crop = frame_bgr[crop_y:int(height * .81), crop_x:int(width * .77)]
    if crop.size == 0:
        return None
    b, g, r = cv2.split(crop)
    red_text = (r > 145) & (r.astype(np.int16) > 2 * g.astype(np.int16)) & (
        r.astype(np.int16) > 1.7 * b.astype(np.int16))
    # Nao confundir com a faixa RADIATION ZONE, que fica la no topo.
    ys, xs = np.nonzero(red_text)
    if len(xs) < 80:
        return None
    red_in_mid = ((xs > crop.shape[1] * .3) & (xs < crop.shape[1] * .7) &
                  (ys > crop.shape[0] * .14) & (ys < crop.shape[0] * .43))
    if int(red_in_mid.sum()) < 65:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    mask = ((gray >= 12) & (gray < 140)).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    options = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        abs_x, abs_y = x + crop_x, y + crop_y
        if not (.18 * width <= w <= .42 * width and
                .23 * height <= h <= .53 * height):
            continue
        if abs((abs_x + w / 2) - width / 2) > width * .15:
            continue
        options.append((abs_x, abs_y, w, h))
    return max(options, key=lambda item: item[2] * item[3]) if options else None


def reward_notice_visible(frame_bgr: np.ndarray, target_x: int) -> bool:
    """Detecta pequenas letras claras no alto, proximas da nave/ultima box.

    O jogo desenha mensagens como 'You received 60 Uridium' nessa regiao.
    Um detector visual simples evita exigir OCR ou acesso interno ao jogo.
    """
    height, width = frame_bgr.shape[:2]
    left = max(0, target_x - 190)
    right = min(width, target_x + 190)
    # Inclui browser normal e fullscreen. Mensagem chega poucos px abaixo
    # do topo da area espacial; ignora HUD lateral via proximidade ao alvo.
    roi = frame_bgr[20:min(180, height), left:right]
    if roi.size == 0:
        return False
    b, g, r = cv2.split(roi)
    white = ((r > 165) & (g > 165) & (b > 165)).astype(np.uint8) * 255
    closed = cv2.morphologyEx(
        white, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1)))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= 65 and 4 <= h <= 15 and 0 <= y <= 150:
            return True
    return False


def new_reward_message(before_bgr: np.ndarray, after_bgr: np.ndarray) -> bool:
    """Detecta uma linha clara *nova* na area de notificacoes marcada.

    Compara com a imagem feita ANTES do clique. Mensagens antigas que ainda
    estejam na tela nao podem disparar uma segunda coleta. O jogador deve
    selecionar apenas as linhas 'You received', sem barras nem animacoes.
    Nao exige OCR nem leitura de memoria do jogo.
    """
    if (before_bgr is None or after_bgr is None or
            before_bgr.shape != after_bgr.shape or before_bgr.ndim != 3):
        return False

    def light_text(image):
        # O texto do print e cinza-claro/branco em fundo preto; ignora
        # mensagens coloridas e pequenas estrelas isoladas.
        low = np.min(image, axis=2)
        high = np.max(image, axis=2)
        return (low >= 125) & ((high.astype(np.int16) - low) <= 42)

    added = light_text(after_bgr) & ~light_text(before_bgr)
    if int(np.count_nonzero(added)) < 42:
        return False
    rows = np.flatnonzero(np.count_nonzero(added, axis=1) >= 8)
    columns = np.flatnonzero(np.any(added, axis=0))
    # Texto de uma notificacao ocupa varias linhas e dezenas de pixels
    # horizontais, ao contrario de estrelas/particulas individuais.
    return (len(rows) >= 3 and len(columns) >= 28 and
            int(columns[-1] - columns[0]) >= 48)


def repair_click_points(panel: tuple[int, int, int, int],
                        destination: str) -> tuple[tuple[int, int], tuple[int, int]]:
    """Posicoes das tres opcoes e do botao de reparar na tela de morte.

    Base/portal/mesmo lugar sao, respectivamente, os tres cartoes da esquerda
    para a direita na tela enviada pelo usuario. As posicoes sao relativas ao
    painel para tolerar resolucoes diferentes, desde que o layout nao mude.
    """
    if destination not in REPAIR_COSTS:
        raise ValueError("Destino de renascimento desconhecido")
    px, py, width, height = panel
    option_x = {"base": .215, "portal": .50, "same_place": .785}[destination]
    return ((px + round(width * option_x), py + round(height * .47)),
            (px + round(width * .50), py + round(height * .895)))


class AutoBoxApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(APP_NAME + " - beta 3.4")
        root.geometry("600x885")
        root.minsize(545, 735)

        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.cfg = self._read_config()
        self.region: dict | None = self.cfg.get("region")
        self.safe_region: dict | None = self.cfg.get("safe_region")
        self.notice_region: dict | None = self.cfg.get("notice_region")
        self.status = tk.StringVar(value="Aguardando configuracao")
        self.region_status = tk.StringVar(value="Nao selecionada")
        self.safe_status = tk.StringVar(value="Nao selecionada")
        self.notice_status = tk.StringVar(value="Nao selecionada")
        self.sample_status = tk.StringVar(value="Nao aprendida")
        self.count = tk.IntVar(value=0)
        self.wait_var = tk.StringVar(value=str(self.cfg.get("wait", 5.0)))
        self.patrol_var = tk.StringVar(value=str(self.cfg.get("patrol_wait", 7.0)))
        self.threshold_var = tk.StringVar(value=str(self.cfg.get("threshold", 0.90)))
        self.title_var = tk.StringVar(value=self.cfg.get("title", "Interstellar Verse"))
        self.auto_revive_var = tk.BooleanVar(value=bool(self.cfg.get("auto_revive", False)))
        previous_destination = "portal" if self.cfg.get("auto_revive", False) else "base"
        self.revive_target_var = tk.StringVar(
            value=self.cfg.get("revive_target", previous_destination))
        self.revive_limit_var = tk.StringVar(value=str(self.cfg.get("revives_per_hour", 2)))

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.state_lock = threading.Lock()
        self.running = False
        self.stopped = False
        self.exit_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.keyboard_listener = None
        self.revive_attempts: list[float] = []

        self._draw()
        self._refresh_labels()
        self._bind_hotkeys()
        self.root.after(100, self._drain_events)
        self.root.after(3500, lambda: self.check_updates(silent=True))
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _read_config(self):
        if SETTINGS_PATH.exists():
            try:
                return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return {}

    def _save_config(self):
        self.cfg.update({
            "region": self.region,
            "safe_region": self.safe_region,
            "notice_region": self.notice_region,
            "wait": self.wait_seconds,
            "patrol_wait": self.patrol_seconds,
            "threshold": self.threshold,
            "title": self.title_required,
            "auto_revive": self.auto_revive,
            "revive_target": self.revive_target,
            "revives_per_hour": self.revives_per_hour,
        })
        SETTINGS_PATH.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")

    def _draw(self):
        frame = ttk.Frame(self.root, padding=17)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="AutoBox | Interstellar Verse",
                  font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Beta 3.4 • Posicao do box conferida antes do clique",
                  foreground="#526477").pack(anchor="w", pady=(1, 13))

        capture_box = ttk.LabelFrame(frame, text="1. Preparar deteccao", padding=10)
        capture_box.pack(fill="x")
        ttk.Button(capture_box, text="Selecionar area do mapa",
                   command=lambda: self._capture_selection("region")).grid(row=0, column=0, sticky="ew")
        ttk.Button(capture_box, text="Aprender uma box",
                   command=lambda: self._capture_selection("sample")).grid(row=1, column=0, sticky="ew", pady=(7, 0))
        ttk.Button(capture_box, text="Marcar zona segura NO MINIMAPA",
                   command=lambda: self._capture_selection("safe")).grid(row=2, column=0, sticky="ew", pady=(7, 0))
        ttk.Button(capture_box, text="Marcar area das mensagens YOU RECEIVED",
                   command=lambda: self._capture_selection("notice")).grid(row=3, column=0, sticky="ew", pady=(7, 0))
        ttk.Label(capture_box, textvariable=self.region_status).grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Label(capture_box, textvariable=self.sample_status).grid(row=1, column=1, sticky="w", padx=(12, 0))
        ttk.Label(capture_box, textvariable=self.safe_status).grid(row=2, column=1, sticky="w", padx=(12, 0))
        ttk.Label(capture_box, textvariable=self.notice_status).grid(row=3, column=1, sticky="w", padx=(12, 0))
        capture_box.columnconfigure(0, weight=1)

        control = ttk.LabelFrame(frame, text="2. Controles", padding=10)
        control.pack(fill="x", pady=(12, 0))
        buttons = ttk.Frame(control)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="▶ Iniciar (F8)", command=self.start).pack(side="left", fill="x", expand=True)
        ttk.Button(buttons, text="Ⅱ Pausar (F9)", command=self.pause).pack(side="left", fill="x", expand=True, padx=7)
        ttk.Button(buttons, text="■ Parar (F10)", command=self.stop).pack(side="left", fill="x", expand=True)
        ttk.Label(control, textvariable=self.status, wraplength=470).pack(anchor="w", pady=(8, 0))
        ttk.Label(control, text="Boxes selecionadas nesta sessao:").pack(side="left", pady=(6, 0))
        ttk.Label(control, textvariable=self.count, font=("Segoe UI", 11, "bold")).pack(
            side="left", padx=(6, 0), pady=(6, 0))

        settings = ttk.LabelFrame(frame, text="3. Ajustes", padding=10)
        settings.pack(fill="x", pady=(12, 0))
        for row, (label, var) in enumerate((
                ("Espera depois da box (seg)", self.wait_var),
                ("Espera em cada ronda (seg)", self.patrol_var),
                ("Confianca da imagem (0,60 a 0,95)", self.threshold_var),
                ("Titulo do jogo na janela", self.title_var))):
            ttk.Label(settings, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(settings, textvariable=var, width=21).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        settings.columnconfigure(1, weight=1)
        ttk.Checkbutton(settings, text="Renascer automaticamente quando morrer",
                        variable=self.auto_revive_var).grid(row=4, column=0, columnspan=2,
                                                            sticky="w", pady=(7, 3))
        destinations = ttk.Frame(settings)
        destinations.grid(row=5, column=0, columnspan=2, sticky="w", pady=3)
        for option, label in (("base", "Base (gratis)"),
                              ("portal", "Portal (250 U)"),
                              ("same_place", "Mesmo lugar (500 U)")):
            ttk.Radiobutton(destinations, text=label, value=option,
                            variable=self.revive_target_var).pack(side="left", padx=(0, 12))
        ttk.Label(settings, text="Maximo de renascimentos por hora (1 a 3)").grid(
            row=6, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.revive_limit_var, width=21).grid(
            row=6, column=1, sticky="ew", padx=(8, 0), pady=3)
        ttk.Button(settings, text="Salvar ajustes", command=self.apply_settings).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        ttk.Button(frame, text="↻ Verificar atualizacoes (GitHub)",
                   command=self.check_updates).pack(fill="x", pady=(12, 0))

        note = (
            "Use F8 e volte ao jogo. O programa so clica se a janela ativa tiver "
            "o titulo indicado. F9 pausa; F10 para. Mover o mouse ao canto "
            "superior esquerdo tambem interrompe o automouse.\n"
            "Sem zona segura marcada, o bot NAO faz ronda. Renascer no portal "
            "custa 250 U; no mesmo lugar, 500 U. Desligado por padrao.\n"
            "O jogo pode proibir automacao. Nao ha garantia de coleta, de "
            "funcionamento indefinido ou de ausencia de punicao na conta."
        )
        ttk.Label(frame, text=note, foreground="#59677c", wraplength=485,
                  justify="left").pack(anchor="w", pady=(12, 0))

        self.wait_seconds = 5.0
        self.patrol_seconds = 7.0
        self.threshold = 0.90
        self.title_required = "interstellar verse"
        self.auto_revive = False
        self.revive_target = "base"
        self.revives_per_hour = 2
        self.apply_settings(silent=True)

    def _refresh_labels(self):
        if self.region:
            self.region_status.set(f"{self.region['width']} x {self.region['height']} px")
        else:
            self.region_status.set("Nao selecionada")
        self.sample_status.set("Box aprendida ✓" if TEMPLATE_PATH.exists() else "Nao aprendida")
        self.safe_status.set("Area segura marcada ✓" if self.safe_region else "Nao selecionada")
        self.notice_status.set("Mensagens marcadas ✓" if self.notice_region else "Nao selecionada")

    def apply_settings(self, silent=False):
        try:
            wait = float(self.wait_var.get().replace(",", "."))
            patrol = float(self.patrol_var.get().replace(",", "."))
            threshold = float(self.threshold_var.get().replace(",", "."))
            revive_limit = int(self.revive_limit_var.get())
            revive_target = self.revive_target_var.get()
            title = self.title_var.get().strip()
            if not (2.0 <= wait <= 30.0 and 3.0 <= patrol <= 30.0):
                raise ValueError("As esperas precisam estar nos intervalos 2–30 e 3–30 segundos.")
            if not 0.60 <= threshold <= 0.95:
                raise ValueError("A confianca precisa estar entre 0,60 e 0,95.")
            if len(title) < 5:
                raise ValueError("Informe pelo menos 5 letras do titulo da janela do jogo.")
            if not 1 <= revive_limit <= 3:
                raise ValueError("O limite de renascimentos precisa ser de 1 a 3 por hora.")
            if revive_target not in REPAIR_COSTS:
                raise ValueError("Escolha Base, Portal ou Mesmo lugar.")
            spend = REPAIR_COSTS[revive_target]
            changed_paid_choice = (not self.auto_revive or
                                   self.revive_target != revive_target or
                                   self.revives_per_hour != revive_limit)
            if not silent and self.auto_revive_var.get() and spend and changed_paid_choice:
                sure = messagebox.askyesno(
                    "Confirmar gasto automatico de Uridium",
                    f"Renascer no {REPAIR_LABELS[revive_target]} custa {spend} Uridium "
                    "a cada morte.\n\n"
                    f"Com limite de {revive_limit} tentativas por hora, "
                    f"pode gastar ate {spend * revive_limit} Uridium por hora.\n\n"
                    "Voce conferiu essa opcao dentro do jogo e quer ativar?")
                if not sure:
                    self.auto_revive_var.set(False)
                    self.auto_revive = False
                    self._save_config()
                    return False
            self.wait_seconds = wait
            self.patrol_seconds = patrol
            self.threshold = threshold
            self.title_required = title.casefold()
            self.auto_revive = bool(self.auto_revive_var.get())
            self.revive_target = revive_target
            self.revives_per_hour = revive_limit
            self._save_config()
            if not silent:
                self.status.set("Ajustes salvos")
            return True
        except (ValueError, OSError) as exc:
            if not silent:
                messagebox.showerror("Ajustes invalidos", str(exc))
            return False

    def _bind_hotkeys(self):
        def on_press(key):
            if key == keyboard.Key.f8:
                self.events.put(("command", "start"))
            elif key == keyboard.Key.f9:
                self.events.put(("command", "pause"))
            elif key == keyboard.Key.f10:
                self.events.put(("command", "stop"))
        self.keyboard_listener = keyboard.Listener(on_press=on_press)
        self.keyboard_listener.daemon = True
        self.keyboard_listener.start()

    def _capture_selection(self, mode: str):
        if self.running:
            messagebox.showinfo("Pausar primeiro", "Aperte F9 antes de selecionar a area ou box.")
            return
        self.root.iconify()
        self.root.after(550, lambda: self._show_capture(mode))

    def _show_capture(self, mode: str):
        try:
            with mss.mss() as sct:
                # O monitor principal e o usado no exemplo. Para outro monitor,
                # configure-o como principal no Windows antes da calibracao.
                mon = sct.monitors[1]
                shot = sct.grab(mon)
            image = Image.frombytes("RGB", shot.size, shot.rgb)
            left, top = int(mon["left"]), int(mon["top"])
            width, height = image.size
            overlay = tk.Toplevel(self.root)
            overlay.overrideredirect(True)
            overlay.geometry(f"{width}x{height}{left:+d}{top:+d}")
            overlay.attributes("-topmost", True)
            overlay.focus_force()
            canvas = tk.Canvas(overlay, width=width, height=height, highlightthickness=0,
                               cursor="crosshair")
            canvas.pack(fill="both", expand=True)
            photo = ImageTk.PhotoImage(image)
            overlay._screen_photo = photo
            canvas.create_image(0, 0, anchor="nw", image=photo)
            if mode == "region":
                hint = "ARRASTE um retangulo apenas na area espacial do mapa"
            elif mode == "safe":
                hint = "ARRASTE so no CENTRO SEGURO do minimapa (sem bordas)"
            elif mode == "notice":
                hint = "ARRASTE so a area do texto YOU RECEIVED (sem HUD ou nave)"
            else:
                hint = "CLIQUE BEM NO CENTRO de uma box luminosa"
            canvas.create_rectangle(10, 10, min(width - 10, 680), 49,
                                    fill="#162e42", outline="#24c9ed", width=2)
            canvas.create_text(23, 29, text=hint + "  |  ESC cancela",
                               anchor="w", fill="white", font=("Segoe UI", 13, "bold"))
            start = [None]
            box = [None]

            def finish():
                overlay.destroy()
                self.root.deiconify()
                self.root.lift()
                self._refresh_labels()

            def down(event):
                start[0] = (event.x, event.y)

            def move(event):
                if mode in ("region", "safe", "notice") and start[0]:
                    if box[0] is not None:
                        canvas.delete(box[0])
                    box[0] = canvas.create_rectangle(
                        start[0][0], start[0][1], event.x, event.y,
                        outline="#00ffff", width=3)

            def up(event):
                if start[0] is None:
                    return
                x0, y0 = start[0]
                if mode in ("region", "safe", "notice"):
                    x1, x2 = sorted((x0, event.x))
                    y1, y2 = sorted((y0, event.y))
                    if mode == "region" and x2 - x1 >= 150 and y2 - y1 >= 150:
                        self.region = {"left": left + x1, "top": top + y1,
                                       "width": x2 - x1, "height": y2 - y1}
                        self._save_config()
                    elif mode == "safe" and x2 - x1 >= 65 and y2 - y1 >= 45:
                        # A captura do usuario mostra o minimapa embaixo e
                        # a direita. Essa checagem evita selecionar o mapa real.
                        if x1 >= width * .5 and y1 >= height * .35:
                            self.safe_region = {"left": left + x1, "top": top + y1,
                                                "width": x2 - x1, "height": y2 - y1}
                            self._save_config()
                    elif mode == "notice" and x2 - x1 >= 65 and y2 - y1 >= 25:
                        self.notice_region = {"left": left + x1, "top": top + y1,
                                              "width": x2 - x1, "height": y2 - y1}
                        self._save_config()
                    finish()
                else:
                    radius = 15
                    if (radius <= event.x < width - radius and
                            radius <= event.y < height - radius):
                        patch = image.crop((event.x - radius, event.y - radius,
                                            event.x + radius + 1, event.y + radius + 1))
                        patch.save(TEMPLATE_PATH)
                    finish()

            canvas.bind("<ButtonPress-1>", down)
            canvas.bind("<B1-Motion>", move)
            canvas.bind("<ButtonRelease-1>", up)
            overlay.bind("<Escape>", lambda _: finish())
            canvas.bind("<ButtonPress-3>", lambda _: finish())
        except Exception as exc:
            self.root.deiconify()
            messagebox.showerror("Falha na captura", str(exc))

    def start(self):
        if not self.region or not TEMPLATE_PATH.exists():
            messagebox.showinfo("Falta calibrar", "Selecione a area do mapa e aprenda uma box primeiro.")
            return
        if not self.apply_settings():
            return
        with self.state_lock:
            self.running = True
            self.stopped = False
        self.exit_event.clear()
        if self.worker is None or not self.worker.is_alive():
            self.worker = threading.Thread(target=self._collect_loop, daemon=True)
            self.worker.start()
        self.status.set("Ativo. Volte ao jogo; F9 pausa.")

    def pause(self):
        with self.state_lock:
            self.running = False
        self.status.set("Pausado. F8 retoma.")

    def stop(self):
        with self.state_lock:
            self.running = False
            self.stopped = True
        self.exit_event.set()
        self.status.set("Parado. F8 inicia novamente.")

    def _drain_events(self):
        while True:
            try:
                event, data = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "command":
                {"start": self.start, "pause": self.pause, "stop": self.stop}[str(data)]()
            elif event == "status":
                self.status.set(str(data))
            elif event == "click":
                self.count.set(self.count.get() + 1)
            elif event == "update_available":
                manifest = data
                if messagebox.askyesno(
                    "Nova versao disponivel",
                    f"AutoBox {manifest['version']} disponivel. Baixar e instalar agora?\n\n"
                    "Suas configuracoes e bibliotecas serao mantidas."):
                    self._download_update(manifest)
            elif event == "update_ready":
                try:
                    self.stop()
                    updater.start_update(data, Path(__file__).resolve().parent)
                    self.root.destroy()
                    return
                except Exception as exc:
                    messagebox.showerror("Falha ao iniciar atualizacao", str(exc))
        self.root.after(100, self._drain_events)

    def check_updates(self, silent=False):
        if not silent:
            self.status.set("Consultando atualizacoes no GitHub...")

        def check_worker():
            try:
                manifest = updater.check_for_update()
                if manifest:
                    self.events.put(("update_available", manifest))
                elif not silent:
                    self.events.put(("status", "Seu AutoBox ja esta atualizado."))
            except Exception as exc:
                if not silent:
                    self.events.put(("status", f"Nao foi possivel verificar a atualizacao: {exc}"))

        threading.Thread(target=check_worker, daemon=True).start()

    def _download_update(self, manifest):
        self.status.set(f"Baixando AutoBox {manifest['version']} com verificacao SHA-256...")

        def download_worker():
            try:
                staged = updater.stage_update(manifest)
                self.events.put(("update_ready", staged))
            except Exception as exc:
                self.events.put(("status", f"Atualizacao cancelada por falha: {exc}"))

        threading.Thread(target=download_worker, daemon=True).start()

    def _ready_to_click(self):
        with self.state_lock:
            if not self.running or self.stopped:
                return False
        title = active_window_title().casefold()
        return self.title_required in title

    def _sleep_interruptible(self, seconds: float):
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self.exit_event.is_set():
            with self.state_lock:
                if not self.running:
                    return
            self.exit_event.wait(min(0.2, end - time.monotonic()))

    @staticmethod
    def _screen_capture(sct):
        monitor = sct.monitors[1]
        raw = np.asarray(sct.grab(monitor))
        return cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR), monitor

    @staticmethod
    def _screen_area(frame, monitor, area):
        x = area["left"] - monitor["left"]
        y = area["top"] - monitor["top"]
        w, h = area["width"], area["height"]
        if x < 0 or y < 0 or x + w > frame.shape[1] or y + h > frame.shape[0]:
            return None
        return frame[y:y + h, x:x + w]

    def _choose_safe_point(self, center=False) -> tuple[int, int] | None:
        area = self.safe_region
        if not area:
            return None
        if center:
            return (area["left"] + area["width"] // 2,
                    area["top"] + area["height"] // 2)
        mx = max(12, int(area["width"] * .16))
        my = max(10, int(area["height"] * .16))
        return (random.randint(area["left"] + mx,
                               area["left"] + area["width"] - mx),
                random.randint(area["top"] + my,
                               area["top"] + area["height"] - my))

    def _click_current_box(self, sct, sample, region, target):
        """Revalida um alvo localmente antes de clicar; nao usa posicao antiga."""
        x, y = target
        left, top = max(0, x - 60), max(0, y - 60)
        right = min(region["width"], x + 61)
        bottom = min(region["height"], y + 61)
        area = {"left": region["left"] + left, "top": region["top"] + top,
                "width": right - left, "height": bottom - top}

        def near_target(expected, radius):
            frame, monitor = self._screen_capture(sct)
            if radiation_visible(frame) or find_death_panel(frame) is not None:
                return None
            crop = self._screen_area(frame, monitor, area)
            if crop is None:
                return None
            matches = locate_boxes(crop, sample, threshold=self.threshold)
            nearby = [(px + left, py + top, confidence)
                      for px, py, confidence in matches
                      if (px + left - expected[0]) ** 2 +
                         (py + top - expected[1]) ** 2 <= radius ** 2]
            if not nearby:
                return None
            best = min(nearby, key=lambda p: (p[0] - expected[0]) ** 2 +
                                             (p[1] - expected[1]) ** 2)
            return best, frame, monitor

        if not self._ready_to_click() or self.region != region:
            return None
        first = near_target(target, 35)
        if first is None:
            return None
        (x, y, _), _, _ = first
        # O cenario se desloca durante o voo. Reencontra e clica no alvo atual,
        # sem mover o cursor antes nem exigir que o box pare na tela.
        if not self._ready_to_click() or self.region != region:
            return None
        current = near_target((x, y), 35)
        if current is None:
            self.events.put(("status", "Box mudou de posicao. Atualizando o alvo antes de clicar..."))
            return None
        (x, y, score), frame, monitor = current
        if not self._ready_to_click() or self.region != region:
            return None
        pyautogui.click(region["left"] + x, region["top"] + y)
        return x, y, score, frame, monitor

    def _patrol_wait(self, sct, sample):
        """Verifica a tela durante a ronda em vez de esperar as cegas."""
        deadline = time.monotonic() + self.patrol_seconds
        while time.monotonic() < deadline and self._ready_to_click():
            self._sleep_interruptible(min(.25, max(0, deadline - time.monotonic())))
            if not self._ready_to_click():
                return
            frame, monitor = self._screen_capture(sct)
            if radiation_visible(frame) or find_death_panel(frame) is not None:
                return
            crop = self._screen_area(frame, monitor, self.region)
            if crop is not None and locate_boxes(crop, sample, threshold=self.threshold):
                self.events.put(("status", "Box encontrada durante a ronda. Conferindo a posicao..."))
                return

    def _track_box(self, frame, monitor, sample, region, point):
        """Acompanha apenas um alvo proximo da ultima posicao conhecida."""
        x, y = point
        left, top = max(0, round(x) - 90), max(0, round(y) - 90)
        right = min(region["width"], round(x) + 91)
        bottom = min(region["height"], round(y) + 91)
        area = {"left": region["left"] + left, "top": region["top"] + top,
                "width": right - left, "height": bottom - top}
        crop = self._screen_area(frame, monitor, area)
        if crop is None:
            return None
        matches = locate_boxes(crop, sample, threshold=self.threshold)
        nearby = sorted(((px + left, py + top, score) for px, py, score in matches
                         if (px + left - x) ** 2 + (py + top - y) ** 2 <= 60 ** 2),
                        key=lambda p: (p[0] - x) ** 2 + (p[1] - y) ** 2)
        if not nearby:
            return None
        # Se dois boxes estiverem quase igualmente proximos, nao troca de alvo.
        if len(nearby) > 1:
            d0 = ((nearby[0][0] - x) ** 2 + (nearby[0][1] - y) ** 2) ** .5
            d1 = ((nearby[1][0] - x) ** 2 + (nearby[1][1] - y) ** 2) ** .5
            if d1 - d0 < 12:
                return None
        return nearby[0][:2]

    def _reward_wait(self, sct, before_click, monitor, target_x: int,
                     sample=None, target=None, region=None):
        """Retorna confirmed, timeout ou interrupted para cada tentativa."""
        before_area = (self._screen_area(before_click, monitor, self.notice_region)
                       if self.notice_region else None)
        baseline = before_area.copy() if before_area is not None else None
        saw_clear = not reward_notice_visible(before_click, target_x)
        deadline = time.monotonic() + self.wait_seconds
        began = time.monotonic()
        hard_deadline = began + min(90.0, max(30.0, self.wait_seconds * 3))
        tracked = target
        best_distance = (((target[0] - region["width"] / 2) ** 2 +
                          (target[1] - region["height"] / 2) ** 2) ** .5
                         if target is not None and region is not None else None)
        next_track = began
        announced = False
        consecutive = 0
        while time.monotonic() < deadline and self._ready_to_click():
            self._sleep_interruptible(0.18)
            if not self._ready_to_click():
                return "interrupted"
            frame, current_monitor = self._screen_capture(sct)
            if radiation_visible(frame) or find_death_panel(frame) is not None:
                return "interrupted"
            now = time.monotonic()
            if sample is not None and tracked is not None and region is not None:
                if self.region != region:
                    return "interrupted"
                if now >= next_track:
                    next_track = now + .3
                    current_target = self._track_box(frame, current_monitor, sample, region, tracked)
                    if current_target is not None:
                        tracked = current_target
                        target_x = region["left"] + tracked[0] - current_monitor["left"]
                        distance = ((tracked[0] - region["width"] / 2) ** 2 +
                                    (tracked[1] - region["height"] / 2) ** 2) ** .5
                        # Centro da area espacial aproxima a posicao da nave.
                        # So progresso novo estende o prazo: oscilacoes nao prendem o bot.
                        if distance < best_distance - 4:
                            best_distance = distance
                            deadline = min(hard_deadline, max(deadline, now + self.wait_seconds))
                            if not announced:
                                self.events.put(("status", "Mantendo o mesmo box enquanto a nave se aproxima..."))
                                announced = True
            if baseline is not None and self.notice_region:
                current = self._screen_area(frame, current_monitor, self.notice_region)
                consecutive = consecutive + 1 if new_reward_message(baseline, current) else 0
                if consecutive >= 2 and time.monotonic() - began >= 0.3:
                    self.events.put(("status", "Novo YOU RECEIVED! Procurando a proxima box..."))
                    return "confirmed"
                continue
            # Compatibilidade com a versao anterior ate marcar a area.
            present = reward_notice_visible(frame, target_x)
            if not present:
                saw_clear = True
            elif saw_clear and time.monotonic() - began >= 0.55:
                self.events.put(("status", "Recompensa detectada! Procurando a proxima box..."))
                return "confirmed"
        return "timeout" if self._ready_to_click() else "interrupted"

    def _recover_collection(self):
        """Sai de uma sequencia sem recompensa sem repetir o alvo."""
        destination = self._choose_safe_point()
        if destination is None:
            with self.state_lock:
                self.running = False
            self.events.put(("status", "Tres tentativas sem confirmacao. Pausado: marque a zona segura no minimapa."))
            return False
        if not self._ready_to_click():
            return False
        pyautogui.click(*destination)
        self.events.put(("status", "Tres tentativas sem confirmacao. Ronda na zona segura para procurar outros boxes..."))
        self._sleep_interruptible(self.patrol_seconds)
        return True

    def _handle_radiation(self):
        if not self.safe_region:
            self.events.put(("command", "pause"))
            self.events.put(("status", "RADIAÇÃO! Bot pausado: marque a zona segura no minimapa."))
            return
        pos = self._choose_safe_point(center=True)
        if pos and self._ready_to_click():
            pyautogui.click(*pos)
            self.events.put(("status", "RADIAÇÃO! Voltando ao centro seguro do minimapa..."))
            self._sleep_interruptible(max(5.0, self.patrol_seconds))

    def _handle_death(self, sct, panel: tuple[int, int, int, int]):
        if not self.auto_revive:
            self.events.put(("command", "pause"))
            self.events.put(("status", "Nave destruida! Renascimento automatico desligado."))
            return
        now = time.monotonic()
        self.revive_attempts = [t for t in self.revive_attempts if now - t < 3600]
        if len(self.revive_attempts) >= self.revives_per_hour:
            self.events.put(("command", "pause"))
            self.events.put(("status", "Limite de renascimentos por hora atingido. Pausado."))
            return
        selection, repair_button = repair_click_points(panel, self.revive_target)
        if self._ready_to_click():
            self.revive_attempts.append(now)
            pyautogui.click(*selection)
            self._sleep_interruptible(.65)
            if self._ready_to_click():
                pyautogui.click(*repair_button)
                label = REPAIR_LABELS[self.revive_target]
                cost = REPAIR_COSTS[self.revive_target]
                self.events.put(("status", f"Tentando renascer: {label} ({cost} U)..."))
                self._sleep_interruptible(4.0)
                frame, _ = self._screen_capture(sct)
                if find_death_panel(frame) is not None:
                    self.events.put(("command", "pause"))
                    self.events.put(("status", "A tela de morte continua aberta. "
                                     "Pausado para evitar novos gastos."))

    def _collect_loop(self):
        sample = cv2.imread(str(TEMPLATE_PATH))
        if sample is None:
            self.events.put(("status", "Erro ao abrir modelo da box. Aprenda de novo."))
            return
        sample_modified = TEMPLATE_PATH.stat().st_mtime_ns
        recent: list[tuple[int, int, float]] = []
        previous: tuple[int, int] | None = None
        missed = 0
        collection_timeouts = 0
        last_patrol = 0.0
        try:
            with mss.mss() as sct:
                while not self.exit_event.is_set():
                    if not self._ready_to_click():
                        with self.state_lock:
                            paused = not self.running
                        if not paused:
                            self.events.put(("status", "Esperando janela do Interstellar Verse ficar ativa..."))
                        self.exit_event.wait(0.75)
                        continue

                    # Permite recalibrar durante uma pausa sem fechar o aplicativo.
                    new_modified = TEMPLATE_PATH.stat().st_mtime_ns
                    if new_modified != sample_modified:
                        new_sample = cv2.imread(str(TEMPLATE_PATH))
                        if new_sample is not None:
                            sample = new_sample
                            sample_modified = new_modified
                            recent.clear()
                            collection_timeouts = 0

                    full_frame, monitor = self._screen_capture(sct)
                    dead = find_death_panel(full_frame)
                    if dead is not None:
                        self._handle_death(sct, (dead[0] + monitor["left"],
                                                 dead[1] + monitor["top"], dead[2], dead[3]))
                        recent.clear()
                        previous = None
                        collection_timeouts = 0
                        continue
                    if radiation_visible(full_frame):
                        self._handle_radiation()
                        recent.clear()
                        previous = None
                        collection_timeouts = 0
                        continue

                    region = dict(self.region)
                    rx = region["left"] - monitor["left"]
                    ry = region["top"] - monitor["top"]
                    frame = full_frame[ry:ry + region["height"],
                                       rx:rx + region["width"]]
                    if frame.shape[:2] != (region["height"], region["width"]):
                        self.events.put(("command", "pause"))
                        self.events.put(("status", "Area selecionada fora da tela principal."))
                        continue
                    boxes = locate_boxes(frame, sample, threshold=self.threshold)
                    now = time.monotonic()
                    recent = [(x, y, t) for x, y, t in recent if now - t <= 18.0]
                    candidates = [
                        (x, y, score) for x, y, score in boxes
                        if all((x - rx) ** 2 + (y - ry) ** 2 > 35 ** 2 for rx, ry, _ in recent)
                    ]

                    if collection_timeouts >= MAX_COLLECTION_TIMEOUTS:
                        if self._recover_collection():
                            collection_timeouts = 0
                            previous = None
                            missed = 0
                            last_patrol = time.monotonic()
                        continue

                    if candidates:
                        missed = 0
                        if previous is None:
                            start = (region["width"] // 2, region["height"] // 2)
                        else:
                            start = previous
                        candidates.sort(key=lambda p: ((p[0] - start[0]) ** 2 +
                                                       (p[1] - start[1]) ** 2) /
                                        max(0.4, p[2]))
                        x, y, score = candidates[0]
                        if self._ready_to_click():
                            clicked = self._click_current_box(sct, sample, region, (x, y))
                            if clicked is None:
                                self._sleep_interruptible(.12)
                                continue
                            x, y, score, click_frame, click_monitor = clicked
                            self.events.put(("click", None))
                            self.events.put(("status", f"Indo ate box ({score:.0%} de confianca)..."))
                            recent.append((x, y, time.monotonic()))
                            previous = (x, y)
                            result = self._reward_wait(sct, click_frame, click_monitor,
                                                       region["left"] + x - click_monitor["left"],
                                                       sample=sample, target=(x, y), region=region)
                            if result == "confirmed":
                                collection_timeouts = 0
                            elif result == "timeout":
                                collection_timeouts += 1
                                self.events.put(("status",
                                    f"Tempo esgotado sem confirmacao ({collection_timeouts}/{MAX_COLLECTION_TIMEOUTS}). Procurando outro alvo..."))
                    else:
                        missed += 1
                        if (self.safe_region and missed >= 2 and
                                now - last_patrol >= self.patrol_seconds):
                            destination = self._choose_safe_point()
                            if destination and self._ready_to_click():
                                pyautogui.click(*destination)
                                self.events.put(("status", "Sem boxes. Ronda na zona segura do minimapa..."))
                                previous = None
                                # Mantem alvos recentes para evitar repetir falhas apos a ronda.
                                last_patrol = now
                                missed = 0
                                self._patrol_wait(sct, sample)
                        else:
                            if not self.safe_region and missed == 2:
                                self.events.put(("status", "Sem boxes. Esperando (ronda desativada ate marcar minimapa)."))
                            self._sleep_interruptible(0.7)

        except pyautogui.FailSafeException:
            self.events.put(("command", "stop"))
            self.events.put(("status", "Parado pelo canto superior esquerdo (seguranca)."))
        except Exception as exc:
            self.events.put(("command", "stop"))
            self.events.put(("status", f"Erro: {exc}"))

    def _close(self):
        self.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    AutoBoxApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
