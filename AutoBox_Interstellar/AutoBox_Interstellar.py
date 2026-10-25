"""AutoBox Interstellar Verse - automacao visual local, experimental.

Funciona exclusivamente por captura de tela e cliques do mouse.
Nao inspeciona trafego, memoria, contas ou arquivos do jogo.
"""

from __future__ import annotations

import ctypes
import contextlib
import importlib.util
import io
import subprocess
import sys
import json
import os
import queue
import random
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import cv2
import mss
import numpy as np
import pyautogui
from PIL import Image, ImageTk
from pynput import keyboard
import updater


APP_NAME = "AutoBox"
APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "AutoBoxInterstellar"
SETTINGS_PATH = APP_DIR / "config.json"
TEMPLATE_PATH = APP_DIR / "box_modelo.png"
PROFILES = (
    {"id": "interstellar", "label": "Interstellar", "title": "Interstellar Verse"},
    {"id": "krypton", "label": "Krypton", "title": "Krypton"},
)


def profile_paths(profile_id):
    if profile_id not in {profile["id"] for profile in PROFILES} | {"interstellar_browser"}:
        raise ValueError("Perfil desconhecido")
    # O Interstellar continua usando os caminhos antigos: sem perder calibracao.
    folder = APP_DIR if profile_id == "interstellar" else APP_DIR / "profiles" / profile_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "config.json", folder / "box_modelo.png"


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
                 threshold: float = 0.90,
                 require_bright: bool = True) -> list[tuple[int, int, float]]:
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
            if patch.size and (not require_bright or int(np.max(np.min(patch, axis=2))) >= 175):
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


def send_windows_click(x, y, hold, ready, wait, user32=None):
    """Envia entrada padrao do Windows, sem ocultar que ela e sintetica.

    O retorno confirma apenas insercao na fila do Windows, nao coleta no jogo.
    https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-sendinput
    """
    if user32 is None:
        if os.name != "nt":
            raise RuntimeError("Clique Windows disponivel somente no Windows")
        user32 = ctypes.WinDLL("user32", use_last_error=True)

    class MouseInput(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_int32), ("dy", ctypes.c_int32),
                    ("mouseData", ctypes.c_uint32), ("dwFlags", ctypes.c_uint32),
                    ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.c_size_t)]

    class InputUnion(ctypes.Union):
        _fields_ = [("mi", MouseInput)]

    class Input(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", ctypes.c_uint32), ("u", InputUnion)]

    send_input = user32.SendInput
    send_input.argtypes = [ctypes.c_uint32, ctypes.POINTER(Input), ctypes.c_int]
    send_input.restype = ctypes.c_uint32
    left, top = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
    width, height = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
    if width <= 1 or height <= 1 or not (left <= x < left + width and top <= y < top + height):
        raise ValueError("Posicao do clique fora da area de trabalho")
    if not ready():
        return False

    def event(flags, dx=0, dy=0):
        value = Input()
        value.type = 0
        value.mi = MouseInput(dx, dy, 0, flags, 0, 0)
        return value

    # MOVE + ABSOLUTE + VIRTUALDESK, seguido por um unico LEFTDOWN.
    move = event(0x0001 | 0x8000 | 0x4000,
                 round((x - left) * 65535 / (width - 1)),
                 round((y - top) * 65535 / (height - 1)))
    events = (Input * 2)(move, event(0x0002))
    inserted = send_input(2, events, ctypes.sizeof(Input))
    if inserted != 2:
        raise OSError("Windows nao inseriu o clique completo "
                      f"({inserted}/2 eventos). Verifique as permissoes do bot e do jogo.")
    try:
        wait(max(.03, hold))
    finally:
        release = (Input * 1)(event(0x0004))
        if send_input(1, release, ctypes.sizeof(Input)) != 1:
            raise OSError("Windows nao confirmou a liberacao do botao esquerdo.")
    return True


class AutoBoxApp:
    def __init__(self, root: tk.Tk, parent=None, profile_id="interstellar", coordinator=None, storage_id=None):
        self.root = root
        self.parent = parent if parent is not None else root
        self.profile_id = profile_id
        self.profile = next(profile for profile in PROFILES if profile["id"] == profile_id)
        self.coordinator = coordinator
        self.settings_path, self.template_path = profile_paths(storage_id or profile_id)
        if coordinator is None:
            root.title(APP_NAME + " - beta 3.6.1")
            root.geometry("640x920")

        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.cfg = self._read_config()
        self.region: dict | None = self.cfg.get("region")
        self.safe_region: dict | None = self.cfg.get("safe_region")
        self.notice_region: dict | None = self.cfg.get("notice_region")
        self.ship_region: dict | None = self.cfg.get("ship_region")
        self.status = tk.StringVar(value="Aguardando configuracao")
        self.region_status = tk.StringVar(value="Nao selecionada")
        self.safe_status = tk.StringVar(value="Nao selecionada")
        self.notice_status = tk.StringVar(value="Nao selecionada")
        self.sample_status = tk.StringVar(value="Nao aprendida")
        self.ship_status = tk.StringVar(value="Nao marcada")
        self.count = tk.IntVar(value=0)
        self.wait_var = tk.StringVar(value=str(self.cfg.get("wait", 5.0)))
        self.patrol_var = tk.StringVar(value=str(self.cfg.get("patrol_wait", 7.0)))
        self.threshold_var = tk.StringVar(value=str(self.cfg.get("threshold", 0.90)))
        self.title_var = tk.StringVar(value=self.cfg.get("title", self.profile["title"]))
        self.auto_revive_var = tk.BooleanVar(value=bool(self.cfg.get("auto_revive", False)))
        previous_destination = "portal" if self.cfg.get("auto_revive", False) else "base"
        self.revive_target_var = tk.StringVar(
            value=self.cfg.get("revive_target", previous_destination))
        self.revive_limit_var = tk.StringVar(value=str(self.cfg.get("revives_per_hour", 2)))

        self.click_hold_var = tk.StringVar(value=str(self.cfg.get(
            "click_hold", .12 if profile_id == "krypton" else 0)))
        self.click_hold = .12 if profile_id == "krypton" else 0
        self.input_method = self.cfg.get("input_method", "windows" if profile_id == "krypton" else "standard")
        self.input_method_var = tk.StringVar(value=(
            "Windows (SendInput)" if self.input_method == "windows" else "Padrao (PyAutoGUI)"))
        self.input_test_cancel = threading.Event()

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
        if coordinator is None:
            self._bind_hotkeys()
        self.root.after(100, self._drain_events)
        if coordinator is None:
            self.root.after(3500, lambda: self.check_updates(silent=True))
            self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _read_config(self):
        if self.settings_path.exists():
            try:
                config = json.loads(self.settings_path.read_text(encoding="utf-8"))
                return config if isinstance(config, dict) else {}
            except (OSError, json.JSONDecodeError):
                pass
        return {}

    def _save_config(self):
        self.cfg.update({
            "region": self.region,
            "safe_region": self.safe_region,
            "notice_region": self.notice_region,
            "ship_region": self.ship_region,
            "wait": self.wait_seconds,
            "patrol_wait": self.patrol_seconds,
            "threshold": self.threshold,
            "title": self.title_required,
            "auto_revive": self.auto_revive,
            "revive_target": self.revive_target,
            "revives_per_hour": self.revives_per_hour,
            "click_hold": self.click_hold,
            "input_method": self.input_method,
        })
        self.settings_path.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")

    def _draw(self):
        frame = ttk.Frame(self.parent, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="AutoBox | " + self.profile["label"],
                  font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Beta 3.6.1 • Configuracao independente por jogo",
                  foreground="#526477").pack(anchor="w", pady=(1, 13))

        capture_box = ttk.LabelFrame(frame, text="1. Preparar deteccao", padding=10)
        capture_box.pack(fill="x")
        ttk.Button(capture_box, text="Selecionar area do mapa",
                   command=lambda: self._capture_selection("region")).grid(row=0, column=0, sticky="ew")
        ttk.Button(capture_box, text="Aprender uma box",
                   command=lambda: self._capture_selection("sample")).grid(row=1, column=0, sticky="ew", pady=(7, 0))
        ttk.Button(capture_box, text="Marcar zona segura NO MINIMAPA",
                   command=lambda: self._capture_selection("safe")).grid(row=2, column=0, sticky="ew", pady=(7, 0))
        ttk.Button(capture_box, text="Marcar area das mensagens de coleta",
                   command=lambda: self._capture_selection("notice")).grid(row=3, column=0, sticky="ew", pady=(7, 0))
        ttk.Label(capture_box, textvariable=self.region_status).grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Label(capture_box, textvariable=self.sample_status).grid(row=1, column=1, sticky="w", padx=(12, 0))
        ttk.Label(capture_box, textvariable=self.safe_status).grid(row=2, column=1, sticky="w", padx=(12, 0))
        ttk.Label(capture_box, textvariable=self.notice_status).grid(row=3, column=1, sticky="w", padx=(12, 0))
        if self._uses_ship_area():
            ttk.Button(capture_box, text="Marcar area da nave (sem boxes)",
                       command=lambda: self._capture_selection("ship")).grid(
                row=4, column=0, sticky="ew", pady=(7, 0))
            ttk.Label(capture_box, textvariable=self.ship_status).grid(
                row=4, column=1, sticky="w", padx=(12, 0))
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
            if getattr(self, "browser_mode", False) and var is self.title_var:
                continue
            ttk.Label(settings, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(settings, textvariable=var, width=21).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        settings.columnconfigure(1, weight=1)
        if self.profile_id == "interstellar":
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
        else:
            ttk.Label(settings, text="Duracao do clique esquerdo (seg)").grid(
                row=4, column=0, sticky="w", pady=3)
            ttk.Entry(settings, textvariable=self.click_hold_var, width=21).grid(
                row=4, column=1, sticky="ew", padx=(8, 0), pady=3)
            ttk.Label(settings, text="Metodo do clique").grid(row=5, column=0, sticky="w")
            ttk.Combobox(settings, textvariable=self.input_method_var, state="readonly",
                         values=("Windows (SendInput)", "Padrao (PyAutoGUI)")).grid(
                row=5, column=1, sticky="ew", padx=(8, 0), pady=3)
            ttk.Button(settings, text="Testar clique no jogo (3 segundos)",
                       command=self._test_click).grid(row=6, column=0, columnspan=2,
                                                      sticky="ew", pady=4)
        if not getattr(self, "browser_mode", False):
            ttk.Button(settings, text="Capturar titulo do jogo (3 segundos)",
                       command=self._capture_window_title).grid(
                row=8, column=0, columnspan=2, sticky="ew", pady=4)
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
        if self.profile_id == "krypton":
            note = (
                "Perfil separado do Interstellar. Aprenda uma box do Krypton e "
                "marque as areas deste jogo, incluindo a nave. Use o titulo correto da janela. "
                "F8 inicia; F9 pausa; F10 para. Trocar de aba interrompe a coleta. "
                "Renascimento e deteccoes especificas do Interstellar nao sao usados aqui."
            )
        if getattr(self, "browser_mode", False):
            note = (
                "Modo experimental: F8 inicia, F9 pausa e F10 para. "
                "A janela dedicada pode ficar atras de outras janelas. "
                "Sua calibracao fica separada do modo que usa o mouse do Windows. "
                "Feche este modo para retornar ao AutoBox principal."
            )
        ttk.Label(frame, text=note, foreground="#59677c", wraplength=485,
                  justify="left").pack(anchor="w", pady=(12, 0))

        self.wait_seconds = 5.0
        self.patrol_seconds = 7.0
        self.threshold = 0.90
        self.title_required = self.profile["title"].casefold()
        self.auto_revive = False
        self.revive_target = "base"
        self.revives_per_hour = 2
        self.apply_settings(silent=True)

    def _refresh_labels(self):
        if self.region:
            self.region_status.set(f"{self.region['width']} x {self.region['height']} px")
        else:
            self.region_status.set("Nao selecionada")
        self.sample_status.set("Box aprendida ✓" if self.template_path.exists() else "Nao aprendida")
        self.safe_status.set("Area segura marcada ✓" if self.safe_region else "Nao selecionada")
        self.notice_status.set("Mensagens marcadas ✓" if self.notice_region else "Nao selecionada")
        self.ship_status.set("Nave marcada ✓" if self._ship_area_valid(self.region) else "Marque a nave")

    def apply_settings(self, silent=False):
        try:
            wait = float(self.wait_var.get().replace(",", "."))
            patrol = float(self.patrol_var.get().replace(",", "."))
            click_hold = float(self.click_hold_var.get().replace(",", "."))
            input_method = {"Windows (SendInput)": "windows",
                            "Padrao (PyAutoGUI)": "standard"}[self.input_method_var.get()]
            threshold = float(self.threshold_var.get().replace(",", "."))
            revive_limit = int(self.revive_limit_var.get())
            revive_target = self.revive_target_var.get()
            title = self.title_var.get().strip()
            if not (2.0 <= wait <= 30.0 and 3.0 <= patrol <= 30.0):
                raise ValueError("As esperas precisam estar nos intervalos 2–30 e 3–30 segundos.")
            if not 0 <= click_hold <= .3:
                raise ValueError("A duracao do clique precisa estar entre 0 e 0,3 segundos.")
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
            if (self.profile_id == "interstellar" and not silent and
                    self.auto_revive_var.get() and spend and changed_paid_choice):
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
            self.auto_revive = self.profile_id == "interstellar" and bool(self.auto_revive_var.get())
            self.click_hold = click_hold
            self.input_method = input_method
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

    def _capture_window_title(self):
        if self.running:
            self.pause()
        self.root.iconify()
        def capture():
            title = active_window_title().strip()
            if len(title) >= 5:
                self.title_var.set(title)
                self.status.set("Titulo capturado. Clique em Salvar ajustes.")
            else:
                self.status.set("Nao foi possivel capturar o titulo. Preencha o campo manualmente.")
            self.root.deiconify()
        self.root.after(3000, capture)

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
        if self.coordinator is not None:
            self.coordinator.stop_other_apps(self)
        if self.running:
            messagebox.showinfo("Pausar primeiro", "Aperte F9 antes de selecionar a area ou box.")
            return
        self.root.iconify()
        self.root.after(550, lambda: self._show_capture(mode))

    def _calibration_image(self):
        with mss.mss() as sct:
            mon = sct.monitors[1]
            shot = sct.grab(mon)
        return Image.frombytes("RGB", shot.size, shot.rgb), int(mon["left"]), int(mon["top"])

    def _capture_context(self):
        return mss.mss()

    def _show_capture(self, mode: str):
        if self.coordinator is not None and self.coordinator.active_app is not self:
            self.root.deiconify()
            return
        try:
            image, left, top = self._calibration_image()
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
            elif mode == "ship":
                hint = "ARRASTE um retangulo justo ao redor da NAVE, sem boxes"
            elif mode == "notice":
                hint = "ARRASTE so a area das mensagens de coleta (sem HUD ou nave)"
            else:
                hint = "CLIQUE NO CENTRO de uma box do jogo desta aba"
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
                if mode in ("region", "safe", "notice", "ship") and start[0]:
                    if box[0] is not None:
                        canvas.delete(box[0])
                    box[0] = canvas.create_rectangle(
                        start[0][0], start[0][1], event.x, event.y,
                        outline="#00ffff", width=3)

            def up(event):
                if start[0] is None:
                    return
                x0, y0 = start[0]
                if mode in ("region", "safe", "notice", "ship"):
                    x1, x2 = sorted((x0, event.x))
                    y1, y2 = sorted((y0, event.y))
                    if mode == "region" and x2 - x1 >= 150 and y2 - y1 >= 150:
                        self.region = {"left": left + x1, "top": top + y1,
                                       "width": x2 - x1, "height": y2 - y1}
                        self._save_config()
                    elif mode == "safe" and x2 - x1 >= 65 and y2 - y1 >= 45:
                        # A captura do usuario mostra o minimapa embaixo e
                        # a direita. Essa checagem evita selecionar o mapa real.
                        if (self.profile_id == "krypton" or
                                (x1 >= width * .5 and y1 >= height * .35)):
                            self.safe_region = {"left": left + x1, "top": top + y1,
                                                "width": x2 - x1, "height": y2 - y1}
                            self._save_config()
                    elif mode == "ship" and x2 - x1 >= 20 and y2 - y1 >= 20:
                        selected = {"left": left + x1, "top": top + y1,
                                    "width": x2 - x1, "height": y2 - y1}
                        old_area = self.ship_region
                        self.ship_region = selected
                        if self._ship_area_valid(self.region):
                            self._save_config()
                            self.status.set("Area da nave salva. Novos boxes nao serao clicados aqui.")
                        else:
                            self.ship_region = old_area
                            self.status.set("Marque primeiro o mapa e depois apenas a nave dentro dele.")
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
                        patch.save(self.template_path)
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
        self.input_test_cancel.set()
        if self.coordinator is not None and not self.coordinator.prepare_start(self):
            return
        # Nao reutiliza o sinal de saida enquanto o worker antigo ainda esta fechando.
        if self.worker is not None and self.worker.is_alive() and self.exit_event.is_set():
            self.root.after(100, self.start)
            return
        if not self.region or not self.template_path.exists():
            messagebox.showinfo("Falta calibrar", "Selecione a area do mapa e aprenda uma box primeiro.")
            return
        if self._uses_ship_area() and not self._ship_area_valid(self.region):
            messagebox.showinfo("Marcar a nave", "Clique em Marcar area da nave e selecione apenas a nave dentro do mapa.")
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
        self.input_test_cancel.set()
        with self.state_lock:
            self.running = False
        self.status.set("Pausado. F8 retoma.")

    def stop(self):
        self.input_test_cancel.set()
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
                    if self.coordinator is not None:
                        self.coordinator.stop_all()
                    else:
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
        if self.coordinator is not None and self.coordinator.active_app is not self:
            return False
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

    def _test_click_allowed(self):
        return (not self.input_test_cancel.is_set() and not self.running and
                (self.coordinator is None or self.coordinator.active_app is self) and
                self.title_required in active_window_title().casefold())

    def _test_click(self):
        if self.profile_id != "krypton":
            return
        self.stop()
        if not self.apply_settings():
            return
        if self.coordinator is not None:
            self.coordinator.stop_other_apps(self)
        self.input_test_cancel.clear()
        self.status.set("Em 3 segundos: volte ao Krypton e coloque o mouse sobre um box. F9 cancela.")
        self.root.iconify()

        def fire():
            if not self._test_click_allowed():
                self.status.set("Teste cancelado: confira o titulo da janela e volte ao jogo antes de 3 segundos.")
                self.root.deiconify()
                return
            if self.worker is not None and self.worker.is_alive():
                self.status.set("Teste cancelado: a coleta anterior ainda esta encerrando.")
                self.root.deiconify()
                return
            x, y = pyautogui.position()
            def worker():
                try:
                    sent = self._game_click(x, y, test=True)
                    self.events.put(("status", (
                        "Clique enviado ao Windows. Confira se a nave se moveu."
                        if sent else "Teste cancelado antes do clique.")))
                except Exception as exc:
                    self.events.put(("status", "Falha no teste de clique: " + str(exc)))
                finally:
                    self.input_test_cancel.set()
            threading.Thread(target=worker, daemon=True).start()

        self.root.after(3000, fire)

    def _game_click(self, x, y, test=False):
        """Mantem Interstellar; Krypton pode usar SendInput ou o metodo anterior."""
        ready = self._test_click_allowed if test else self._ready_to_click
        wait = self.input_test_cancel.wait if test else self._sleep_interruptible
        if not ready():
            return False
        if self.profile_id == "interstellar":
            pyautogui.click(x, y)
            return True
        if self.input_method == "windows":
            pyautogui.failSafeCheck()
            return send_windows_click(x, y, self.click_hold, ready, wait)
        if self.click_hold <= 0:
            pyautogui.click(x, y)
            return True
        pyautogui.moveTo(x, y, duration=0)
        if not ready():
            return False
        pyautogui.mouseDown(button="left")
        try:
            wait(self.click_hold)
        finally:
            pyautogui.mouseUp(button="left")
        return True

    def _uses_ship_area(self):
        return self.profile_id == "krypton" or getattr(self, "browser_mode", False)

    def _ship_area_valid(self, region):
        area = getattr(self, "ship_region", None)
        if not area or not region:
            return False
        try:
            values = [area[k] for k in ("left", "top", "width", "height")]
            if not all(isinstance(value, (int, float)) for value in values):
                return False
            return (20 <= area["width"] <= region["width"] / 2 and
                    20 <= area["height"] <= region["height"] / 2 and
                    region["left"] <= area["left"] and region["top"] <= area["top"] and
                    area["left"] + area["width"] <= region["left"] + region["width"] and
                    area["top"] + area["height"] <= region["top"] + region["height"])
        except (KeyError, TypeError):
            return False

    def _ship_center(self, region):
        if self._uses_ship_area() and self._ship_area_valid(region):
            area = self.ship_region
            return (area["left"] + area["width"] / 2 - region["left"],
                    area["top"] + area["height"] / 2 - region["top"])
        return region["width"] / 2, region["height"] / 2

    def _box_allowed(self, point, region):
        if not self._uses_ship_area():
            return True
        if not self._ship_area_valid(region):
            return False
        x, y = region["left"] + point[0], region["top"] + point[1]
        area = self.ship_region
        return not (area["left"] - 4 <= x <= area["left"] + area["width"] + 4 and
                    area["top"] - 4 <= y <= area["top"] + area["height"] + 4)

    def _click_current_box(self, sct, sample, region, target):
        """Revalida um alvo localmente antes de clicar; nao usa posicao antiga."""
        x, y = target
        if not self._box_allowed(target, region):
            return None
        left, top = max(0, x - 60), max(0, y - 60)
        right = min(region["width"], x + 61)
        bottom = min(region["height"], y + 61)
        area = {"left": region["left"] + left, "top": region["top"] + top,
                "width": right - left, "height": bottom - top}

        def near_target(expected, radius):
            frame, monitor = self._screen_capture(sct)
            if (self.profile_id == "interstellar" and radiation_visible(frame)) or (find_death_panel(frame) if self.profile_id == "interstellar" else None) is not None:
                return None
            crop = self._screen_area(frame, monitor, area)
            if crop is None:
                return None
            matches = locate_boxes(crop, sample, threshold=self.threshold,
                                   require_bright=self.profile_id == "interstellar")
            nearby = [(px + left, py + top, confidence)
                      for px, py, confidence in matches
                      if (px + left - expected[0]) ** 2 +
                         (py + top - expected[1]) ** 2 <= radius ** 2
                      and self._box_allowed((px + left, py + top), region)]
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
        if not self._box_allowed((x, y), region):
            return None
        if not self._game_click(region["left"] + x, region["top"] + y):
            return None
        return x, y, score, frame, monitor

    def _patrol_wait(self, sct, sample):
        """Verifica a tela durante a ronda em vez de esperar as cegas."""
        deadline = time.monotonic() + self.patrol_seconds
        while time.monotonic() < deadline and self._ready_to_click():
            self._sleep_interruptible(min(.25, max(0, deadline - time.monotonic())))
            if not self._ready_to_click():
                return
            frame, monitor = self._screen_capture(sct)
            if (self.profile_id == "interstellar" and radiation_visible(frame)) or (find_death_panel(frame) if self.profile_id == "interstellar" else None) is not None:
                return
            crop = self._screen_area(frame, monitor, self.region)
            if crop is not None:
                found = locate_boxes(crop, sample, threshold=self.threshold,
                                     require_bright=self.profile_id == "interstellar")
                if any(self._box_allowed((x, y), self.region) for x, y, _ in found):
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
        matches = locate_boxes(crop, sample, threshold=self.threshold,
                                   require_bright=self.profile_id == "interstellar")
        nearby = sorted(((px + left, py + top, score) for px, py, score in matches
                         if (px + left - x) ** 2 + (py + top - y) ** 2 <= 60 ** 2
                         and self._box_allowed((px + left, py + top), region)),
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
        """Mantem o alvo; no Krypton retoma uma aproximacao que parou."""
        before_area = (self._screen_area(before_click, monitor, self.notice_region)
                       if self.notice_region else None)
        baseline = before_area.copy() if before_area is not None else None
        saw_clear = self.profile_id != "interstellar" or not reward_notice_visible(before_click, target_x)
        began = time.monotonic()
        deadline = began + self.wait_seconds
        hard_deadline = began + min(90.0, max(30.0, self.wait_seconds * 3))
        tracked = target
        self.last_tracked_target = target
        origin = self._ship_center(region) if region is not None else None
        best_distance = (((target[0] - origin[0]) ** 2 +
                          (target[1] - origin[1]) ** 2) ** .5
                         if target is not None and region is not None else None)
        arrival_radius = 70
        if self.profile_id == "krypton" and self._ship_area_valid(region):
            area = self.ship_region
            arrival_radius = max(70, ((area["width"] / 2) ** 2 +
                                      (area["height"] / 2) ** 2) ** .5 + 30)
        last_progress = began
        last_retry = began
        retries = 0
        next_track = began
        announced = False
        missing_near_ship = 0
        departure_deadline = None
        consecutive = 0
        while time.monotonic() < deadline and self._ready_to_click():
            self._sleep_interruptible(0.18)
            if not self._ready_to_click():
                return "interrupted"
            frame, current_monitor = self._screen_capture(sct)
            if (self.profile_id == "interstellar" and radiation_visible(frame)) or (
                    find_death_panel(frame) if self.profile_id == "interstellar" else None) is not None:
                return "interrupted"
            now = time.monotonic()
            # Confirma recompensa antes de considerar qualquer novo clique.
            if baseline is not None and self.notice_region:
                current = self._screen_area(frame, current_monitor, self.notice_region)
                consecutive = consecutive + 1 if new_reward_message(baseline, current) else 0
                if consecutive >= 2 and now - began >= .3:
                    self.events.put(("status", "Nova recompensa! Procurando a proxima box..."))
                    return "confirmed"
            else:
                present = self.profile_id == "interstellar" and reward_notice_visible(frame, target_x)
                if not present:
                    saw_clear = True
                elif saw_clear and now - began >= .55:
                    self.events.put(("status", "Recompensa detectada! Procurando a proxima box..."))
                    return "confirmed"

            if sample is not None and tracked is not None and region is not None:
                if self.region != region:
                    return "interrupted"
                if now >= next_track:
                    next_track = now + .3
                    current_target = self._track_box(frame, current_monitor, sample, region, tracked)
                    if current_target is None:
                        missing_near_ship = missing_near_ship + 1 if best_distance <= arrival_radius else 0
                        if missing_near_ship >= 2 and departure_deadline is None:
                            departure_deadline = now + .35
                    else:
                        missing_near_ship = 0
                        departure_deadline = None
                        tracked = current_target
                        self.last_tracked_target = tracked
                        target_x = region["left"] + tracked[0] - current_monitor["left"]
                        distance = ((tracked[0] - origin[0]) ** 2 +
                                    (tracked[1] - origin[1]) ** 2) ** .5
                        if distance < best_distance - 4:
                            best_distance = distance
                            last_progress = now
                            deadline = min(hard_deadline, max(deadline, now + self.wait_seconds))
                            if not announced:
                                self.events.put(("status", "Mantendo o mesmo box enquanto a nave se aproxima..."))
                                announced = True
                        # Um destino de tela pode ficar desatualizado enquanto a camera move.
                        # Retenta somente este alvo, ainda visivel e longe da nave.
                        browser_mode = getattr(self, "browser_mode", False)
                        retry_limit = 6 if browser_mode else 2
                        reaim_browser = (browser_mode and now - last_retry >= .9 and
                                         self._box_allowed(tracked, region))
                        resume_krypton = (self.profile_id == "krypton" and distance > arrival_radius and
                                          now - last_progress >= 1.0 and now - last_retry >= 1.2)
                        if ((reaim_browser or resume_krypton) and
                                retries < retry_limit and consecutive == 0):
                            last_retry = now
                            clicked = self._click_current_box(sct, sample, region, tracked)
                            if clicked is not None:
                                retries += 1
                                tracked = clicked[:2]
                                self.last_tracked_target = tracked
                                last_progress = time.monotonic()
                                deadline = min(hard_deadline, max(
                                    deadline, last_progress + self.wait_seconds))
                                self.events.put(("status",
                                    f"Atualizando a rota para o mesmo box ({retries}/{retry_limit})..."))
            if departure_deadline is not None and now >= departure_deadline:
                self.events.put(("status", "Box saiu de vista perto da nave. Procurando a proxima (sem confirmacao)..."))
                return "unconfirmed"
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
        self._game_click(*destination)
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
            self._game_click(*pos)
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
            self._game_click(*selection)
            self._sleep_interruptible(.65)
            if self._ready_to_click():
                self._game_click(*repair_button)
                label = REPAIR_LABELS[self.revive_target]
                cost = REPAIR_COSTS[self.revive_target]
                self.events.put(("status", f"Tentando renascer: {label} ({cost} U)..."))
                self._sleep_interruptible(4.0)
                frame, _ = self._screen_capture(sct)
                if (find_death_panel(frame) if self.profile_id == "interstellar" else None) is not None:
                    self.events.put(("command", "pause"))
                    self.events.put(("status", "A tela de morte continua aberta. "
                                     "Pausado para evitar novos gastos."))

    def _collect_loop(self):
        sample = cv2.imread(str(self.template_path))
        if sample is None:
            self.events.put(("status", "Erro ao abrir modelo da box. Aprenda de novo."))
            return
        sample_modified = self.template_path.stat().st_mtime_ns
        recent: list[tuple[int, int, float]] = []
        missed = 0
        collection_timeouts = 0
        last_patrol = 0.0
        try:
            with self._capture_context() as sct:
                while not self.exit_event.is_set():
                    if not self._ready_to_click():
                        with self.state_lock:
                            paused = not self.running
                        if not paused:
                            self.events.put(("status", "Esperando a janela do jogo desta aba ficar ativa..."))
                        self.exit_event.wait(0.75)
                        continue

                    # Permite recalibrar durante uma pausa sem fechar o aplicativo.
                    new_modified = self.template_path.stat().st_mtime_ns
                    if new_modified != sample_modified:
                        new_sample = cv2.imread(str(self.template_path))
                        if new_sample is not None:
                            sample = new_sample
                            sample_modified = new_modified
                            recent.clear()
                            collection_timeouts = 0

                    full_frame, monitor = self._screen_capture(sct)
                    dead = (find_death_panel(full_frame) if self.profile_id == "interstellar" else None)
                    if dead is not None:
                        self._handle_death(sct, (dead[0] + monitor["left"],
                                                 dead[1] + monitor["top"], dead[2], dead[3]))
                        recent.clear()
                        collection_timeouts = 0
                        continue
                    if (self.profile_id == "interstellar" and radiation_visible(full_frame)):
                        self._handle_radiation()
                        recent.clear()
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
                    boxes = locate_boxes(frame, sample, threshold=self.threshold,
                                   require_bright=self.profile_id == "interstellar")
                    now = time.monotonic()
                    recent_ttl = 2.5 if self._uses_ship_area() else 18.0
                    recent = [(x, y, t) for x, y, t in recent if now - t <= recent_ttl]
                    boxes = [(x, y, score) for x, y, score in boxes
                             if self._box_allowed((x, y), region)]
                    candidates = [
                        (x, y, score) for x, y, score in boxes
                        if all((x - rx) ** 2 + (y - ry) ** 2 > 35 ** 2 for rx, ry, _ in recent)
                    ]

                    if collection_timeouts >= MAX_COLLECTION_TIMEOUTS:
                        if self._recover_collection():
                            collection_timeouts = 0
                            missed = 0
                            last_patrol = time.monotonic()
                        continue

                    if candidates:
                        missed = 0
                        # Usa a posicao calibrada da nave no Krypton,
                        # nunca as coordenadas antigas do clique anterior.
                        center = self._ship_center(region)
                        candidates.sort(key=lambda p: (
                            (p[0] - center[0]) ** 2 + (p[1] - center[1]) ** 2,
                            -p[2], p[0], p[1]))
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
                            result = self._reward_wait(sct, click_frame, click_monitor,
                                                       region["left"] + x - click_monitor["left"],
                                                       sample=sample, target=(x, y), region=region)
                            if self._uses_ship_area() and result in ("confirmed", "unconfirmed"):
                                # A camera mudou: nao conserva as coordenadas antigas da rota.
                                recent.clear()
                                final_target = self.last_tracked_target
                                if final_target is not None:
                                    recent.append((*final_target, time.monotonic()))
                                collection_timeouts = 0
                            if result == "confirmed":
                                collection_timeouts = 0
                            elif result == "timeout":
                                collection_timeouts += 1
                                self.events.put(("status",
                                    f"Tempo esgotado sem confirmacao ({collection_timeouts}/{MAX_COLLECTION_TIMEOUTS}). Procurando outro alvo..."))
                    else:
                        if self._uses_ship_area() and boxes:
                            # Ha boxes visiveis, apenas temporariamente filtrados.
                            # Nao interrompe a area com uma nova ordem de minimapa.
                            self._sleep_interruptible(.3)
                            continue
                        missed += 1
                        if (self.safe_region and missed >= 2 and
                                now - last_patrol >= self.patrol_seconds):
                            destination = self._choose_safe_point()
                            if destination and self._ready_to_click():
                                self._game_click(*destination)
                                self.events.put(("status", "Sem boxes. Ronda na zona segura do minimapa..."))
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


class AutoBoxWindow:
    """Uma aba por perfil; somente a aba selecionada pode operar o mouse."""
    def __init__(self, root):
        self.root = root
        self.apps = {}
        self.active_app = None
        root.title(APP_NAME + " - beta 3.6.1")
        root.geometry("660x" + str(min(970, root.winfo_screenheight() - 90)))
        root.minsize(590, min(780, root.winfo_screenheight() - 90))
        self.background_process = None
        ttk.Button(root, text="Interstellar: testar coleta sem ocupar o mouse",
                   command=self._launch_background).pack(fill="x", padx=10, pady=7)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)
        for profile in PROFILES:
            tab = ttk.Frame(self.notebook)
            self.notebook.add(tab, text=profile["label"])
            canvas = tk.Canvas(tab, highlightthickness=0)
            scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            body = ttk.Frame(canvas)
            item = canvas.create_window((0, 0), window=body, anchor="nw")
            body.bind("<Configure>", lambda event, c=canvas: c.configure(scrollregion=c.bbox("all")))
            canvas.bind("<Configure>", lambda event, c=canvas, i=item: c.itemconfigure(i, width=event.width))
            app = AutoBoxApp(root, parent=body, profile_id=profile["id"], coordinator=self)
            self.apps[str(tab)] = app
        self.active_app = self.apps[self.notebook.select()]
        self.notebook.bind("<<NotebookTabChanged>>", self._tab_changed)
        self._bind_hotkeys()
        root.after(3500, lambda: self.active_app.check_updates(silent=True))
        root.protocol("WM_DELETE_WINDOW", self._close)

    def _launch_background(self):
        if self.background_process is not None and self.background_process.poll() is None:
            return
        self.stop_all()
        if any(app.worker is not None and app.worker.is_alive() for app in self.apps.values()):
            self.root.after(100, self._launch_background)
            return
        self.keyboard_listener.stop()
        try:
            self.background_process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--browser-mode"],
                cwd=str(Path(__file__).resolve().parent),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            self._bind_hotkeys()
            messagebox.showerror("Modo navegador", str(exc))
            return
        self.root.iconify()
        self._watch_background()

    def _watch_background(self):
        if self.background_process.poll() is None:
            self.root.after(500, self._watch_background)
            return
        self.background_process = None
        self._bind_hotkeys()
        self.root.deiconify()

    def stop_other_apps(self, app):
        for other in self.apps.values():
            if other is not app:
                other.stop()

    def prepare_start(self, app):
        if app is not self.active_app:
            return False
        self.stop_other_apps(app)
        if any(other.worker is not None and other.worker.is_alive()
               for other in self.apps.values() if other is not app):
            app.status.set("Aguardando encerrar a outra aba...")
            self.root.after(100, lambda: app.start() if app is self.active_app else None)
            return False
        return True

    def _tab_changed(self, event=None):
        selected = self.apps.get(self.notebook.select())
        if selected is None or selected is self.active_app:
            return
        self.stop_all()
        self.active_app = selected
        selected.status.set("Perfil " + selected.profile["label"] + " selecionado. F8 inicia.")

    def stop_all(self):
        for app in self.apps.values():
            app.stop()

    def _bind_hotkeys(self):
        def on_press(key):
            command = {keyboard.Key.f8: "start", keyboard.Key.f9: "pause",
                       keyboard.Key.f10: "stop"}.get(key)
            if command and self.active_app is not None:
                self.active_app.events.put(("command", command))
        self.keyboard_listener = keyboard.Listener(on_press=on_press)
        self.keyboard_listener.daemon = True
        self.keyboard_listener.start()

    def _close(self):
        if self.background_process is not None and self.background_process.poll() is None:
            messagebox.showinfo("Janela dedicada", "Feche primeiro a janela do modo navegador.")
            return
        self.stop_all()
        self.keyboard_listener.stop()
        self.root.destroy()


GAME_URL = "https://interstellar-verse.com/play/#play"


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


def ensure_browser_runtime():
    if importlib.util.find_spec("playwright") is None:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "playwright>=1.50,<2"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=240,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError("Nao foi possivel preparar o navegador. Verifique a internet e tente novamente.")


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

    def start(self, executable):
        if self.thread is not None and self.thread.is_alive():
            return
        self.error = None
        self.warning = None
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
                page = context.pages[0] if context.pages else context.new_page()
                try:
                    page.goto(GAME_URL, wait_until="domcontentloaded", timeout=45000)
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
                            result = page.screenshot(type="png", timeout=5000)
                        elif operation == "click":
                            x, y = payload
                            if not (0 <= x < self.viewport["width"] and 0 <= y < self.viewport["height"]):
                                raise ValueError("Clique fora da imagem do jogo.")
                            page.mouse.click(x, y, button="left", delay=40)
                            result = True
                        else:
                            raise ValueError("Comando de navegador desconhecido.")
                        reply.put((True, result))
                    except Exception as exc:
                        reply.put((False, str(exc)))
        except Exception as exc:
            self.error = "Nao foi possivel abrir o Opera GX dedicado: " + str(exc)
        finally:
            self.ready.clear()
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            self.closed.set()


class BackgroundApp(AutoBoxApp):
    """Coleta visual experimental numa sessao isolada do Opera GX."""
    def __init__(self, root):
        self.browser_mode = True
        self.closing = threading.Event()
        viewport = {"width": max(800, min(1280, root.winfo_screenwidth() - 60)),
                    "height": max(500, min(720, root.winfo_screenheight() - 120))}
        self.session = BrowserSession(APP_DIR / "profiles" / "interstellar_browser" / "opera_session",
                                      viewport)
        self.installing = False
        self.last_click_preview = None
        self.last_browser_frame = None
        self.aiming_box = False
        canvas = tk.Canvas(root, highlightthickness=0)
        scroll = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = ttk.Frame(canvas)
        item = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
        super().__init__(root, parent=body, storage_id="interstellar_browser")
        root.title("AutoBox - Interstellar sem mouse (teste) - beta 3.6.1")
        root.geometry("680x" + str(min(950, root.winfo_screenheight() - 80)))
        self.opera_executable = self.cfg.get("opera_executable", "") or find_opera_gx()
        self.root.after(500, self._monitor_session)

    def _draw(self):
        box = ttk.LabelFrame(self.parent, text="Sessao dedicada do Opera GX — experimental", padding=10)
        box.pack(fill="x", padx=14, pady=(10, 0))
        ttk.Label(box, text=(
            "Abra a sessao, entre no jogo e calibre pela imagem desta janela. "
            "A coleta usa comandos do navegador e um perfil separado. "
            "Neste primeiro teste, deixe o Opera dedicado aberto; pode ficar atras de outras janelas."),
            wraplength=600).pack(anchor="w")
        ttk.Button(box, text="Abrir Opera GX dedicado", command=self._open_browser).pack(
            fill="x", pady=(8, 3))
        ttk.Button(box, text="Localizar executavel do Opera GX", command=self._choose_opera).pack(fill="x")
        ttk.Button(box, text="Ver ponto do ultimo clique na box",
                   command=self._show_last_click).pack(fill="x", pady=(4, 0))
        super()._draw()

    def _show_last_click(self):
        self.pause()
        if self.last_click_preview is None:
            self.status.set("Ainda nao ha clique de box para mostrar.")
            return
        frame, x, y = self.last_click_preview
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        original_width, original_height = image.size
        image.thumbnail((self.root.winfo_screenwidth() - 80, self.root.winfo_screenheight() - 160))
        scale_x, scale_y = image.width / original_width, image.height / original_height
        window = tk.Toplevel(self.root)
        window.title("Ultimo clique: vermelho = ponto enviado; amarelo = nave")
        ttk.Label(window, text="Coleta pausada. Confira se a cruz vermelha fica no centro do box.",
                  padding=8).pack()
        canvas = tk.Canvas(window, width=image.width, height=image.height, highlightthickness=0)
        canvas.pack()
        photo = ImageTk.PhotoImage(image)
        canvas._preview_photo = photo
        canvas.create_image(0, 0, anchor="nw", image=photo)
        px, py = x * scale_x, y * scale_y
        canvas.create_line(px - 14, py, px + 14, py, fill="red", width=2)
        canvas.create_line(px, py - 14, px, py + 14, fill="red", width=2)
        canvas.create_oval(px - 7, py - 7, px + 7, py + 7, outline="red", width=2)
        if self.ship_region:
            area = self.ship_region
            canvas.create_rectangle(area["left"] * scale_x, area["top"] * scale_y,
                                    (area["left"] + area["width"]) * scale_x,
                                    (area["top"] + area["height"]) * scale_y,
                                    outline="yellow", width=2)

    def _monitor_session(self):
        if self.session.closed.is_set() and self.running:
            self.stop()
            self.status.set("A sessao dedicada foi fechada. Abra-a novamente para retomar.")
        if not self.closing.is_set():
            self.root.after(500, self._monitor_session)

    def _choose_opera(self):
        chosen = filedialog.askopenfilename(title="Selecione opera.exe ou launcher.exe do Opera GX",
                                            filetypes=[("Executavel Windows", "*.exe")])
        if chosen:
            self.opera_executable = chosen
            self.cfg["opera_executable"] = chosen
            self._save_config()
            self.status.set("Opera GX selecionado. Abra a sessao dedicada.")

    def _open_browser(self):
        if self.installing or self.session.ready.is_set():
            return
        executable = getattr(self, "opera_executable", "") or find_opera_gx()
        if not executable or not Path(executable).is_file():
            self.status.set("Nao localizei o Opera GX. Use Localizar executavel.")
            return
        self.installing = True
        self.status.set("Preparando o controle do navegador. A primeira vez pode demorar...")
        def prepare():
            try:
                ensure_browser_runtime()
                if self.closing.is_set():
                    return
                self.session.start(executable)
                if not self.session.ready.wait(65):
                    raise RuntimeError(self.session.error or "O Opera GX nao respondeu. Confira o executavel.")
                self.events.put(("status", self.session.warning or
                    "Sessao aberta. Faca login no jogo, calibre o mapa e aprenda uma box nesta sessao."))
            except Exception as exc:
                self.events.put(("status", str(exc)))
            finally:
                self.installing = False
        threading.Thread(target=prepare, daemon=True).start()

    def start(self):
        if not self.session.ready.is_set():
            self.status.set("Abra primeiro o Opera GX dedicado e entre no jogo.")
            return
        super().start()

    def _ready_to_click(self):
        with self.state_lock:
            return self.running and not self.stopped and self.session.ready.is_set()

    def _click_current_box(self, sct, sample, region, target):
        self.aiming_box = True
        try:
            return super()._click_current_box(sct, sample, region, target)
        finally:
            self.aiming_box = False

    def _game_click(self, x, y, test=False):
        if not self._ready_to_click():
            return False
        sent = self.session.request("click", (x, y), allowed=self._ready_to_click)
        if sent and self.aiming_box and self.last_browser_frame is not None:
            self.last_click_preview = (self.last_browser_frame.copy(), x, y)
        return sent

    def _screen_capture(self, sct):
        data = self.session.request("screenshot")
        image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("Nao foi possivel capturar a janela dedicada.")
        self.last_browser_frame = image.copy()
        height, width = image.shape[:2]
        if (width, height) != (self.session.viewport["width"], self.session.viewport["height"]):
            raise RuntimeError("A imagem do navegador mudou de tamanho. Abra novamente e recalibre.")
        return image, {"left": 0, "top": 0, "width": width, "height": height}

    def _calibration_image(self):
        data = self.session.request("screenshot")
        return Image.open(io.BytesIO(data)).convert("RGB"), 0, 0

    def _capture_context(self):
        return contextlib.nullcontext(None)

    def _capture_window_title(self):
        self.status.set("Neste modo nao e preciso capturar titulo: o controle usa a sessao dedicada.")

    def check_updates(self, silent=False):
        if not silent:
            self.status.set("Feche este modo e atualize pelo AutoBox principal.")

    def _close(self):
        self.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        self.closing.set()
        self.status.set("Fechando a sessao dedicada...")
        done = threading.Event()
        def shutdown():
            try:
                self.session.close()
            finally:
                done.set()
        threading.Thread(target=shutdown, daemon=True).start()
        def finish():
            if done.is_set():
                self.root.destroy()
            else:
                self.root.after(100, finish)
        finish()


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    if "--browser-mode" in sys.argv:
        BackgroundApp(root)
    else:
        AutoBoxWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
