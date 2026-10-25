"""AutoBox Sem Mouse — aplicativo independente, exclusivo de coleta no Interstellar."""
from __future__ import annotations
import ctypes
import io
import json
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
import cv2
import numpy as np
from PIL import Image, ImageTk
from pynput import keyboard
from browser_session import BrowserSession, find_opera_gx
from collector import Collector
from controller import inside
from vision import locate_boxes
import updater

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "AutoBoxSemMouse"
CONFIG_PATH = APP_DIR / "config.json"
MODEL_PATH = APP_DIR / "box.png"
if os.name == "nt":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

def read_config():
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}

def valid_area(area, viewport):
    try:
        return (all(isinstance(area[k], (int, float)) for k in ("left", "top", "width", "height"))
                and area["left"] >= 0 and area["top"] >= 0 and area["width"] > 0 and area["height"] > 0
                and area["left"] + area["width"] <= viewport["width"]
                and area["top"] + area["height"] <= viewport["height"])
    except (KeyError, TypeError):
        return False

class AutoBoxSemMouse:
    def __init__(self, root):
        self.root = root
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.cfg = read_config()
        self.viewport = {"width": max(800, min(1280, root.winfo_screenwidth()-60)),
                         "height": max(500, min(720, root.winfo_screenheight()-120))}
        if self.cfg.get("viewport") != self.viewport:
            for key in ("map", "ship", "notice", "minimap"):
                self.cfg.pop(key, None)
        self.cfg["viewport"] = self.viewport
        self.session = BrowserSession(APP_DIR / "opera_session", self.viewport)
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.stop_event.set()
        self.worker = None
        self.opening = False
        self.closing = False
        self.last_preview = None
        self.attempts = self.confirmed = self.failed = 0
        self.status = tk.StringVar(value="Abra o Opera GX dedicado para comecar.")
        self.stats = tk.StringVar(value="Tentativas: 0 | Confirmadas: 0 | Sem progresso: 0")
        self.threshold = tk.StringVar(value=str(self.cfg.get("threshold", .9)))
        self.area_labels = {}
        root.title("AutoBox Sem Mouse — beta " + updater.CURRENT_VERSION)
        root.geometry("710x" + str(min(900, root.winfo_screenheight()-90)))
        self._draw()
        self._refresh()
        self._bind_keys()
        root.after(100, self._drain)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def _draw(self):
        canvas = tk.Canvas(self.root, highlightthickness=0)
        scroll = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = ttk.Frame(canvas)
        item = canvas.create_window((0,0), window=body, anchor="nw")
        body.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(item, width=event.width))
        frame = ttk.Frame(body, padding=15)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="AutoBox Sem Mouse", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Somente coleta no Interstellar • sessao independente • experimental").pack(anchor="w", pady=(2, 12))
        browser = ttk.LabelFrame(frame, text="1. Janela dedicada", padding=10)
        browser.pack(fill="x")
        ttk.Button(browser, text="Abrir Opera GX e entrar no jogo", command=self.open_browser).pack(fill="x")
        ttk.Button(browser, text="Localizar executavel do Opera GX", command=self.choose_opera).pack(fill="x", pady=(5,0))
        ttk.Label(browser, text="Faca o login nessa janela. Pode deixa-la atras de outros programas; teste sem minimizar.",
                  wraplength=650).pack(anchor="w", pady=(5,0))
        calibrate = ttk.LabelFrame(frame, text="2. Calibrar pela imagem da sessao", padding=10)
        calibrate.pack(fill="x", pady=(10,0))
        for row, (key, label) in enumerate((
                ("map", "Marcar area espacial do mapa"), ("sample", "Aprender uma box"),
                ("ship", "Marcar somente a nave"), ("minimap", "Marcar zona de patrulha no minimapa"),
                ("notice", "Marcar mensagens de recompensa"))):
            ttk.Button(calibrate, text=label, command=lambda k=key: self.calibrate(k)).grid(
                row=row, column=0, sticky="ew", pady=2)
            var = tk.StringVar()
            self.area_labels[key] = var
            ttk.Label(calibrate, textvariable=var).grid(row=row, column=1, sticky="w", padx=10)
        calibrate.columnconfigure(0, weight=1)
        controls = ttk.LabelFrame(frame, text="3. Coleta", padding=10)
        controls.pack(fill="x", pady=(10,0))
        buttons = ttk.Frame(controls)
        buttons.pack(fill="x")
        for label, command in (("Iniciar (F8)", self.start), ("Pausar (F9)", self.pause), ("Parar (F10)", self.stop)):
            ttk.Button(buttons, text=label, command=command).pack(side="left", fill="x", expand=True, padx=2)
        ttk.Label(controls, textvariable=self.status, wraplength=640).pack(anchor="w", pady=(8,3))
        ttk.Label(controls, textvariable=self.stats).pack(anchor="w")
        settings = ttk.Frame(frame)
        settings.pack(fill="x", pady=8)
        ttk.Label(settings, text="Confianca da imagem (0,60 a 0,95)").pack(side="left")
        ttk.Entry(settings, textvariable=self.threshold, width=8).pack(side="left", padx=8)
        ttk.Button(settings, text="Salvar", command=self.save).pack(side="left")
        ttk.Button(frame, text="Testar deteccao (sem mover a nave)", command=self.test_detection).pack(fill="x", pady=3)
        ttk.Button(frame, text="Ver imagem e ponto do ultimo clique", command=self.preview).pack(fill="x", pady=3)
        ttk.Button(frame, text="Verificar atualizacoes deste bot", command=self.check_updates).pack(fill="x", pady=3)
        ttk.Label(frame, text="Historico da sessao").pack(anchor="w", pady=(6,2))
        self.log = tk.Text(frame, height=6, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)

    def _bind_keys(self):
        def pressed(key):
            action = {keyboard.Key.f8:"start", keyboard.Key.f9:"pause", keyboard.Key.f10:"stop"}.get(key)
            if action:
                self.events.put(("command", action))
        self.listener = keyboard.Listener(on_press=pressed)
        self.listener.daemon = True
        self.listener.start()

    def say(self, text):
        self.status.set(text)
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S") + " — " + text + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 70:
            self.log.delete("1.0", "20.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _refresh(self):
        for key, label in self.area_labels.items():
            ready = MODEL_PATH.is_file() if key == "sample" else valid_area(self.cfg.get(key), self.viewport)
            label.set("Pronto" if ready else ("Opcional" if key in ("notice","minimap") else "Falta calibrar"))

    def save(self):
        try:
            threshold = float(self.threshold.get().replace(",", "."))
            if not .6 <= threshold <= .95:
                raise ValueError("Use confianca entre 0,60 e 0,95.")
            self.cfg["threshold"] = threshold
            temporary = CONFIG_PATH.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.cfg, indent=2), encoding="utf-8")
            os.replace(temporary, CONFIG_PATH)
            return True
        except (ValueError, OSError) as exc:
            self.say("Nao foi possivel salvar: " + str(exc))
            return False

    def choose_opera(self):
        if self.session.ready.is_set():
            self.say("Feche e reabra o aplicativo para trocar o executavel.")
            return
        selected = filedialog.askopenfilename(title="Selecione opera.exe ou launcher.exe do Opera GX",
                                              filetypes=[("Executavel", "*.exe")])
        if selected:
            self.cfg["opera_executable"] = selected
            self.save()
            self.say("Opera GX selecionado.")

    def open_browser(self):
        if self.opening or self.closing or self.session.ready.is_set():
            return
        executable = self.cfg.get("opera_executable") or find_opera_gx()
        if not executable or not Path(executable).is_file():
            self.say("Use Localizar executavel para selecionar seu Opera GX.")
            return
        self.opening = True
        self.say("Abrindo a sessao separada do Opera GX...")
        def open_session():
            try:
                self.session.start(executable)
                if not self.session.ready.wait(65):
                    raise RuntimeError(self.session.error or "Opera GX nao respondeu.")
                self.events.put(("status", self.session.warning or
                    "Sessao aberta. Faca login, calibre o mapa, a nave e uma box."))
            except Exception as exc:
                self.events.put(("status", str(exc)))
            finally:
                self.opening = False
        threading.Thread(target=open_session, daemon=True).start()

    def _decode(self, data):
        return cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)

    def start(self):
        if self.closing:
            return
        if self.worker is not None and self.worker.is_alive():
            if self.stop_event.is_set():
                self.root.after(100, self.start)
            return
        if not self.session.ready.is_set():
            self.say("Abra a sessao dedicada primeiro.")
            return
        if not self.save():
            return
        required = all(valid_area(self.cfg.get(k), self.viewport) for k in ("map","ship"))
        if not required or not MODEL_PATH.is_file():
            self.say("Calibre o mapa, aprenda uma box e marque somente a nave.")
            return
        if (self.cfg["ship"]["width"] > self.cfg["map"]["width"]/2 or
                self.cfg["ship"]["height"] > self.cfg["map"]["height"]/2):
            self.say("A marcacao da nave deve envolver somente a nave, sem o mapa inteiro.")
            return
        if not inside((self.cfg["ship"]["left"], self.cfg["ship"]["top"]), self.cfg["map"]) or not inside(
                (self.cfg["ship"]["left"]+self.cfg["ship"]["width"],
                 self.cfg["ship"]["top"]+self.cfg["ship"]["height"]), self.cfg["map"]):
            self.say("A area da nave deve ficar dentro do mapa.")
            return
        sample = cv2.imread(str(MODEL_PATH))
        if sample is None:
            self.say("Aprenda novamente uma box.")
            return
        self.stop_event = threading.Event()
        engine = Collector(self.session, self.cfg, sample, self.stop_event,
                           lambda event, data: self.events.put((event,data)), self._decode)
        self.worker = threading.Thread(target=engine.run, daemon=True)
        self.worker.start()
        self.say("Coleta iniciada. Voce pode usar outra janela; F9 pausa.")

    def pause(self):
        self.stop_event.set()
        self.say("Pausado. F8 inicia uma nova busca.")

    def stop(self):
        self.stop_event.set()
        self.say("Parado.")

    def calibrate(self, mode):
        if not self.session.ready.is_set():
            self.say("Abra o Opera GX dedicado e entre no jogo antes de calibrar.")
            return
        self.stop_event.set()
        if self.worker is not None and self.worker.is_alive():
            self.root.after(100, lambda: self.calibrate(mode))
            return
        def capture():
            try:
                data = self.session.request("screenshot")
                self.events.put(("calibrate", (mode,data)))
            except Exception as exc:
                self.events.put(("status", str(exc)))
        threading.Thread(target=capture, daemon=True).start()

    def _select(self, mode, data):
        image = Image.open(io.BytesIO(data)).convert("RGB")
        if image.size != (self.viewport["width"], self.viewport["height"]):
            self.say("A imagem mudou de tamanho. Reabra e calibre novamente.")
            return
        overlay = tk.Toplevel(self.root)
        overlay.title("Calibracao — imagem congelada")
        overlay.overrideredirect(True)
        overlay.geometry("%sx%s+0+0" % image.size)
        overlay.attributes("-topmost", True)
        overlay.after_idle(overlay.focus_force)
        canvas = tk.Canvas(overlay, width=image.width, height=image.height, highlightthickness=0, cursor="crosshair")
        canvas.pack()
        photo = ImageTk.PhotoImage(image)
        canvas._photo = photo
        canvas.create_image(0,0,anchor="nw",image=photo)
        label = {"map":"Arraste apenas a area espacial do mapa", "ship":"Arraste um retangulo justo na nave, sem boxes",
                 "minimap":"Arraste uma zona segura DENTRO do minimapa", "notice":"Arraste somente as mensagens novas de recompensa",
                 "sample":"Clique precisamente no CENTRO de uma box"}[mode]
        canvas.create_rectangle(8,8,min(image.width-8,800),45,fill="#17364c",outline="cyan")
        canvas.create_text(18,26,text="IMAGEM CONGELADA | "+label+" | ESC cancela",fill="white",anchor="w",font=("Segoe UI",12))
        start, drawn = [None], [None]
        def finish():
            overlay.destroy()
            self.root.deiconify()
            self._refresh()
        def down(event):
            start[0] = (event.x,event.y)
        def move(event):
            if start[0] and mode != "sample":
                if drawn[0] is not None:
                    canvas.delete(drawn[0])
                drawn[0] = canvas.create_rectangle(*start[0],event.x,event.y,outline="cyan",width=2)
        def up(event):
            if not start[0]:
                return
            if mode == "sample":
                x,y=event.x,event.y
                if 15 <= x < image.width-15 and 15 <= y < image.height-15:
                    image.crop((x-15,y-15,x+16,y+16)).save(MODEL_PATH)
                    self.say("Modelo de box salvo.")
            else:
                x1,x2=sorted((max(0,min(image.width,start[0][0])),max(0,min(image.width,event.x)))); y1,y2=sorted((max(0,min(image.height,start[0][1])),max(0,min(image.height,event.y))))
                area={"left":x1,"top":y1,"width":x2-x1,"height":y2-y1}
                minimum=150 if mode=="map" else 20
                if area["width"] >= minimum and area["height"] >= minimum:
                    self.cfg[mode]=area
                    self.save()
                    self.say("Area salva: "+mode)
                else:
                    self.say("Selecao pequena demais. Marque novamente.")
            finish()
        canvas.bind("<ButtonPress-1>",down)
        canvas.bind("<B1-Motion>",move)
        canvas.bind("<ButtonRelease-1>",up)
        overlay.bind("<Escape>",lambda event: finish())


    def test_detection(self):
        self.stop_event.set()
        if self.worker is not None and self.worker.is_alive():
            self.root.after(100, self.test_detection)
            return
        if not self.session.ready.is_set():
            self.say("Abra a sessao dedicada primeiro.")
            return
        if not valid_area(self.cfg.get("map"), self.viewport) or not MODEL_PATH.is_file():
            self.say("Marque o mapa dentro da imagem e aprenda uma box primeiro.")
            return
        if not self.save():
            return
        area = dict(self.cfg["map"])
        threshold = self.cfg["threshold"]
        def capture():
            try:
                data = self.session.request("screenshot")
                frame = self._decode(data)
                sample = cv2.imread(str(MODEL_PATH))
                if frame is None or sample is None:
                    raise ValueError("Imagem ou modelo indisponivel.")
                x,y,w,h = (int(area[k]) for k in ("left","top","width","height"))
                matches = locate_boxes(frame[y:y+h,x:x+w], sample, threshold=threshold)
                points = [(px+x,py+y,score) for px,py,score in matches]
                self.events.put(("detection", (data,points)))
            except Exception as exc:
                self.events.put(("status", "Teste interrompido: "+str(exc)))
        threading.Thread(target=capture, daemon=True).start()

    def show_detection(self, data, points):
        image = Image.open(io.BytesIO(data)).convert("RGB")
        original = image.size
        image.thumbnail((self.root.winfo_screenwidth()-80,self.root.winfo_screenheight()-180))
        sx,sy = image.width/original[0],image.height/original[1]
        window = tk.Toplevel(self.root)
        window.title("Teste de deteccao — coleta pausada")
        ttk.Label(window, text="%s candidatos. As cruzes devem ficar nas boxes. Nenhum clique foi enviado." % len(points),
                  padding=8).pack()
        canvas = tk.Canvas(window,width=image.width,height=image.height,highlightthickness=0)
        canvas.pack()
        photo = ImageTk.PhotoImage(image); canvas._photo = photo
        canvas.create_image(0,0,anchor="nw",image=photo)
        for x,y,score in points:
            x,y = x*sx,y*sy
            canvas.create_rectangle(x-10,y-10,x+10,y+10,outline="cyan",width=2)
            canvas.create_text(x+12,y,text="%.2f" % score,anchor="w",fill="cyan")
        window.lift()
        self.say("Teste: %s candidatos reconhecidos. Confira as marcacoes na imagem." % len(points))

    def preview(self):
        self.pause()
        if self.last_preview is None:
            self.say("Ainda nao foi enviado um clique de box nesta sessao.")
            return
        frame, point = self.last_preview
        image=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
        original=image.size
        image.thumbnail((self.root.winfo_screenwidth()-80,self.root.winfo_screenheight()-160))
        sx,sy=image.width/original[0],image.height/original[1]
        window=tk.Toplevel(self.root); window.title("Ultimo clique — cruz vermelha")
        ttk.Label(window,text="Confira se a cruz vermelha esta no centro da box. Coleta pausada.",padding=8).pack()
        canvas=tk.Canvas(window,width=image.width,height=image.height,highlightthickness=0); canvas.pack()
        photo=ImageTk.PhotoImage(image); canvas._photo=photo
        canvas.create_image(0,0,anchor="nw",image=photo)
        x,y=point[0]*sx,point[1]*sy
        canvas.create_line(x-14,y,x+14,y,fill="red",width=2)
        canvas.create_line(x,y-14,x,y+14,fill="red",width=2)

    def check_updates(self):
        self.say("Verificando atualizacoes deste bot...")
        def check():
            try:
                manifest=updater.check_for_update()
                if manifest:
                    self.events.put(("update",manifest))
                else:
                    self.events.put(("status","Este bot ja esta atualizado."))
            except Exception as exc:
                self.events.put(("status","Falha ao verificar atualizacao: "+str(exc)))
        threading.Thread(target=check,daemon=True).start()

    def _download(self, manifest):
        self.stop_event.set()
        self.say("Baixando e verificando a atualizacao...")
        def download():
            try:
                self.events.put(("update_ready",updater.stage_update(manifest)))
            except Exception as exc:
                self.events.put(("status","Atualizacao cancelada: "+str(exc)))
        threading.Thread(target=download,daemon=True).start()

    def _drain(self):
        if self.closing:
            return
        while True:
            try:
                event,data=self.events.get_nowait()
            except queue.Empty:
                break
            if event=="command":
                {"start":self.start,"pause":self.pause,"stop":self.stop}[data]()
            elif event=="status":
                self.say(data)
            elif event=="detection":
                self.show_detection(*data)
            elif event=="preview":
                self.last_preview=data
            elif event=="attempt":
                self.attempts+=1
            elif event=="confirmed":
                self.confirmed+=1
            elif event=="failed":
                self.failed+=1
            elif event=="calibrate":
                self._select(*data)
            elif event=="update":
                if messagebox.askyesno("Atualizacao", "Instalar a versao "+data["version"]+" deste bot?"):
                    self._download(data)
            elif event=="update_ready":
                self.close(lambda: updater.start_update(data,Path(__file__).resolve().parent))
                return
        self.stats.set("Tentativas: %s | Confirmadas: %s | Sem progresso: %s" %
                       (self.attempts,self.confirmed,self.failed))
        self.root.after(100,self._drain)

    def close(self, after=None):
        if self.closing:
            return
        self.closing=True
        self.stop_event.set()
        self.listener.stop()
        self.say("Encerrando a sessao dedicada...")
        done=threading.Event()
        def shutdown():
            try:
                self.session.close()
            finally:
                done.set()
        threading.Thread(target=shutdown,daemon=True).start()
        def finish():
            if not done.is_set():
                self.root.after(100,finish)
                return
            try:
                if after:
                    after()
            finally:
                self.root.destroy()
        finish()

if __name__=="__main__":
    root=tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    AutoBoxSemMouse(root)
    root.mainloop()
